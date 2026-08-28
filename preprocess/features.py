# -*- coding: utf-8 -*-
"""脳波・心拍・瞳孔・視線の特徴量。

どの関数も「切り出した区間」を受けて辞書を返す。設問単位でも窓単位でも
同じ関数を使い、区間の作り方だけを呼び出し側で変える。

値が取れないときは NaN を返し、行そのものは落とさない。落とすかどうかは
学習側で決められるようにする。品質の判定結果は別の列で持つ。
"""

from __future__ import annotations

import numpy as np
from scipy import signal

from xdf_io import Stream, rr_values

# ------------------------------------------------------------
# 既定値
# ------------------------------------------------------------

# 脳波の帯域（Hz）
#
# 低γ（30〜40Hz）は皮質γ活動として扱わないこと。乾式電極ではここに出るのは
# 主に筋電（側頭筋・前頭筋・首）である。列を消さないのは、筋緊張そのものが
# 認知負荷や行き詰まりと関係し、介入タイミングの推定に使えるため。
# 筋電なら4chが同時に上がり、脳波_振幅超過率 と相関する。
BANDS = {
    "θ": (4.0, 8.0),
    "α": (8.0, 13.0),
    "β": (13.0, 30.0),
    "低γ": (30.0, 40.0),
}

# サンプリング周波数は公称値で固定する。
#
# 本実験9セッションの XDF で実測したところ、実効レートは 256.0299〜256.0303 Hz
# （公称との差 0.012%）で、1.5倍を超えるサンプル間隔は9本すべてで0件だった。
# 取りこぼしも無い。帯域境界のずれは 0.001Hz 相当なので公称値のままでよい。
#
# **実効レートを fs に入れてはいけない。** muselsl はタイムスタンプを公称
# 256Hz の線形な格子に載せるため（実測の間隔は p1〜p75 が 3.9055〜3.9057ms で
# ほぼ一定）、そこから出した実効レートは循環している。取りこぼしがあった場合も
# デバイス側は 256Hz で取り続けているので、fs を下げるのは逆向きの補正になる。
# 対処は穴の検出と補間または窓の除外。
EEG_RATE = 256.0
EEG_BANDPASS = (1.0, 40.0)

# この振幅を超えるサンプルがあった窓は品質を落とす（µV）
# S01/pA の実測では p99 が 72〜162 µV、瞬目で 800 µV 超まで振れる
EEG_ARTIFACT_UV = 200.0

# 生理的にありえない RR を捨てる（ms）
RR_MIN_MS = 300.0
RR_MAX_MS = 2000.0

# 瞳孔の採用条件
#
# S01/pA では diameter_3d が約半分 NaN で、値が出ているときも
# eye0 が 1.36、eye1 が 2.17 と左右で 60% も違った。mm としてありえないので、
# 3D 眼球モデルが校正されていないと判断し、diameter_2d（px）を主に使う。
# px は目とカメラの距離で変わるため、セッション内の相対変化として扱うこと。
PUPIL_MIN_CONFIDENCE = 0.6
PUPIL_MIN_PX = 1.0
PUPIL_MAX_PX = 400.0
PUPIL_MIN_MM = 1.0
PUPIL_MAX_MM = 10.0

# ブロック列は問題によって数が違うので、最大数ぶん固定で出す
MAX_BLOCKS = 6

EEG_CHANNELS = ("TP9", "AF7", "AF8", "TP10")


def _nan_dict(keys) -> dict:
    return {k: np.nan for k in keys}


# ============================================================
# 脳波
# ============================================================

