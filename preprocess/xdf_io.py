# -*- coding: utf-8 -*-
"""XDF の読み込みと、課題の経過時間への整列。

XDF の中の時刻は LSL のローカル時計（起動からの秒数）で、
課題ページが書き出す時刻は「開始ボタンからの経過ミリ秒」である。
この2つをつなぐのが ExperimentMarkers の task_start ただ1点。

    XDF時刻 = task_start の LSL時刻 + 経過秒

逆に、XDF のサンプル時刻から経過秒を出すには task_start を引く。
本モジュールは読み込んだ時点で全ストリームの時刻を経過秒へ直し、
以降の処理が LSL 時計を意識しなくて済むようにする。
"""

from __future__ import annotations

import json
import struct
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyxdf

# lsl/view_xdf.py の関数を使い回す（同じ読み方を二重に書かない）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lsl"))
from view_xdf import channel_labels, stream_name, stream_type  # noqa: E402


MARKER_STREAM = "ExperimentMarkers"
MARKER_TASK_START = "task_start"
MARKER_TASK_END = "task_end"
MARKER_SUPPORT = "support"


# ============================================================
# ストリーム1本ぶんの入れ物
# ============================================================

@dataclass
class Stream:
    """1本のストリーム。時刻は task_start を 0 とした経過秒。"""

    name: str
    type: str
    labels: list[str]
    times: np.ndarray                    # (N,) 経過秒
    values: np.ndarray | list            # 数値なら (N, ch)、文字列ならリスト
    is_string: bool

    def __len__(self) -> int:
        return len(self.times)

    def slice(self, start_s: float, end_s: float) -> "Stream":
        """[start_s, end_s) を切り出す。境界の扱いは全特徴量で共通にする。"""
        keep = (self.times >= start_s) & (self.times < end_s)

        if self.is_string:
            values = [v for v, k in zip(self.values, keep) if k]
        else:
            values = self.values[keep]

        return Stream(
            name=self.name,
            type=self.type,
            labels=self.labels,
            times=self.times[keep],
            values=values,
            is_string=self.is_string,
        )

    def column(self, label: str) -> np.ndarray:
        """ラベル名で列を取り出す。無い場合は空配列。"""
        if self.is_string or label not in self.labels:
            return np.empty(0)
        return np.asarray(self.values)[:, self.labels.index(label)]


# ============================================================
# 記録1本ぶん
# ============================================================

@dataclass
class Recording:
    path: Path
    streams: dict[str, Stream] = field(default_factory=dict)
    task_start_lsl: float | None = None
    # task_end は課題の終端には使わない（events.csv のほうが確か）。
    # 実際の記録では入っていなかったため、様子を見るためだけに持っている
    has_task_end: bool = False
    truncated: bool = False              # 末尾が欠けていた（記録を途中で止めた記録）
    support_times: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def get(self, name: str) -> Stream | None:
        return self.streams.get(name)

    def eeg(self) -> Stream | None:
        """Muse は EEG と ACC の2本が同じ name で来るため型で選ぶ。"""
        return self.streams.get("Muse/EEG")

    def acc(self) -> Stream | None:
        return self.streams.get("Muse/ACC")


# ============================================================
# 文字列サンプルの取り出し
# ============================================================

def _string_samples(stream) -> list[str]:
    """pyxdf の文字列ストリームから素の文字列を並べて返す。"""
    out = []

    for sample in stream["time_series"]:
        value = sample[0] if isinstance(sample, (list, tuple, np.ndarray)) else sample

        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")

        out.append(str(value))

    return out


def parse_json_stream(stream: Stream) -> list[dict]:
    """JSON 文字列のストリームを辞書の並びへ直す。

    Garmin（hr_bpm / rr_ms）と PupilSurface（kind / x / y / on_surface）が
    どちらもこの形。壊れた行は黙って捨てる（記録側の取りこぼしに強くする）。
    """
    rows = []

    for t, text in zip(stream.times, stream.values):
        try:
            obj = json.loads(text)
        except Exception:
            continue

        if isinstance(obj, dict):
            obj["経過秒"] = float(t)
            rows.append(obj)

    return rows


def rr_values(row: dict) -> list[float]:
    """Garmin の rr_ms を取り出す。

    view_xdf.py はリストを前提にしているが、実データは数値で来ていた。
    どちらでも受けられるようにする。
    """
    value = row.get("rr_ms")

    if value is None:
        return []

    if isinstance(value, (list, tuple)):
        return [float(v) for v in value if v is not None]

    try:
        return [float(value)]
    except (TypeError, ValueError):
        return []


# ============================================================
# 途中で切れた XDF を読む
# ============================================================

