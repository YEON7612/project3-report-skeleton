# -*- coding: utf-8 -*-
"""제안서에 들어갈 그림만 만든다. core/metrics.py의 topic_evidence()가
돌려준 표를 그대로 받아 인라인 SVG 문자열로 그린다 — 데이터를 새로
조회하지 않는다(이 파일은 그림만 만든다).

외부 CDN·이미지 파일·폰트 링크를 쓰지 않는다. 함수 하나가 완결된 SVG
문자열 하나를 돌려주고, 그 문자열을 HTML에 그대로 박으면 된다
(report/proposal.py의 _CSS처럼 <style> 안에 두지 않고 본문에 직접 넣는다).

색은 최대 3개 — config.COLORS에서 그대로 가져온다. 의미는 이 앱 전체에서
고정이다("도메인이 바뀌어도 바꾸지 않는다" — config.py 주석):
    강조1(ACCENT) = COLORS["block"]  — 병목·최저(문제가 있는 쪽)
    기본1(BASE)   = COLORS["ok"]     — 병목이 아닌 나머지·최고(정상/우수)
    회색1(GRAY)   = COLORS["none"]   — 비교 불가·표본 부족·눈금/보조선
텍스트 잉크색(INK)만 config.COLORS에 없는 값을 쓴다 — report/proposal.py의
_CSS가 쓰는 --ink(#0f172a)와 같은 값이다(이 문서가 밝은 배경이라 그
문서와 같은 잉크색을 그대로 맞췄다. 데이터를 나타내는 색이 아니라 글자
색이라 3색 예산에 넣지 않는다).
"""
from __future__ import annotations

import math

import pandas as pd

from core import config as C

ACCENT = C.COLORS["block"]
BASE = C.COLORS["ok"]
GRAY = C.COLORS["none"]
INK = "#0f172a"  # report/proposal.py _CSS의 --ink와 같은 값. 데이터 색이 아니다.

_FONT = "system-ui,-apple-system,BlinkMacSystemFont,'Malgun Gothic','Apple SD Gothic Neo',sans-serif"

# 이 파일에 쓰이는 고정 문구는 전부 core.config.PROPOSAL_WORDS["charts"]에
# 있다 — 여기서 문자열을 직접 박지 않는다.
_W = C.PROPOSAL_WORDS["charts"]


def _esc(v) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _svg_open(width: int, height: int) -> str:
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg" '
            f'font-family="{_FONT}" font-size="12">')


def _caption(y: float, grain: str) -> str:
    return (f'<text x="0" y="{y:.1f}" font-size="11" fill="{GRAY}">'
            f'{_esc(_W["grain_prefix"])}{_esc(grain)}</text>')


def _empty_svg(title: str, grain: str) -> str:
    """그릴 값이 아예 없을 때 — 0으로 그리지 않고 없다는 사실만 보여준다."""
    width, height = 640, 92
    return "".join([
        _svg_open(width, height),
        f'<text x="0" y="28" font-size="13" fill="{INK}">{_esc(title)}</text>',
        f'<text x="0" y="50" font-size="12" fill="{GRAY}">{_esc(_W["empty_chart"])}</text>',
        _caption(76, grain),
        "</svg>",
    ])


def _nice_ticks(vmin: float, vmax: float, count: int = 4) -> list[float]:
    """vmin~vmax 구간에 보기 좋은 간격의 눈금 값을 만든다. 실제 데이터
    범위에서 계산한다 — 예시 숫자를 넣지 않는다."""
    if vmax <= vmin:
        return [vmin]
    raw_step = (vmax - vmin) / count
    magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step > 0 else 1
    step = magnitude
    for m in (1, 2, 2.5, 5, 10):
        step = m * magnitude
        if step >= raw_step:
            break
    start = math.floor(vmin / step) * step
    ticks, v = [], start
    while v <= vmax + step * 1e-6:
        if v >= vmin - step * 1e-6:
            ticks.append(round(v, 6))
        v += step
    return ticks or [vmin, vmax]


