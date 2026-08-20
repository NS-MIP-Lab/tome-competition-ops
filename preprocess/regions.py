# -*- coding: utf-8 -*-
"""サーフェス座標をウィンドウ座標へ直し、視線を領域とブロックへ割り当てる。

layout.csv の座標はウィンドウ座標（左上原点、実測で 1512×949）。
Pupil のサーフェス座標は左下原点の正規化座標。向きが違う。

S01/pA の実データで検証した結果は次のとおり。

  x は反転なし。視線 x の分布が二山になり、細い山（0.10〜0.25、全体の14%）が
  layout.csv のコード文字範囲（0.02〜0.22）と重なる。幅広い山（0.55〜0.95、86%）が
  設計書側（0.50〜1.00）と重なる。

  y は反転あり。コードの x 帯に絞って y を見ると、文字範囲に入る割合が
  反転あり 52.8% / 反転なし 32.3%。反転ありのとき最大の山が
  B3（10〜14行目の while 文）に乗る。

  x_window = x_surface
  y_window = 1 - y_surface

**縦のずれと伸びは残っている。** タグはベゼルに貼るためサーフェスは画面より広く、
実測の山は B3 の 0.557〜0.688 より広く 0.475〜0.775 に散る。
そのため変換は決め打ちにせず係数で持ち、セッションごとに
当てはまりを採点して surface_fit.csv に出す。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# 領域の名前
REGION_CODE = "コード"
REGION_DOC = "設計書"
REGION_OFF = "画面外"

# コード文字の横幅（S01/pA の実測。採点で使う帯）
CODE_TEXT_BAND = (0.05, 0.30)

# 座標の平滑化（Box の gaze_aoi_all_in_one_final.py と同じ既定値）
MEDIAN_WINDOW = 3
MIN_CONFIDENCE = 0.6


# ============================================================
# 変換
# ============================================================

@dataclass
class Transform:
    """サーフェス座標 → ウィンドウ座標の相似変換。

    反転を先に適用し、そのあと拡大縮小と平行移動をかける。
    既定値は S01/pA の実測にもとづく（x そのまま、y 反転）。
    """

    flip_x: bool = False
    flip_y: bool = True
    scale_x: float = 1.0
    scale_y: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    @property
    def name(self) -> str:
        return f"x{'反転' if self.flip_x else 'そのまま'}/y{'反転' if self.flip_y else 'そのまま'}"

    def apply(self, x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        if self.flip_x:
            x = 1.0 - x
        if self.flip_y:
            y = 1.0 - y

        return x * self.scale_x + self.offset_x, y * self.scale_y + self.offset_y


# 採点で比べる4通り
CANDIDATES = [
    Transform(flip_x=False, flip_y=True),
    Transform(flip_x=False, flip_y=False),
    Transform(flip_x=True, flip_y=True),
    Transform(flip_x=True, flip_y=False),
]


# ============================================================
# layout.csv の読み取り
# ============================================================

@dataclass
class Layout:
    """1セッションのコード領域とブロック境界（すべて正規化座標）。"""

    code_left: float
    code_right: float
    code_top: float
    code_bottom: float
    window_w: float
    window_h: float
    blocks: list[dict]      # ブロックID, ラベル, 開始行, 終了行, 上, 下, 文字上, 文字下

    @classmethod
    def from_frame(cls, df: pd.DataFrame | None) -> "Layout | None":
        if df is None or not len(df):
            return None

        first = df.iloc[0]
        window_h = float(first["ウィンドウ高さ"])
        window_w = float(first["ウィンドウ幅"])

        blocks = []

        for _, r in df.iterrows():
            blocks.append(
                {
                    "ブロックID": str(r["ブロックID"]),
                    "ラベル": str(r["ラベル"]),
                    "開始行": int(r["開始行"]),
                    "終了行": int(r["終了行"]),
                    "上": float(r["判定領域_上_正規化"]),
                    "下": float(r["判定領域_下_正規化"]),
                    # 文字範囲は px でしか出ていないので正規化する
                    "文字上": float(r["文字範囲_上px"]) / window_h,
                    "文字下": float(r["文字範囲_下px"]) / window_h,
                }
            )

        return cls(
            code_left=float(first["判定領域_左_正規化"]),
            code_right=float(first["判定領域_右_正規化"]),
            code_top=min(b["上"] for b in blocks),
            code_bottom=max(b["下"] for b in blocks),
            window_w=window_w,
            window_h=window_h,
            blocks=blocks,
        )

    def block_ids(self) -> list[str]:
        return [b["ブロックID"] for b in self.blocks]


# ============================================================
# 当てはまりの採点
# ============================================================

def score_fit(
    x_surface: np.ndarray,
    y_surface: np.ndarray,
    layout: Layout,
    transform: Transform,
    band: tuple[float, float] = CODE_TEXT_BAND,
) -> dict:
    """変換の当てはまりを採点する。

    コードの文字が並ぶ細い x 帯に絞り、y が文字範囲に入る割合を見る。
    コードは行と空行が交互に並ぶので、正しい変換なら文字範囲に集まる。
    """
    x, y = transform.apply(x_surface, y_surface)

    in_band = (x >= band[0]) & (x <= band[1])
    n_band = int(in_band.sum())

    in_code_area = (x >= layout.code_left) & (x <= layout.code_right)
    n_code_area = int(in_code_area.sum())

    def hit_rate(mask: np.ndarray) -> float:
        if not mask.any():
            return float("nan")

        yy = y[mask]
        hit = np.zeros(len(yy), dtype=bool)

        for b in layout.blocks:
            hit |= (yy >= b["文字上"]) & (yy <= b["文字下"])

        return float(hit.mean() * 100.0)

    return {
        "変換": transform.name,
        "x反転": transform.flip_x,
        "y反転": transform.flip_y,
        "コード帯サンプル数": n_band,
        "文字範囲一致率_コード帯": round(hit_rate(in_band), 1),
        "コード領域サンプル数": n_code_area,
        "文字範囲一致率_コード領域": round(hit_rate(in_code_area), 1),
    }


def best_transform(
    x_surface: np.ndarray,
    y_surface: np.ndarray,
    layout: Layout,
) -> tuple[Transform, list[dict]]:
    """4通りを採点し、一致率が最も高いものを返す。

    採点できない（視線が無い、layout が無い）ときは既定の変換を返す。
    """
    rows = [score_fit(x_surface, y_surface, layout, t) for t in CANDIDATES]

    scored = [
        (r["文字範囲一致率_コード帯"], t, r)
        for r, t in zip(rows, CANDIDATES)
        if r["コード帯サンプル数"] > 0 and np.isfinite(r["文字範囲一致率_コード帯"])
    ]

    if not scored:
        return CANDIDATES[0], rows

    scored.sort(key=lambda s: s[0], reverse=True)
    return scored[0][1], rows


# ============================================================
# 平滑化
# ============================================================

def median_filter(values: np.ndarray, window: int = MEDIAN_WINDOW) -> np.ndarray:
    """奇数長の中位数フィルタ。端は縮めて処理する。

    視線は1サンプルだけ飛ぶことがあり、そのままブロック判定に通すと
    ありえない往復が数えられてしまう。
    """
    values = np.asarray(values, dtype=float)

    if window <= 1 or len(values) < window:
        return values

    if window % 2 == 0:
        window += 1

    half = window // 2
    padded = np.pad(values, half, mode="edge")
    strided = np.lib.stride_tricks.sliding_window_view(padded, window)

    return np.median(strided, axis=1)


# ============================================================
# 領域とブロックの割り当て
# ============================================================

def assign(
    x_win: np.ndarray,
    y_win: np.ndarray,
    on_surface: np.ndarray,
    layout: Layout | None,
) -> tuple[np.ndarray, np.ndarray]:
    """ウィンドウ座標から、領域名とブロックIDを決める。

    コード領域の外（画面右半分）は設計書側とみなす。
    そこで何を見ていたかは、その時刻に表示していた設問で表す（呼び出し側で付ける）。
    """
    n = len(x_win)
    region = np.full(n, REGION_OFF, dtype=object)
    block = np.full(n, "", dtype=object)

    on = np.asarray(on_surface, dtype=bool)
    inside = on & np.isfinite(x_win) & np.isfinite(y_win)
    inside &= (x_win >= 0.0) & (x_win <= 1.0) & (y_win >= 0.0) & (y_win <= 1.0)

    if layout is None:
        region[inside] = REGION_DOC
        return region, block

    in_code_x = (x_win >= layout.code_left) & (x_win <= layout.code_right)
    in_code_y = (y_win >= layout.code_top) & (y_win <= layout.code_bottom)

    code = inside & in_code_x & in_code_y
    doc = inside & ~code

    region[code] = REGION_CODE
    region[doc] = REGION_DOC

    # 判定領域は隙間なく縦に並んでいるので、上から順に当てれば漏れない
    for b in layout.blocks:
        hit = code & (y_win >= b["上"]) & (y_win < b["下"])
        block[hit] = b["ブロックID"]

    # 最下端はちょうど境界に乗ることがある
    last = layout.blocks[-1]
    edge = code & (block == "") & (y_win >= last["上"])
    block[edge] = last["ブロックID"]

    return region, block
