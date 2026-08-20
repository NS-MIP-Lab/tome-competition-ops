# -*- coding: utf-8 -*-
"""XDF と課題データを、モデルに学習させられる表へ一括変換する。

    python preprocess/build_dataset.py
    python preprocess/build_dataset.py --window 10 --hop 2 --horizon 20
    python preprocess/build_dataset.py --task-data task_data --out dataset

出力（すべて utf-8-sig、列名は日本語）

    coverage.csv         セッション × ストリーム。**最初に見るべき表**
    surface_fit.csv      座標変換の当てはまり採点（4通り）
    gaze_regions.csv     視線1サンプル1行。領域・ブロック・設問つき
    features_step.csv    設問単位。理解度と対応づけやすい
    features_window.csv  窓単位。介入タイミング推定用
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import features  # noqa: E402
import regions  # noqa: E402
import task_io  # noqa: E402
import xdf_io  # noqa: E402

ENC = "utf-8-sig"

# 学習に使えるサンプルとみなす最低条件（窓単位）
DEFAULT_WINDOW_S = 5.0
DEFAULT_HOP_S = 1.0
DEFAULT_HORIZON_S = 10.0


# ============================================================
# 設問の対応表
# ============================================================

def step_intervals(session: task_io.Session) -> list[dict]:
    """設問滞在を [開始秒, 終了秒) の並びに直す。訪問ごとに1件。"""
    out = []

    for _, r in session.steps().iterrows():
        out.append(
            {
                "設問": str(r["対象"]),
                "訪問": int(r["連番"]),
                "開始秒": float(r["開始経過ミリ秒"]) / 1000.0,
                "終了秒": float(r["終了経過ミリ秒"]) / 1000.0,
            }
        )

    return sorted(out, key=lambda d: d["開始秒"])


def step_at(intervals: list[dict], times: np.ndarray) -> np.ndarray:
    """各時刻に表示していた設問を返す。滞在の外は空文字。

    設問は1度に1つしか出ないので、区間は重ならない。
    理解度テストを出している間は設問滞在が閉じているため、そこは空になる。
    """
    out = np.full(len(times), "", dtype=object)

    for iv in intervals:
        hit = (times >= iv["開始秒"]) & (times < iv["終了秒"])
        out[hit] = iv["設問"]

    return out


def quiz_lookup(session: task_io.Session) -> dict[str, str]:
    """設問 → その直後の理解度テストの正誤。"""
    out = {}

    for _, q in session.quizzes().iterrows():
        _qid, verdict = task_io.quiz_result(q["補足"])
        out[str(q["対象"])] = verdict

    return out


# ============================================================
# 視線の表を1セッションぶん作る
# ============================================================

def build_gaze_table(
    session: task_io.Session,
    rec: xdf_io.Recording,
    layout: regions.Layout | None,
) -> tuple[pd.DataFrame, list[dict], regions.Transform]:
    """サーフェス視線を、領域とブロックつきの長形式にする。

    戻り値の2つめは座標変換の採点表、3つめは採用した変換。
    """
    empty = pd.DataFrame(
        columns=[
            "経過秒", "x_surface", "y_surface", "サーフェス内",
            "x_window", "y_window", "領域", "ブロックID", "設問",
        ]
    )

    stream = rec.get("PupilSurface")

    if stream is None or len(stream) == 0:
        return empty, [], regions.CANDIDATES[0]

    rows = [r for r in xdf_io.parse_json_stream(stream) if r.get("kind") == "gaze"]

    if not rows:
        return empty, [], regions.CANDIDATES[0]

    times = np.array([r["経過秒"] for r in rows], dtype=float)
    xs = np.array([r.get("x", np.nan) for r in rows], dtype=float)
    ys = np.array([r.get("y", np.nan) for r in rows], dtype=float)
    on = np.array([bool(r.get("on_surface")) for r in rows], dtype=bool)

    # ---- 座標変換を決める。layout が無ければ採点できないので既定値
    fit_rows: list[dict] = []
    transform = regions.CANDIDATES[0]

    if layout is not None and on.any():
        transform, fit_rows = regions.best_transform(xs[on], ys[on], layout)

    # ---- 1サンプルだけ飛ぶ点を抑える。ありえない往復が数えられるのを防ぐ
    xs_smooth = regions.median_filter(xs)
    ys_smooth = regions.median_filter(ys)

    x_win, y_win = transform.apply(xs_smooth, ys_smooth)
    region, block = regions.assign(x_win, y_win, on, layout)

    step = step_at(step_intervals(session), times)

    table = pd.DataFrame(
        {
            "経過秒": np.round(times, 4),
            "x_surface": np.round(xs, 5),
            "y_surface": np.round(ys, 5),
            "サーフェス内": on,
            "x_window": np.round(x_win, 5),
            "y_window": np.round(y_win, 5),
            "領域": region,
            "ブロックID": block,
            "設問": step,
        }
    )

    return table, fit_rows, transform


# ============================================================
# 区間ひとつぶんの特徴量
# ============================================================

def segment_features(
    rec: xdf_io.Recording,
    gaze: pd.DataFrame,
    start_s: float,
    end_s: float,
) -> dict:
    """[start_s, end_s) の特徴量をまとめて出す。"""
    out: dict = {}

    eeg = rec.eeg()
    out.update(features.eeg_features(eeg.slice(start_s, end_s) if eeg else None))

    garmin = rec.get("GarminVenu3S")
    rows = xdf_io.parse_json_stream(garmin.slice(start_s, end_s)) if garmin else []
    out.update(features.hrv_features(rows))

    pupil = rec.get("PupilPupillometry")
    out.update(features.pupil_features(pupil.slice(start_s, end_s) if pupil else None))

    fix = rec.get("PupilFixations")
    out.update(features.fixation_features(fix.slice(start_s, end_s) if fix else None))

    if len(gaze):
        sel = gaze[(gaze["経過秒"] >= start_s) & (gaze["経過秒"] < end_s)]
        out.update(
            features.gaze_features(
                sel["領域"].to_numpy(), sel["ブロックID"].to_numpy()
            )
        )
    else:
        out.update(features.gaze_features(np.array([]), np.array([])))

    return out


# ============================================================
# 設問単位
# ============================================================

def build_step_rows(
    session: task_io.Session,
    rec: xdf_io.Recording,
    gaze: pd.DataFrame,
) -> list[dict]:
    """1行 = 被験者 × 問題 × 設問。訪問を1つにまとめる。

    設問は行き戻りがあるため、訪問ごとの区間をすべて足したものを1行にする。
    特徴量は最初と最後を含む全区間から出す（間に別の設問を挟むことがあるが、
    設問ごとの滞在は連続していないので、区間ごとに出して重み付き平均を取る）。
    """
    intervals = step_intervals(session)

    if not intervals:
        return []

    quizzes = quiz_lookup(session)
    duration = session.duration_s() or 0.0

    by_step: dict[str, list[dict]] = {}

    for iv in intervals:
        by_step.setdefault(iv["設問"], []).append(iv)

    rows = []

    for step, ivs in sorted(by_step.items()):
        total_ms = sum((iv["終了秒"] - iv["開始秒"]) for iv in ivs) * 1000.0

        # 訪問ごとに特徴量を出し、滞在時間で重み付けして平均する
        per_visit = []
        weights = []

        for iv in ivs:
            per_visit.append(segment_features(rec, gaze, iv["開始秒"], iv["終了秒"]))
            weights.append(max(iv["終了秒"] - iv["開始秒"], 1e-6))

        merged = _weighted_merge(per_visit, weights)

        row = {
            "被験者ID": session.subject,
            "問題ID": session.problem,
            "アルゴリズム": session.algorithm,
            "条件": session.mode,
            "設問": step,
            "訪問回数": len(ivs),
            "滞在ミリ秒": round(total_ms),
            "初回開始秒": round(ivs[0]["開始秒"], 3),
            "最終終了秒": round(ivs[-1]["終了秒"], 3),
            "課題全体秒": round(duration, 3),
            "理解度正誤": quizzes.get(step, ""),
            "介入要請回数": sum(
                1
                for t in rec.support_times
                if any(iv["開始秒"] <= t < iv["終了秒"] for iv in ivs)
            ),
        }
        row.update(merged)
        rows.append(row)

    return rows


def _weighted_merge(dicts: list[dict], weights: list[float]) -> dict:
    """数値列は重み付き平均、文字列列は最も重い区間の値を採る。"""
    if not dicts:
        return {}

    if len(dicts) == 1:
        return dicts[0]

    heaviest = dicts[int(np.argmax(weights))]
    out: dict = {}

    for key in dicts[0]:
        values = [d.get(key) for d in dicts]

        if all(isinstance(v, str) for v in values):
            out[key] = heaviest[key]
            continue

        arr = np.array(
            [v if isinstance(v, (int, float, np.floating)) else np.nan for v in values],
            dtype=float,
        )
        w = np.array(weights, dtype=float)
        ok = np.isfinite(arr)

        if not ok.any():
            out[key] = np.nan
            continue

        # 件数や回数は足し算のほうが素直
        if key.endswith(("件数", "回数", "サンプル数")):
            out[key] = float(arr[ok].sum())
        else:
            out[key] = round(float((arr[ok] * w[ok]).sum() / w[ok].sum()), 6)

    return out


# ============================================================
# 窓単位
# ============================================================

def build_window_rows(
    session: task_io.Session,
    rec: xdf_io.Recording,
    gaze: pd.DataFrame,
    window_s: float,
    hop_s: float,
    horizon_s: float,
) -> list[dict]:
    """1行 = 固定長の窓。介入要請の先読みラベルを付ける。

    課題全体の長さは events.csv のセッション行から取る。
    task_end マーカーは記録されないことがあるため、そちらには頼らない。
    """
    duration = session.duration_s()

    if duration is None or duration <= 0:
        return []

    intervals = step_intervals(session)
    quizzes = quiz_lookup(session)
    supports = np.array(rec.support_times, dtype=float)

    rows = []
    start = 0.0

    while start + window_s <= duration + 1e-9:
        end = start + window_s

        # その窓の中央で表示していた設問を代表にする
        center = np.array([start + window_s / 2.0])
        step = step_at(intervals, center)[0]

        # 先読み：窓の終わりから horizon 秒以内に support があるか
        upcoming = supports[(supports >= end) & (supports < end + horizon_s)]
        after = supports[supports >= end]

        row = {
            "被験者ID": session.subject,
            "問題ID": session.problem,
            "アルゴリズム": session.algorithm,
            "条件": session.mode,
            "窓開始秒": round(start, 3),
            "窓終了秒": round(end, 3),
            "窓長秒": window_s,
            "設問": step,
            "理解度正誤": quizzes.get(step, ""),
            "介入要請あり": int(len(upcoming) > 0),
            "介入要請までの秒数": round(float(after.min() - end), 3) if len(after) else np.nan,
        }
        row.update(segment_features(rec, gaze, start, end))
        rows.append(row)

        start += hop_s

    return rows


# ============================================================
# 網羅状況
# ============================================================

STREAM_KEYS = [
    ("Muse/EEG", "脳波"),
    ("Muse/ACC", "加速度"),
    ("PupilSurface", "サーフェス視線"),
    ("PupilGaze", "視線"),
    ("PupilFixations", "注視"),
    ("PupilPupillometry", "瞳孔"),
    ("GarminVenu3S", "心拍"),
    ("ExperimentMarkers", "マーカー"),
]


def classify(
    session: task_io.Session,
    rec: xdf_io.Recording | None,
    gaze: pd.DataFrame,
) -> str:
    """このセッションが学習に使えるかを一言で表す。

    「中断」は、記録を途中で止めた回。XDF の末尾が欠けたまま
    課題データも保存されていない形になる。異常ではないので、
    欠けの警告とは分けて表示する。
    """
    if rec is None:
        return "XDFなし"

    if rec.truncated and session.json_path is None:
        return "中断"

    if rec.task_start_lsl is None:
        return "整列不可（task_startなし）"

    if session.events is None:
        return "課題データなし"

    if len(gaze) == 0:
        return "視線なし"

    return "使用可"


def coverage_row(
    session: task_io.Session,
    rec: xdf_io.Recording | None,
    gaze: pd.DataFrame,
) -> dict:
    row = {
        "被験者ID": session.subject,
        "問題ID": session.problem,
        "条件": session.mode,
        "判定": classify(session, rec, gaze),
        "XDF": session.xdf.name if session.xdf else "",
        "課題データ": "あり" if session.json_path else "なし",
        "events.csv": "あり" if session.events is not None else "なし",
        "layout.csv": "あり" if session.layout is not None else "なし",
        "課題全体秒": session.duration_s() if session.duration_s() else np.nan,
        "task_start": "あり" if rec and rec.task_start_lsl is not None else "なし",
        "ヒント要請数": len(rec.support_times) if rec else 0,
    }

    for key, name in STREAM_KEYS:
        stream = rec.get(key) if rec else None
        row[f"{name}件数"] = len(stream) if stream else 0

    row["サーフェス視線_画面内件数"] = int(gaze["サーフェス内"].sum()) if len(gaze) else 0

    notes = session.notes + (rec.notes if rec else [])
    row["注記"] = " / ".join(notes) if notes else "問題なし"

    return row


# ============================================================
# 入口
# ============================================================

def main() -> int:
    root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(
        description="XDF と課題データを学習用の表へ一括変換する",
    )
    parser.add_argument("--task-data", default=str(root / "task_data"))
    parser.add_argument("--out", default=str(root / "dataset"))
    parser.add_argument("--window", type=float, default=DEFAULT_WINDOW_S)
    parser.add_argument("--hop", type=float, default=DEFAULT_HOP_S)
    parser.add_argument("--horizon", type=float, default=DEFAULT_HORIZON_S)
    parser.add_argument(
        "--no-gaze-samples",
        action="store_true",
        help="gaze_regions.csv を書かない（数十万行になるため）",
    )
    args = parser.parse_args()

    task_data = Path(args.task_data)
    out_dir = Path(args.out)

    sessions = task_io.discover(task_data)

    if not sessions:
        print(f"セッションが見つかりません: {task_data}")
        return 1

    print(f"対象: {len(sessions)} セッション（{task_data}）")
    print()

    coverage: list[dict] = []
    fits: list[dict] = []
    gaze_all: list[pd.DataFrame] = []
    step_rows: list[dict] = []
    window_rows: list[dict] = []

    for session in sessions:
        print(f"--- {session.label}（{session.mode or '条件不明'}）")

        if session.xdf is None:
            print("    XDF が無いので飛ばします")
            coverage.append(coverage_row(session, None, pd.DataFrame()))
            continue

        try:
            rec = xdf_io.load(session.xdf)
        except Exception as e:
            print(f"    XDF を読めません: {e}")
            session.notes.append(f"XDF読み込み失敗: {e}")
            coverage.append(coverage_row(session, None, pd.DataFrame()))
            continue

        layout = regions.Layout.from_frame(session.layout)
        gaze, fit_rows, transform = build_gaze_table(session, rec, layout)

        for r in fit_rows:
            fits.append(
                {"被験者ID": session.subject, "問題ID": session.problem,
                 "採用": r["変換"] == transform.name, **r}
            )

        verdict = classify(session, rec, gaze)

        if len(gaze):
            print(f"    視線 {len(gaze)} 件、採用した変換: {transform.name}")
            gaze_all.append(
                gaze.assign(被験者ID=session.subject, 問題ID=session.problem)
            )
        elif verdict != "中断":
            print("    サーフェス視線が無いため、視線の特徴量は空になります")

        coverage.append(coverage_row(session, rec, gaze))

        if verdict == "中断":
            print("    途中で止めた記録なので、特徴量は作りません")
            continue

        if session.events is None:
            print("    events.csv が無いため、特徴量は作れません")
            continue

        s_rows = build_step_rows(session, rec, gaze)
        w_rows = build_window_rows(
            session, rec, gaze, args.window, args.hop, args.horizon
        )

        step_rows += s_rows
        window_rows += w_rows

        print(f"    設問単位 {len(s_rows)} 行 / 窓単位 {len(w_rows)} 行")

    # ---- 書き出し
    out_dir.mkdir(parents=True, exist_ok=True)

    def write(name: str, frame: pd.DataFrame) -> None:
        path = out_dir / name
        frame.to_csv(path, index=False, encoding=ENC)
        print(f"  {name:22} {len(frame):7} 行")

    print()
    print(f"書き出し先: {out_dir}")

    write("coverage.csv", pd.DataFrame(coverage))
    write("surface_fit.csv", pd.DataFrame(fits))

    step_df = pd.DataFrame(step_rows)
    window_df = pd.DataFrame(window_rows)

    write("features_step.csv", step_df)
    write("features_window.csv", window_df)

    if args.no_gaze_samples:
        print("  gaze_regions.csv       （--no-gaze-samples のため書きません）")
    else:
        gaze_df = (
            pd.concat(gaze_all, ignore_index=True) if gaze_all else pd.DataFrame()
        )
        write("gaze_regions.csv", gaze_df)

    # ---- 最後に、学習に使えるかどうかを言う
    print()
    print("=" * 60)

    positives = int(window_df["介入要請あり"].sum()) if len(window_df) else 0

    if positives == 0:
        print("警告: 介入要請の正例が 0 件です。")
        print("      ヒントボタンが押されたセッションが無いため、")
        print("      介入タイミングの学習にはまだ使えません。")
        print("      特徴量と対応づけの確認までは、このまま進められます。")
    else:
        rate = positives / len(window_df) * 100
        print(f"介入要請の正例: {positives} / {len(window_df)} 行（{rate:.2f}%）")

    if len(step_df):
        known = step_df[step_df["理解度正誤"] != ""]
        correct = int((known["理解度正誤"] == "正解").sum())
        print(f"理解度テスト: {correct} / {len(known)} 問 正解（補助ラベル）")

    # 判定の内訳。「中断」は途中で止めた回なので、欠けの警告とは分けて出す
    verdicts = pd.DataFrame(coverage)["判定"].value_counts()
    print()
    print("セッションの判定:")

    for name, count in verdicts.items():
        print(f"  {name}: {count} 件")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