# ── ① 현황 — 퍼널 단계별 도달 ────────────────────────────────────
def funnel_svg(f: pd.DataFrame | None, grain: str, unit: str = "명") -> str:
    """단계별 도달 가로 막대. 병목 구간(is_bottleneck)만 강조색, 나머지는
    기본색. f는 topic_evidence(t, topic)["현황"]["표"]를 그대로 받는다
    (funnel()/retention_funnel() 반환 형태: step·label·n·step_rate·
    cum_rate·drop·is_bottleneck). n이 없는 행은 그리지 않는다.
    """
    if f is None or not len(f):
        return _empty_svg(_W["empty_titles"]["현황"], grain)
    rows = f[f["n"].notna()].reset_index(drop=True)
    if not len(rows):
        return _empty_svg(_W["empty_titles"]["현황"], grain)

    n_rows = len(rows)
    left, right, top, row_h, bar_h, axis_h = 130, 90, 12, 40, 24, 26
    width = 640
    plot_w = width - left - right
    height = top + n_rows * row_h + axis_h + 24 + 8

    max_n = float(rows["n"].max())
    ticks = _nice_ticks(0, max_n * 1.15)
    top_tick = ticks[-1] if ticks[-1] > 0 else 1

    def x(v: float) -> float:
        return left + (v / top_tick) * plot_w

    axis_y = top + n_rows * row_h + 6
    parts = [_svg_open(width, height)]
    for tv in ticks:
        gx = x(tv)
        parts.append(f'<line x1="{gx:.1f}" y1="{top-4}" x2="{gx:.1f}" '
                    f'y2="{axis_y:.1f}" stroke="{GRAY}" stroke-width="1" '
                    f'opacity="0.25"/>')
        parts.append(f'<text x="{gx:.1f}" y="{axis_y+14:.1f}" font-size="10" '
                    f'fill="{GRAY}" text-anchor="middle">{tv:,.0f}</text>')

    for i, r in rows.iterrows():
        y = top + i * row_h
        bar_y = y + (row_h - bar_h) / 2
        bw = (float(r["n"]) / top_tick) * plot_w
        color = ACCENT if bool(r["is_bottleneck"]) else BASE
        parts.append(f'<rect x="{left:.1f}" y="{bar_y:.1f}" width="{bw:.1f}" '
                    f'height="{bar_h}" fill="{color}" rx="3"/>')
        parts.append(f'<text x="{left-10:.1f}" y="{bar_y+bar_h/2+4:.1f}" '
                    f'font-size="12" fill="{INK}" text-anchor="end">'
                    f'{_esc(r["label"])}</text>')
        label = f'{int(r["n"]):,}{unit}'
        if pd.notna(r["step_rate"]):
            label += f'  ({float(r["step_rate"])*100:.1f}%)'
        parts.append(f'<text x="{left+bw+8:.1f}" y="{bar_y+bar_h/2+4:.1f}" '
                    f'font-size="11" fill="{GRAY}">{_esc(label)}</text>')

    parts.append(_caption(axis_h + top + n_rows * row_h + 20, grain))
    parts.append("</svg>")
    return "".join(parts)


# ── ② 원인 — 분해 축 전환율 ──────────────────────────────────────
def gap_svg(g: pd.DataFrame | None, grain: str) -> str:
    """축별 전환율 가로 막대. 최고·최저 칸만 색(최저=강조색, 최고=기본색),
    나머지는 회색. g는 topic_evidence(t, topic)["원인"]["표"]를 그대로
    받는다(funnel_by() 결과 + "신뢰"·"표시" 열). "신뢰" 열이 비어 있지
    않은(trust_check()에 걸린) 칸은 막대를 그리지 않고 사유만 적는다 —
    0으로 그리지 않는다.
    """
    if g is None or not len(g):
        return _empty_svg(_W["empty_titles"]["원인"], grain)
    rows = g.reset_index(drop=True)
    dim_col = rows.columns[0]

    n_rows = len(rows)
    left, right, top, row_h, bar_h, axis_h = 100, 150, 12, 40, 24, 26
    width = 640
    plot_w = width - left - right
    height = top + n_rows * row_h + axis_h + 24 + 8

    ticks = [0, 25, 50, 75, 100]  # 전환율은 항상 0~100%라 고정 눈금을 쓴다.

    def x(pct: float) -> float:
        return left + (pct / 100) * plot_w

    axis_y = top + n_rows * row_h + 6
    parts = [_svg_open(width, height)]
    for tv in ticks:
        gx = x(tv)
        parts.append(f'<line x1="{gx:.1f}" y1="{top-4}" x2="{gx:.1f}" '
                    f'y2="{axis_y:.1f}" stroke="{GRAY}" stroke-width="1" '
                    f'opacity="0.25"/>')
        parts.append(f'<text x="{gx:.1f}" y="{axis_y+14:.1f}" font-size="10" '
                    f'fill="{GRAY}" text-anchor="middle">{tv:.0f}%</text>')

    for i, r in rows.iterrows():
        y = top + i * row_h
        bar_y = y + (row_h - bar_h) / 2
        parts.append(f'<text x="{left-10:.1f}" y="{bar_y+bar_h/2+4:.1f}" '
                    f'font-size="12" fill="{INK}" text-anchor="end">'
                    f'{_esc(r[dim_col])}</text>')
        untrusted = str(r.get("신뢰", "") or "").strip()
        if untrusted:
            parts.append(f'<text x="{left+8:.1f}" y="{bar_y+bar_h/2+4:.1f}" '
                        f'font-size="11" fill="{GRAY}">{_esc(_W["low_sample_prefix"])}'
                        f'{_esc(untrusted)}</text>')
            continue
        pct = float(r["전환율"]) * 100
        bw = (pct / 100) * plot_w
        표시 = r.get("표시", "")
        color = ACCENT if 표시 == "최저" else (BASE if 표시 == "최고" else GRAY)
        parts.append(f'<rect x="{left:.1f}" y="{bar_y:.1f}" width="{bw:.1f}" '
                    f'height="{bar_h}" fill="{color}" rx="3"/>')
        parts.append(f'<text x="{left+bw+8:.1f}" y="{bar_y+bar_h/2+4:.1f}" '
                    f'font-size="11" fill="{GRAY}">{pct:.1f}% '
                    f'({int(r["도달"]):,}명)</text>')

    parts.append(_caption(axis_h + top + n_rows * row_h + 20, grain))
    parts.append("</svg>")
    return "".join(parts)