def eeg_columns() -> list[str]:
    cols = []

    for ch in EEG_CHANNELS:
        for band in BANDS:
            cols.append(f"脳波_{ch}_{band}")

    # 相対パワーと総パワー。
    #
    # 絶対値（µV²）は電極の当たりで数倍変わるので、被験者をまたぐと比べられない。
    # 学習側でセッションごとに標準化しても消えるのは「セッション全体のスケール」
    # だけで、セッション内で全帯域が同時に上下する共通ゲイン（首に力が入る、
    # 電極がずれる）は残る。相対パワーは窓ごとに比を取るのでこれが割り落ちる。
    #
    # 分母は4帯域の合計（≒4〜40Hz）。1〜40Hz の積分にすると瞬目のエネルギー
    # （4Hz未満）が分母に入り、相対パワーが瞬目に振られる。
    # 合計が1になるので4列のうち1列は冗長。木系のモデルなら害はない。
    for ch in EEG_CHANNELS:
        for band in BANDS:
            cols.append(f"脳波_{ch}_{band}相対")

    # 比にすると振幅そのものの情報が消えるので、別列で残す
    cols += [f"脳波_{ch}_総パワー" for ch in EEG_CHANNELS]

    cols += [
        "脳波_θα比",
        "脳波_前頭左右差α",
        "脳波_サンプル数",
        "脳波_品質",
        "脳波_振幅超過率",
        # 損失マスク。ラベル側の「〇〇ラベル有効」と同じ使い方をする。
        # 行は落とさないので、学習側でこの列を見て脳波の損失を外すこと
        "脳波有効",
    ]
    return cols


# 品質のうち、これだけを有効として扱う
EEG_QUALITY_OK = "有効"


def eeg_features(stream: Stream | None) -> dict:
    """帯域パワーを Welch で出す。単位は µV²（帯域内を積分した値）。

    品質の判定結果は `脳波_品質` と、それを 0/1 に落とした `脳波有効` で持つ。
    **行は落とさない。** どの行を使うかは学習側で決める。
    """
    out = _eeg_features(stream)

    # 品質は途中で上書きされる（振幅で判定したあと、区間が短ければ差し替わる）。
    # マスクは必ず最後に立てる
    out["脳波有効"] = int(out["脳波_品質"] == EEG_QUALITY_OK)

    return out


def _eeg_features(stream: Stream | None) -> dict:
    out = _nan_dict(eeg_columns())
    out["脳波_サンプル数"] = 0
    out["脳波_品質"] = "データなし"

    if stream is None or len(stream) == 0:
        return out

    values = np.asarray(stream.values, dtype=float)
    labels = stream.labels or [f"ch{i}" for i in range(values.shape[1])]
    n = len(values)

    out["脳波_サンプル数"] = n

    # 振幅の異常（瞬目・体動）はここで数えるだけ。行は落とさない
    finite = np.isfinite(values)
    over = np.abs(np.where(finite, values, 0.0)) > EEG_ARTIFACT_UV
    over_rate = float(over.any(axis=1).mean())

    out["脳波_振幅超過率"] = round(over_rate, 4)
    out["脳波_品質"] = "振幅過大" if over_rate > 0.10 else "有効"

    # Welch には最低 1 秒ぶん欲しい。足りなければ帯域パワーは出さない
    nperseg = int(min(n, EEG_RATE))

    if nperseg < 64:
        out["脳波_品質"] = "区間が短い"
        return out

    nyquist = EEG_RATE / 2.0
    sos = signal.butter(
        4,
        [EEG_BANDPASS[0] / nyquist, EEG_BANDPASS[1] / nyquist],
        btype="bandpass",
        output="sos",
    )

    powers: dict[str, dict[str, float]] = {}

    for i, label in enumerate(labels):
        col = values[:, i]
        good = np.isfinite(col)

        if not good.any():
            continue

        # 欠損は平均で埋める。区間内の欠損はごく少ないため影響は小さい
        col = np.where(good, col, col[good].mean())
        filtered = signal.sosfiltfilt(sos, col - col.mean())
        freqs, psd = signal.welch(filtered, fs=EEG_RATE, nperseg=nperseg)

        powers[label] = {}

        for band, (lo, hi) in BANDS.items():
            sel = (freqs >= lo) & (freqs < hi)
            value = float(np.trapezoid(psd[sel], freqs[sel])) if sel.any() else np.nan
            powers[label][band] = value
            out[f"脳波_{label}_{band}"] = round(value, 4)

    # 相対パワーと総パワー。同じ PSD の積分値を使い回す
    for label, band_power in powers.items():
        values_ = [band_power.get(b, np.nan) for b in BANDS]

        if not all(np.isfinite(v) for v in values_):
            continue

        total = float(sum(values_))
        out[f"脳波_{label}_総パワー"] = round(total, 4)

        if total <= 0:
            continue

        for band in BANDS:
            out[f"脳波_{label}_{band}相対"] = round(band_power[band] / total, 4)

    # θ/α 比。4ch の平均どうしで割る
    theta = [p["θ"] for p in powers.values() if np.isfinite(p.get("θ", np.nan))]
    alpha = [p["α"] for p in powers.values() if np.isfinite(p.get("α", np.nan))]

    if theta and alpha and np.mean(alpha) > 0:
        out["脳波_θα比"] = round(float(np.mean(theta) / np.mean(alpha)), 4)

    # 前頭の左右差。比を対数で取り、左右のスケール差に寄らない形にする
    left = powers.get("AF7", {}).get("α", np.nan)
    right = powers.get("AF8", {}).get("α", np.nan)

    if np.isfinite(left) and np.isfinite(right) and left > 0 and right > 0:
        out["脳波_前頭左右差α"] = round(float(np.log(left) - np.log(right)), 4)

    return out


