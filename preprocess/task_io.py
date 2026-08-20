# -*- coding: utf-8 -*-
"""課題ページが書き出したファイルの読み込みと、XDF との突き合わせ。

task_data/<被験者ID>/<問題ID>/ に、次の5種類が並ぶ。

    design_<問題>_<条件>_<被験者>_<時刻>.xdf            LabRecorder が付ける名前
    design_<問題>_<条件>_<被験者>_<時刻>.json           課題ページの書き出し（正本）
    design_..._answers.csv                             回答（人が採点する用）
    design_..._events.csv                              イベント（機械学習用）
    design_..._layout.csv                              コードブロックの座標

XDF は /start の時刻、JSON 以下は /save の時刻で名前が付くため、
**時刻印は一致しない**。JSON の中の「XDFファイル」で結びつける。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ENC = "utf-8-sig"

# events.csv の 種別
KIND_SESSION = "セッション"
KIND_STEP = "設問滞在"
KIND_HINT = "ヒント要請"
KIND_QUIZ = "理解度テスト"


# ============================================================
# 1セッションぶん
# ============================================================

@dataclass
class Session:
    subject: str
    problem: str
    xdf: Path | None = None
    json_path: Path | None = None
    meta: dict = field(default_factory=dict)
    events: pd.DataFrame | None = None
    layout: pd.DataFrame | None = None
    answers: pd.DataFrame | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.subject}/{self.problem}"

    @property
    def mode(self) -> str:
        """学習用 / 検証用。events.csv の条件、無ければファイル名から。"""
        if self.events is not None and len(self.events):
            return str(self.events.iloc[0].get("条件", ""))

        if self.xdf:
            if "_learning_" in self.xdf.name:
                return "学習用"
            if "_test_" in self.xdf.name:
                return "検証用"

        return ""

    @property
    def algorithm(self) -> str:
        if self.events is not None and len(self.events):
            return str(self.events.iloc[0].get("アルゴリズム", ""))
        return str(self.meta.get("アルゴリズム", ""))

    def session_row(self) -> pd.Series | None:
        """課題全体の1行。開始0秒・終了何秒かが入っている。"""
        if self.events is None:
            return None

        rows = self.events[self.events["種別"] == KIND_SESSION]
        return rows.iloc[0] if len(rows) else None

    def duration_s(self) -> float | None:
        row = self.session_row()

        if row is None:
            return None

        return float(row["終了経過ミリ秒"]) / 1000.0

    def steps(self) -> pd.DataFrame:
        """設問滞在。1行が1回の訪問。同じ設問が複数回出る。"""
        if self.events is None:
            return pd.DataFrame()

        return self.events[self.events["種別"] == KIND_STEP].copy()

    def quizzes(self) -> pd.DataFrame:
        if self.events is None:
            return pd.DataFrame()

        return self.events[self.events["種別"] == KIND_QUIZ].copy()

    def hints(self) -> pd.DataFrame:
        if self.events is None:
            return pd.DataFrame()

        return self.events[self.events["種別"] == KIND_HINT].copy()

    def confidence(self) -> int | None:
        """Q6 の自己評価の理解度（1〜5）。セッションに1つだけ。

        JSON の「回答」の中で、キーが .confidence で終わる項目に入っている。
        JSON が無い場合は answers.csv の項目名で拾う。
        """
        for row in self.meta.get("回答", []):
            key = str(row.get("キー", ""))

            if key.endswith(".confidence"):
                try:
                    return int(str(row.get("回答", "")).strip())
                except (TypeError, ValueError):
                    return None

        if self.answers is not None:
            hit = self.answers[
                self.answers["項目"].astype(str).str.contains("理解度", na=False)
            ]

            for value in hit["回答"]:
                try:
                    return int(str(value).strip())
                except (TypeError, ValueError):
                    continue

        return None

    def free_text(self) -> str:
        """Q6 の自由記述（迷った箇所）。ラベルではなく、人が読む用。"""
        for row in self.meta.get("回答", []):
            if str(row.get("キー", "")).endswith(".unsure"):
                return str(row.get("回答", ""))

        return ""


# ============================================================
# 読み込み
# ============================================================

def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None

    try:
        return pd.read_csv(path, encoding=ENC)
    except Exception:
        return pd.read_csv(path, encoding="utf-8")


def _read_json(path: Path) -> dict:
    with open(path, encoding=ENC) as f:
        return json.load(f)


def quiz_result(supplement: str) -> tuple[str, str]:
    """events.csv の補足欄から、問題IDと正誤を取り出す。

    形は「PAQ1-H1／選択3／正解3／正解」。区切りは全角スラッシュ。
    """
    parts = [p.strip() for p in str(supplement).split("／")]

    if len(parts) < 4:
        return "", ""

    return parts[0], parts[3]


# ============================================================
# セッションを探す
# ============================================================

def discover(task_data: Path) -> list[Session]:
    """task_data 以下を走査して、セッションの一覧を作る。

    XDF が無い（課題データだけ）場合も、XDF だけの場合も拾う。
    どちらが欠けているかは notes に残し、網羅状況の表に出す。
    """
    task_data = Path(task_data)
    sessions: list[Session] = []

    if not task_data.exists():
        return sessions

    for problem_dir in sorted(p for p in task_data.glob("*/*") if p.is_dir()):
        subject = problem_dir.parent.name
        problem = problem_dir.name

        xdfs = sorted(problem_dir.glob("*.xdf"))
        jsons = sorted(problem_dir.glob("*.json"))

        used_xdf: set[Path] = set()

        # ---- JSON を軸に組む
        for json_path in jsons:
            session = Session(subject=subject, problem=problem, json_path=json_path)

            try:
                session.meta = _read_json(json_path)
            except Exception as e:
                session.notes.append(f"JSONを読めない: {e}")
                sessions.append(session)
                continue

            stem = json_path.stem
            session.events = _read_csv(problem_dir / f"{stem}_events.csv")
            session.layout = _read_csv(problem_dir / f"{stem}_layout.csv")
            session.answers = _read_csv(problem_dir / f"{stem}_answers.csv")

            for name, table in (
                ("events.csv", session.events),
                ("layout.csv", session.layout),
                ("answers.csv", session.answers),
            ):
                if table is None:
                    session.notes.append(f"{name} が無い")

            # ---- XDF を結びつける。JSON の中のファイル名で照合する
            recorded = str(session.meta.get("XDFファイル", ""))
            wanted = Path(recorded.replace("\\", "/")).name if recorded else ""

            match = next((x for x in xdfs if x.name == wanted), None)

            if match is None and len(xdfs) == 1:
                match = xdfs[0]
                session.notes.append("XDFはファイル名では照合できず、同フォルダの1件を使用")
            elif match is None and xdfs:
                session.notes.append(
                    f"XDFを特定できない（候補{len(xdfs)}件）: {wanted or '記録なし'}"
                )

            if match is not None:
                session.xdf = match
                used_xdf.add(match)
            else:
                session.notes.append("XDFが無い")

            sessions.append(session)

        # ---- JSON に結びつかなかった XDF は単独で拾う
        for xdf in xdfs:
            if xdf in used_xdf:
                continue

            sessions.append(
                Session(
                    subject=subject,
                    problem=problem,
                    xdf=xdf,
                    notes=["課題データ（json/csv）が無い"],
                )
            )

    return sessions
