# -*- coding: utf-8 -*-
"""PDF용 차트 (matplotlib).

**화면은 Plotly, 인쇄는 matplotlib.**
Plotly를 이미지로 내보내려면 kaleido가 필요한데 환경을 심하게 타서
배포하면 잘 깨진다. matplotlib은 순수 파이썬으로 PNG를 만들어 안정적이다.

한글 폰트를 지정하지 않으면 네모(두부)가 나온다. fonts/NotoSansKR-Regular.ttf 사용.
"""
from __future__ import annotations

import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                      # 화면 없는 서버에서도 그릴 수 있게
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

from core import config as C

FONT_DIR = C.ROOT / "fonts"
_registered = False


def use_korean_font() -> str:
    """한글 폰트를 matplotlib에 등록한다. 없으면 시스템 폰트로 물러선다."""
    global _registered
    name = "Noto Sans KR"
    if not _registered:
        for f in ("NotoSansKR-Regular.ttf", "NotoSansKR-Bold.ttf"):
            p = FONT_DIR / f
            if p.exists():
                font_manager.fontManager.addfont(str(p))
        _registered = True
    have = {f.name for f in font_manager.fontManager.ttflist}
    if name not in have:
        name = "Malgun Gothic" if "Malgun Gothic" in have else "DejaVu Sans"
    plt.rcParams["font.family"] = name
    plt.rcParams["axes.unicode_minus"] = False   # 마이너스가 깨지는 것 방지
    return name


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def funnel_png(f) -> bytes:
    use_korean_font()
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    colors = [C.COLORS["block"] if b else C.BRAND["primary"] for b in f.is_bottleneck]
    y = range(len(f))
    ax.barh(list(y), f.n, color=colors, height=0.62)
    ax.set_yticks(list(y))
    ax.set_yticklabels(f.label, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, f.n.max() * 1.30)
    for i, r in enumerate(f.itertuples()):
        txt = f"{r.n:,}"
        if r.step_rate == r.step_rate:
            txt += f"  ({r.step_rate*100:.1f}%)"
        ax.text(r.n * 1.02, i, txt, va="center", fontsize=9,
                color=C.BRAND["muted"])
    for s in ("top", "right", "bottom"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(C.BRAND["line"])
    ax.set_xticks([])
    return _png(fig)


def device_png(g) -> bytes:
    """분해 축 전환율 비교. g에 "사유" 컬럼이 있으면(core.metrics.trust_check()
    를 이미 돌려 채워 둔 값 — 대시보드 분해 표와 같은 재사용) 그 칸은 막대와
    수치 없이 사유만 적는다. 값을 회색으로도 보여주지 않는다."""
    use_korean_font()
    has_reason = "사유" in g.columns
    ok = (g[g["사유"].isna()] if has_reason else g).sort_values("전환율")
    hidden = g[g["사유"].notna()] if has_reason else g.iloc[0:0]
    order = pd.concat([ok, hidden]) if len(hidden) else ok

    fig, ax = plt.subplots(figsize=(7.2, 0.62 * len(order) + 1.0))
    is_hidden = [has_reason and pd.notna(r["사유"]) for _, r in order.iterrows()]
    colors = [
        C.BRAND["line"] if h else
        (C.COLORS["block"] if v == ok["전환율"].min() else C.BRAND["primary"])
        for h, v in zip(is_hidden, order["전환율"])]
    widths = [0 if h else v * 100 for h, v in zip(is_hidden, order["전환율"])]
    y = range(len(order))
    ax.barh(list(y), widths, color=colors, height=0.55)
    ax.set_yticks(list(y))
    ax.set_yticklabels(order[order.columns[0]], fontsize=10)
    xmax = (ok["전환율"].max() if len(ok) else order["전환율"].max()) * 148
    ax.set_xlim(0, xmax)
    for i, (h, r) in enumerate(zip(is_hidden, order.itertuples())):
        if h:
            ax.text(xmax * 0.015, i, f"표본 부족 — {r.사유}", va="center",
                    fontsize=9, color=C.BRAND["muted"])
        else:
            ax.text(r.전환율 * 101, i, f"{r.전환율*100:.1f}%   ({r.도달:,}명)",
                    va="center", fontsize=9, color=C.BRAND["muted"])
    for s in ("top", "right", "bottom"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(C.BRAND["line"])
    ax.set_xticks([])
    return _png(fig)


def trend_png(m, col: str, title: str = "") -> bytes:
    use_korean_font()
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    ax.plot(list(m.index), m[col], marker="o", markersize=4,
            color=C.BRAND["primary"], linewidth=2)
    ax.set_title(title, fontsize=10, color=C.BRAND["ink"], loc="left", pad=8)
    ax.grid(axis="y", color=C.BRAND["line"], linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(C.BRAND["line"])
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.yticks(fontsize=8)
    return _png(fig)


def experiments_png(res) -> bytes:
    """실험별 효과와 신뢰구간. 무효 실험은 값 대신 사유를 적는다."""
    use_korean_font()
    usable = [r for r in res if r["verdict"] != "무효"]
    fig, ax = plt.subplots(figsize=(7.2, 0.72 * len(res) + 1.0))
    labels, ys = [], []
    for i, r in enumerate(reversed(res)):
        labels.append(f"{r['id']}")
        ys.append(i)
        if r["verdict"] == "무효":
            ax.text(0, i, "  SRM으로 무효 — 해석 불가", va="center",
                    fontsize=9, color=C.COLORS["block"])
            continue
        lo, hi, d = r["lo"] * 100, r["hi"] * 100, r["diff"] * 100
        col = C.COLORS.get(r["color"], C.BRAND["primary"])
        ax.plot([lo, hi], [i, i], color=col, linewidth=3.2, solid_capstyle="round")
        ax.plot([d], [i], "o", color=col, markersize=7,
                markeredgecolor="white", markeredgewidth=1.4)
        ax.text(hi, i + 0.28, f"{d:+.2f}%p", fontsize=8,
                color=C.BRAND["muted"], va="bottom")
    ax.axvline(0, color=C.BRAND["line"], linewidth=1.2)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("대조군 대비 차이 (%p)", fontsize=9, color=C.BRAND["muted"])
    ax.grid(axis="x", color=C.BRAND["line"], linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C.BRAND["line"])
    plt.xticks(fontsize=8)
    return _png(fig)