# ============================================================
# 心拍
# ============================================================

def hrv_columns() -> list[str]:
    return [
        "心拍_平均HR",
        "心拍_サンプル数",
        "心拍_RR件数",
        "心拍_RR平均ms",
        "心拍_RMSSD",
        "心拍_SDNN",
        "心拍_pNN50",
    ]


def hrv_features(rows: list[dict]) -> dict:
    """Garmin の JSON 列から心拍と変動指標を出す。

    rr_ms は数値でもリストでも来る（xdf_io.rr_values が両方受ける）。
    """
    out = _nan_dict(hrv_columns())
    out["心拍_サンプル数"] = len(rows)
    out["心拍_RR件数"] = 0

    if not rows:
        return out

    hr = [float(r["hr_bpm"]) for r in rows if r.get("hr_bpm") is not None]

    if hr:
        out["心拍_平均HR"] = round(float(np.mean(hr)), 2)

    rr: list[float] = []

    for r in rows:
        rr.extend(rr_values(r))

    rr = np.array([v for v in rr if RR_MIN_MS <= v <= RR_MAX_MS], dtype=float)
    out["心拍_RR件数"] = int(len(rr))

    if len(rr) >= 1:
        out["心拍_RR平均ms"] = round(float(rr.mean()), 2)

    if len(rr) >= 2:
        diff = np.diff(rr)
        out["心拍_RMSSD"] = round(float(np.sqrt(np.mean(diff ** 2))), 2)
        out["心拍_SDNN"] = round(float(rr.std(ddof=1)), 2)
        out["心拍_pNN50"] = round(float((np.abs(diff) > 50).mean() * 100.0), 2)

    return out


# ============================================================
# 瞳孔
# ============================================================

def pupil_columns() -> list[str]:
    cols = []

    for eye in (0, 1):
        cols += [
            f"瞳孔_eye{eye}_平均px",
            f"瞳孔_eye{eye}_標準偏差px",
            f"瞳孔_eye{eye}_件数",
            f"瞳孔_eye{eye}_平均mm",
        ]

    cols += ["瞳孔_採用率", "瞳孔_3d有効率"]
    return cols