# ── ③ 추세 — 최근 월별 꺾은선 ────────────────────────────────────
def trend_svg(s: pd.Series | None, grain: str, unit: str = "",
              threshold: float | None = None) -> str:
    """최근 개월 수만큼의 꺾은선. s는 topic_evidence(t, topic)["추세"]["표"]
    를 그대로 받는다(monthly() 시계열, 인덱스가 "YYYY-MM"). threshold를
    넘기면(호출하는 쪽이 정한다 — 여기서 새로 찾지 않는다) 회색 점선
    기준선을 같이 그린다. 값이 없으면(None이거나 전부 NaN) 그리지 않는다.
    """
    if s is None or not len(s):
        return _empty_svg(_W["empty_titles"]["추세"], grain)
    s = s.dropna()
    if not len(s):
        return _empty_svg(_W["empty_titles"]["추세"], grain)

    n = len(s)
    left, right, top, plot_h = 60, 20, 16, 160
    bottom_axis_gap, x_label_h = 10, 46
    width = 640
    plot_w = width - left - right
    height = top + plot_h + bottom_axis_gap + x_label_h + 24

    values = list(s.astype(float).values)
    if threshold is not None:
        values.append(float(threshold))
    vmin, vmax = min(values), max(values)
    if vmin == vmax:
        vmin, vmax = vmin - 1, vmax + 1
    pad = (vmax - vmin) * 0.12
    vmin, vmax = vmin - pad, vmax + pad
    ticks = _nice_ticks(vmin, vmax)

    def x(i: int) -> float:
        return left + (i / (n - 1) if n > 1 else 0.5) * plot_w

    def y(v: float) -> float:
        return top + plot_h - (v - vmin) / (vmax - vmin) * plot_h

    parts = [_svg_open(width, height)]
    for tv in ticks:
        gy = y(tv)
        parts.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{left+plot_w}" '
                    f'y2="{gy:.1f}" stroke="{GRAY}" stroke-width="1" '
                    f'opacity="0.2"/>')
        parts.append(f'<text x="{left-8}" y="{gy+4:.1f}" font-size="10" '
                    f'fill="{GRAY}" text-anchor="end">{tv:,.1f}{unit}</text>')

    if threshold is not None:
        ty = y(float(threshold))
        parts.append(f'<line x1="{left}" y1="{ty:.1f}" x2="{left+plot_w}" '
                    f'y2="{ty:.1f}" stroke="{GRAY}" stroke-width="1.4" '
                    f'stroke-dasharray="5,4"/>')
        parts.append(f'<text x="{left+plot_w}" y="{ty-6:.1f}" font-size="10" '
                    f'fill="{GRAY}" text-anchor="end">{_esc(_W["threshold_prefix"])} '
                    f'{float(threshold):,.1f}{unit}</text>')

    pts = " ".join(f"{x(i):.1f},{y(float(v)):.1f}"
                   for i, v in enumerate(s.values))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{BASE}" '
                f'stroke-width="2.4"/>')

    x_axis_y = top + plot_h
    for i, (idx, v) in enumerate(s.items()):
        px, py = x(i), y(float(v))
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.4" '
                    f'fill="{BASE}"/>')
        parts.append(f'<text x="{px:.1f}" y="{py-10:.1f}" font-size="9.5" '
                    f'fill="{INK}" text-anchor="middle">{float(v):,.1f}'
                    f'{unit}</text>')
        parts.append(f'<text x="{px:.1f}" y="{x_axis_y+18:.1f}" '
                    f'font-size="9.5" fill="{GRAY}" text-anchor="end" '
                    f'transform="rotate(-40 {px:.1f} {x_axis_y+18:.1f})">'
                    f'{_esc(idx)}</text>')

    parts.append(_caption(x_axis_y + bottom_axis_gap + x_label_h + 8, grain))
    parts.append("</svg>")
    return "".join(parts)
