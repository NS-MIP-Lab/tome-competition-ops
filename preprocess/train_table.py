# -*- coding: utf-8 -*-
"""features_window.csv を、そのまま学習に渡せる表へ整える。

features_window.csv は「判断材料を全部載せる」表なので、文字列の列が混ざり、
絶対値のままの列があり、課題の進行度も入っている。そのままモデルには渡せない。

ここでやるのは4つ。

  1. 文字列を落とすか数値へ直す
  2. 被験者ごとに標準化する（既定は課題の最初のN分を基準にする）
  3. 識別子・ラベル・マスク・特徴量を分けて、役割の表を出す
  4. 引数で列の構成を選べるようにする

**元の表は書き換えない。** train_window.csv を別に出す。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ------------------------------------------------------------
# 列の役割
# ------------------------------------------------------------

# 分割に必要なので残すが、特徴量ではない。GroupKFold の groups に 被験者ID を使う
ID_COLUMNS = ["被験者ID", "問題ID"]

LABEL_COLUMNS = [
    "介入要請あり",
    "介入要請までの秒数",
    "理解度正誤",
    "自己評価理解度",
]

MASK_COLUMNS = [
    "介入ラベル有効",
    "理解度ラベル有効",
    "自己評価ラベル有効",
    "脳波有効",
]

# 落とす列。
#   アルゴリズム・条件 … 問題ID と セッションで決まるので冗長
#   脳波_品質          … 脳波有効 に落としてある
#   窓終了秒・窓長秒    … 窓開始秒と窓長から決まる
DROP_COLUMNS = ["アルゴリズム", "条件", "脳波_品質", "窓終了秒", "窓長秒"]

# 課題の進行度。既定では外す。
#
# 押下は課題の終盤と特定の設問に偏るため、これを入れるとモデルが生体情報を
# 見ずに「終盤なら押される」と学習できてしまう。S03/pE では押下6回のうち
# 2回が最後の5%に入っていた。
PROGRESS_COLUMNS = ["設問", "窓開始秒"]

# 理解度正誤 の文字列を 0/1 へ
VERDICT_MAP = {"正解": 1.0, "不正解": 0.0}

# ベースラインがこの行数より少ないセッションは、セッション全体の統計に落とす
MIN_BASELINE_ROWS = 30


def _eeg_drop(mode: str) -> list[str]:
    """脳波のどの列を落とすか。

    脳波_θα比 と 脳波_前頭左右差α は絶対値から作るが比なのでスケールに
    寄らない。どの mode でも残す。
    """
    if mode == "both":
        return []

    from features import BANDS, EEG_CHANNELS

    if mode == "relative":
        return [f"脳波_{ch}_{b}" for ch in EEG_CHANNELS for b in BANDS]

    if mode == "absolute":
        return [f"脳波_{ch}_{b}相対" for ch in EEG_CHANNELS for b in BANDS]

    raise ValueError(f"未知の脳波列の指定: {mode}")


def _log_columns(df: pd.DataFrame, cols: list[str]) -> list[str]:
    """log1p を掛ける列。負の値を含まない列だけを対象にする。

    帯域パワー（µV²）や件数は右に強く裾を引くので、そのまま平均と標準偏差で
    正規化すると値が発散する。S03/pE を最初の3分で標準化したときの |z| の最大は

      そのまま     489.7        log1p のあと   64.4
      中央値/MAD   718.3        log1p のあと  233.3

    で、log1p → 平均/標準偏差 が最も収まった。中央値/MAD は MAD が0になる列
    （脳波_サンプル数 など基準区間でほぼ一定）が全行 NaN になるため使わない。

    脳波_前頭左右差α は対数比なので負を取る。対象から外れる。
    """
    keep = []

    for c in cols:
        values = df[c].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]

        if len(finite) and finite.min() >= 0.0:
            keep.append(c)

    return keep


def _standardize(
    df: pd.DataFrame,
    feature_cols: list[str],
    mode: str,
    baseline_s: float,
) -> tuple[pd.DataFrame, list[str]]:
    """被験者ごとに正規化する。log1p を掛けてから平均と標準偏差で z 化する。

    mode="baseline" は課題の最初の baseline_s 秒を基準にする。実運用でも
    同じことができる形にするため。mode="session" はセッション全体を使う。
    交差検証では被験者ごとに分けるのでどちらも漏れは起きないが、session は
    未来のデータを使うので実運用の形ではない。

    セッションは（被験者ID, 問題ID）で1つ。標準偏差が0の列はそのまま残す。
    """
    notes: list[str] = []

    if mode == "none" or not feature_cols:
        return df, notes

    out = df.copy()

    # 右の裾を畳んでから正規化する。掛ける列は全セッション共通にする
    # （セッションごとに変えると、同じ列が別のスケールになる）
    log_cols = _log_columns(df, feature_cols)
    out[log_cols] = np.log1p(out[log_cols])

    for (subject, problem), idx in df.groupby(ID_COLUMNS, sort=False).groups.items():
        block = out.loc[idx, feature_cols]
        basis = block
        label = "セッション全体"

        if mode == "baseline":
            within = df.loc[idx, "窓終了秒"] <= baseline_s
            basis = block[within.to_numpy()]

            if len(basis) < MIN_BASELINE_ROWS:
                notes.append(
                    f"{subject}/{problem}: ベースラインが {len(basis)} 行しか無いため"
                    "セッション全体で標準化"
                )
                basis = block
            else:
                label = f"最初の{baseline_s:.0f}秒"

        center = basis.mean()
        scale = basis.std(ddof=0).replace(0.0, np.nan)

        # 基準区間で値が動かない列は、そのままだと列ごと NaN になって消える。
        # セッション全体の標準偏差で代用し、それも0なら割らずに中心だけ引く
        flat = scale.isna()

        if flat.any():
            fallback = block.loc[:, flat].std(ddof=0).replace(0.0, np.nan)
            scale.loc[flat] = fallback.fillna(1.0)
            names = ", ".join(list(scale.index[flat])[:3])
            notes.append(
                f"{subject}/{problem}: 基準区間で動かない列 {int(flat.sum())} 個"
                f"（{names} …）はセッション全体の広がりで割った"
            )

        out.loc[idx, feature_cols] = ((block - center) / scale).to_numpy()
        out.loc[idx, "標準化の基準"] = label

    return out, notes


def build(
    window_df: pd.DataFrame,
    *,
    standardize: str = "baseline",
    baseline_s: float = 180.0,
    eeg: str = "relative",
    progress: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """学習用の表と、列の役割の表を作る。

    戻り値は (train_df, columns_df, notes)。
    """
    if not len(window_df):
        return pd.DataFrame(), pd.DataFrame(), []

    df = window_df.copy()

    # ---- ラベルを数値へ
    df["理解度正誤"] = df["理解度正誤"].map(VERDICT_MAP).astype(float)

    # ---- 進行度。設問は one-hot にしてから消す
    progress_cols: list[str] = []

    if progress:
        dummies = pd.get_dummies(df["設問"], prefix="設問").astype(int)
        df = pd.concat([df, dummies], axis=1)
        progress_cols = ["窓開始秒"] + list(dummies.columns)

    # ---- 落とす列を決める
    drop = set(DROP_COLUMNS) | set(_eeg_drop(eeg)) | {"設問"}

    if not progress:
        drop |= set(PROGRESS_COLUMNS)

    # 窓終了秒は標準化の区切りに要るので、最後に落とす
    keep_until_end = {"窓終了秒"}

    # ---- 特徴量の列
    reserved = set(ID_COLUMNS) | set(LABEL_COLUMNS) | set(MASK_COLUMNS)
    feature_cols = [
        c
        for c in df.columns
        if c not in reserved
        and c not in drop
        and c not in keep_until_end
        and c not in progress_cols
        and pd.api.types.is_numeric_dtype(df[c])
    ]

    # ---- 標準化。進行度と one-hot は素の値のまま使う
    #
    # 件数の列は整数なので、z 化した値を書き戻す前に float へ直しておく
    df[feature_cols] = df[feature_cols].astype(float)
    df["標準化の基準"] = "なし"
    df, notes = _standardize(df, feature_cols, standardize, baseline_s)

    # ---- 並べ直す
    ordered = (
        ID_COLUMNS
        + ["標準化の基準"]
        + progress_cols
        + LABEL_COLUMNS
        + MASK_COLUMNS
        + feature_cols
    )
    train_df = df[ordered]

    # ---- 役割の表
    def role(col: str) -> str:
        if col in ID_COLUMNS:
            return "識別子"
        if col == "標準化の基準":
            return "注記"
        if col in LABEL_COLUMNS:
            return "ラベル"
        if col in MASK_COLUMNS:
            return "マスク"
        if col in progress_cols:
            return "特徴量（進行度）"
        return "特徴量"

    columns_df = pd.DataFrame(
        {
            "列": ordered,
            "役割": [role(c) for c in ordered],
            "標準化": [
                "済" if (c in feature_cols and standardize != "none") else "—"
                for c in ordered
            ],
        }
    )

    return train_df, columns_df, notes