def pupil_features(stream: Stream | None) -> dict:
    """瞳孔の大きさ。diameter_2d（px）を主、diameter_3d（mm）を従にする。

    3D 側は S01/pA で半分が NaN、左右で 60% 食い違っていたため信用しない。
    px は絶対値に意味が無いので、学習側でセッションごとに標準化して使う。
    """
    out = _nan_dict(pupil_columns())

    for eye in (0, 1):
        out[f"瞳孔_eye{eye}_件数"] = 0

    if stream is None or len(stream) == 0:
        return out

    values = np.asarray(stream.values, dtype=float)

    eye_id = values[:, 0]
    px = values[:, 1]
    mm = values[:, 2]
    confidence = values[:, 3]

    ok = (
        (confidence >= PUPIL_MIN_CONFIDENCE)
        & np.isfinite(px)
        & (px >= PUPIL_MIN_PX)
        & (px <= PUPIL_MAX_PX)
    )
    ok_mm = (
        (confidence >= PUPIL_MIN_CONFIDENCE)
        & np.isfinite(mm)
        & (mm >= PUPIL_MIN_MM)
        & (mm <= PUPIL_MAX_MM)
    )

    out["瞳孔_採用率"] = round(float(ok.mean()), 4)
    out["瞳孔_3d有効率"] = round(float(ok_mm.mean()), 4)

    for eye in (0, 1):
        is_eye = eye_id == eye
        sel = ok & is_eye
        count = int(sel.sum())
        out[f"瞳孔_eye{eye}_件数"] = count

        if count >= 2:
            d = px[sel]
            out[f"瞳孔_eye{eye}_平均px"] = round(float(d.mean()), 4)
            out[f"瞳孔_eye{eye}_標準偏差px"] = round(float(d.std(ddof=1)), 4)
        elif count == 1:
            out[f"瞳孔_eye{eye}_平均px"] = round(float(px[sel][0]), 4)

        sel_mm = ok_mm & is_eye

        if sel_mm.any():
            out[f"瞳孔_eye{eye}_平均mm"] = round(float(mm[sel_mm].mean()), 4)

    return out


# ============================================================
# 注視（Pupil の fixation ストリーム）
# ============================================================

def fixation_columns() -> list[str]:
    # 回数と合計時間は区間の長さで割る。設問単位は滞在時間がばらつくので、
    # 生の値だと「長くいた設問ほど大きい」だけの値になり、滞在ミリ秒と
    # 同じ情報を二重に持ってしまう
    return ["注視_回数毎秒", "注視_平均時間ms", "注視_時間割合", "注視_件数"]


def fixation_features(stream: Stream | None, span_s: float | None = None) -> dict:
    """注視の頻度と長さ。

    このストリームは1つの注視につき複数サンプルを流すため、
    fixation_id でまとめてから数える。duration はその注視の最大値を採る。

    span_s（区間の長さ）を渡すと、回数と合計時間を毎秒・割合に直す。
    渡さないときは生の件数だけを返す。

    注意：S01/pA では平均時間が 307〜308ms に張り付いており、Pupil 側の
    検出設定によるものと見られる。本実験でも注視数がセッション間で25倍
    ばらついている（397〜10,361）。使う前に品質を確かめること。
    """
    out = _nan_dict(fixation_columns())
    out["注視_件数"] = 0

    if stream is None or len(stream) == 0:
        return out

    values = np.asarray(stream.values, dtype=float)
    ids = values[:, 0]
    durations = values[:, 3]

    unique = np.unique(ids[np.isfinite(ids)])
    out["注視_件数"] = int(len(unique))

    if len(unique) == 0:
        return out

    per_fixation = np.array(
        [np.nanmax(durations[ids == i]) for i in unique],
        dtype=float,
    )
    per_fixation = per_fixation[np.isfinite(per_fixation)]

    if not len(per_fixation):
        return out

    out["注視_平均時間ms"] = round(float(per_fixation.mean()), 2)

    if span_s and span_s > 0:
        out["注視_回数毎秒"] = round(len(unique) / span_s, 4)
        # 合計が区間長を超えることがある（注視が区間をまたぐ）。1 で頭打ちにする
        out["注視_時間割合"] = round(min(per_fixation.sum() / 1000.0 / span_s, 1.0), 4)

    return out


# ============================================================
# 視線の領域
# ============================================================

# ブロックの滞在としてこれ未満は数えない（境界の揺れで偽の遷移が出るため）
GAZE_MIN_DWELL_S = 0.10


def gaze_columns() -> list[str]:
    cols = [
        "視線_サンプル数",
        "視線_画面内率",
        "視線_コード率",
        "視線_設計書率",
        # 回数は毎秒に直す。設問単位は滞在時間が数十秒〜数千秒とばらつくため、
        # 生の回数だと「長くいた設問ほど大きい」だけの値になり、滞在ミリ秒と
        # 同じ情報を二重に持ってしまう
        "視線_往復回数毎秒",
        "視線_ブロック遷移毎秒",
        # ブロック境界を使わないので、縦の校正がずれていても影響を受けない
        "視線_コード縦移動量毎秒",
        "視線_コード縦分散",
    ]

    cols += [f"視線_B{i}率" for i in range(1, MAX_BLOCKS + 1)]
    return cols