def last_complete_chunk(data: bytes) -> int:
    """最後の完全なチャンクが終わる位置を返す。

    XDF は「可変長整数の長さ → uint16 のタグ → 中身」の繰り返し。
    可変長整数は先頭1バイトが後続のバイト数（1・4・8 のいずれか）。
    記録が途中で止まると末尾のチャンクが欠けるので、そこを切り落とす。
    """
    n = len(data)

    if n < 4 or data[:4] != b"XDF:":
        return 0

    pos = 4
    last = 4

    while pos < n:
        width = data[pos]

        if width not in (1, 4, 8) or pos + 1 + width > n:
            break

        length = int.from_bytes(data[pos + 1 : pos + 1 + width], "little")
        end = pos + 1 + width + length

        # 長さにはタグの 2 バイトが含まれる
        if length < 2 or end > n:
            break

        pos = end
        last = end

    return last


def load_streams(path: Path) -> tuple[list, list[str], bool]:
    """pyxdf で読む。末尾が欠けている場合は切り落としてから読み直す。

    記録を途中で止めると末尾のチャンクが欠け、pyxdf が struct.error で落ちる。
    途中で止めた記録は、末尾に数十バイトの欠けが残る。
    3つめの戻り値が「末尾が欠けていたか」。
    """
    notes: list[str] = []

    try:
        streams, _ = pyxdf.load_xdf(str(path))
        return streams, notes, False
    except Exception as e:
        # except を抜けると e が消えるので、メッセージだけ残す
        reason = f"{type(e).__name__}: {e}"

    data = Path(path).read_bytes()
    cut = last_complete_chunk(data)

    if cut <= 4 or cut >= len(data):
        raise RuntimeError(f"XDFを読めません（{reason}）")

    dropped = len(data) - cut
    notes.append(f"末尾 {dropped} バイトが欠けていたため切り落として読み込み")

    with tempfile.TemporaryDirectory() as tmp:
        repaired = Path(tmp) / Path(path).name
        repaired.write_bytes(data[:cut])
        streams, _ = pyxdf.load_xdf(str(repaired))

    return streams, notes, True


# ============================================================
# 読み込み
# ============================================================

def load(path: Path) -> Recording:
    """XDF を読み、時刻を task_start 基準の経過秒へ直して返す。

    task_start が無い記録は、整列の基準が無いので None のまま返す。
    呼び出し側で網羅状況として記録し、その記録は特徴量から外す。
    """
    rec = Recording(path=Path(path))

    streams, notes, truncated = load_streams(Path(path))
    rec.notes.extend(notes)
    rec.truncated = truncated

    # ---- 先にマーカーを読み、時刻の原点を決める
    raw_marker = None

    for s in streams:
        if stream_name(s) == MARKER_STREAM:
            raw_marker = s
            break

    if raw_marker is None:
        rec.notes.append(f"{MARKER_STREAM} が無い")
    else:
        texts = _string_samples(raw_marker)
        times = np.asarray(raw_marker["time_stamps"], dtype=float)

        for text, t in zip(texts, times):
            if text == MARKER_TASK_START and rec.task_start_lsl is None:
                rec.task_start_lsl = float(t)
            elif text == MARKER_TASK_END:
                rec.has_task_end = True

        if rec.task_start_lsl is None:
            rec.notes.append(f"{MARKER_TASK_START} マーカーが無い")

    origin = rec.task_start_lsl if rec.task_start_lsl is not None else 0.0

    if rec.task_start_lsl is None:
        rec.notes.append("時刻の原点が無いため経過秒は記録開始基準")

        all_times = [
            float(np.asarray(s["time_stamps"], dtype=float)[0])
            for s in streams
            if len(s["time_stamps"])
        ]

        if all_times:
            origin = min(all_times)

    # ---- 各ストリームを経過秒へ直す
    for s in streams:
        name = stream_name(s)
        stype = stream_type(s)
        times = np.asarray(s["time_stamps"], dtype=float) - origin

        fmt = s["info"]["channel_format"][0]
        is_string = fmt == "string"

        if is_string:
            values = _string_samples(s)
        else:
            values = np.asarray(s["time_series"], dtype=float)

            if values.ndim == 1:
                values = values[:, None]

        labels = channel_labels(s)

        if len(labels) != (0 if is_string else values.shape[1]):
            labels = [] if is_string else [f"ch{i}" for i in range(values.shape[1])]

        # Muse は EEG と ACC が同名なので型で分ける
        key = f"{name}/{stype}" if name == "Muse" else name

        rec.streams[key] = Stream(
            name=name,
            type=stype,
            labels=labels,
            times=times,
            values=values,
            is_string=is_string,
        )

    # ---- ヒント要請（support）の時刻を経過秒で持つ
    if raw_marker is not None:
        marker = rec.streams.get(MARKER_STREAM)

        if marker is not None:
            rec.support_times = [
                float(t)
                for t, text in zip(marker.times, marker.values)
                if text == MARKER_SUPPORT
            ]

    return rec