def gaze_features(
    region: np.ndarray,
    block: np.ndarray,
    times: np.ndarray | None = None,
    y_window: np.ndarray | None = None,
) -> dict:
    """領域とブロックの割合、行き来の頻度、コード内の縦の動き。

    割合の分母は「画面内にあったサンプル」。画面外の割合は別の列で持つ。
    回数は区間の長さで割って毎秒に直す。

    times と y_window を渡すと、コード内の縦の動きも出す。本実験9セッションで
    調べたところ、押下直前は縦移動量が減る（8件中7件）。ブロック境界を使わない
    ので、縦の校正がずれていても影響を受けない。
    """
    from regions import REGION_CODE, REGION_DOC

    out = _nan_dict(gaze_columns())
    out["視線_サンプル数"] = int(len(region))

    if len(region) == 0:
        return out

    region = np.asarray(region, dtype=object)
    block = np.asarray(block, dtype=object)

    is_code = region == REGION_CODE
    is_doc = region == REGION_DOC
    on_screen = is_code | is_doc

    out["視線_画面内率"] = round(float(on_screen.mean()), 4)

    # 区間の長さ。時刻が無ければサンプル数から概算できないので回数は出さない
    span = None

    if times is not None and len(times) > 1:
        span = float(np.max(times) - np.min(times))

        if span <= 0:
            span = None

    n_on = int(on_screen.sum())

    if n_on == 0:
        return out

    out["視線_コード率"] = round(float(is_code.sum() / n_on), 4)
    out["視線_設計書率"] = round(float(is_doc.sum() / n_on), 4)

    # 往復。画面外を挟んでも、コードと設計書が入れ替わったら1回と数える
    side = region[on_screen]
    flips = int((side[1:] != side[:-1]).sum()) if len(side) > 1 else 0

    if span:
        out["視線_往復回数毎秒"] = round(flips / span, 4)

    n_code = int(is_code.sum())

    if n_code:
        for i in range(1, MAX_BLOCKS + 1):
            name = f"B{i}"
            out[f"視線_{name}率"] = round(
                float((block[is_code] == name).sum() / n_code), 4
            )

    # ---- ここから下はコード側だけを見る
    if times is None or y_window is None or n_code < 2:
        return out

    times = np.asarray(times, dtype=float)
    y_window = np.asarray(y_window, dtype=float)

    tc = times[is_code]
    yc = y_window[is_code]
    good = np.isfinite(yc)
    tc, yc = tc[good], yc[good]

    if len(yc) < 2:
        return out

    out["視線_コード縦分散"] = round(float(yc.var()), 6)

    if span:
        out["視線_コード縦移動量毎秒"] = round(float(np.abs(np.diff(yc)).sum() / span), 4)
        out["視線_ブロック遷移毎秒"] = round(
            _block_transitions(block[is_code][good], tc) / span, 4
        )

    return out


def _block_transitions(labels: np.ndarray, times: np.ndarray) -> int:
    """ブロックが変わった回数。短すぎる滞在は数えない。

    境界の上で視線が揺れると偽の遷移が並ぶので、GAZE_MIN_DWELL_S 未満の
    滞在は無かったことにしてから数える。
    """
    if len(labels) < 2:
        return 0

    runs = []
    cur = labels[0]
    start = times[0]

    for i in range(1, len(labels)):
        if labels[i] != cur:
            runs.append((cur, times[i] - start))
            cur = labels[i]
            start = times[i]

    runs.append((cur, times[-1] - start))

    keep = [name for name, dwell in runs if dwell >= GAZE_MIN_DWELL_S and name != ""]

    return sum(1 for i in range(1, len(keep)) if keep[i] != keep[i - 1])


# ============================================================
# 全部まとめる
# ============================================================

def all_columns() -> list[str]:
    return (
        eeg_columns()
        + hrv_columns()
        + pupil_columns()
        + fixation_columns()
        + gaze_columns()
    )
