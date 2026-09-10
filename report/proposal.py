# -*- coding: utf-8 -*-
"""제안서 조립 — topic_evidence() 근거만으로 처음부터 다시 짠 버전.

build(topic, evidence, cards, human)은 core/metrics.py의 proposal_topics()·
topic_evidence()가 이미 조회해 둔 값만 문장으로 옮긴다. 이 파일 스스로
데이터를 조회하지 않는다(topic_evidence()가 이미 "조회만 한다"를 지켰으니,
여기서 다시 querying하면 같은 계산이 두 곳에서 갈릴 위험이 생긴다).

절 순서·제목·질문은 core/config.py의 PROPOSAL_SECTIONS 하나에서 읽는다 —
이 파일에 문자열을 박지 않는다(그 상수의 근거는 CLAUDE.md "제안서 구조
확정" 절과 config.py 자체 주석에 있다).

자동 절(현황·원인·규모·추세): evidence[키]가 데이터를 냈으면 그 숫자로
문장을 짓는다. evidence[키]["사유"]가 있으면(못 낸 이유) 절을 통째로
빼지 않고 그 사유를 "문장"에 그대로 담아 "없음" 상태로 남긴다 — 팀장이
왜 없는지 볼 수 있어야 한다.

사람 절(위험철회·요청)은 문장을 짓지 않는다. "위험과 철회 기준은
무엇인가" 절만 cards(제안카드.md 파싱 결과, report/card_parser.py의
parse_file()이 만든 것 — 여기서 새로 파싱하지 않는다)에서 topic과 제목이
같은 카드를 찾아 "되돌림"·"효과"를 읽기 전용 참고 자료("표")로 먼저
보여준다("적용" 절이 판단기준.md 후보를 읽기 전용으로 보여줬던 것과 같은
패턴). "문장"(사람이 실제로 쓰는 칸)은 참고 자료와 분리된 별도 값이라
고쳐 넣을 방법이 없다.
"""
from __future__ import annotations

import html as _html
import re

import pandas as pd

from core import config as C
from report.sections import check_phrasing
from report.to_pdf import build_pdf as _build_pdf

# 절 키 -> viz/proposal_charts.py의 차트 함수 이름(접두어). report/proposal.py는
# viz/를 import하지 않는다 — 차트를 실제로 그리는 건 pages/*.py의 몫이고,
# 여기서는 "이 절엔 이 차트가 맞는다"는 표시만 남긴다(sections.py가
# "charts": ["funnel","device"] 키만 남기고 실제 렌더링을 미루는 것과 같은
# 분리). "규모"·사람 절은 차트가 없다 — viz에 그 절용 차트 함수가 없다.
_CHART_KEYS = {"현황": "funnel", "원인": "gap", "추세": "trend"}

# 이 파일에 쓰이는 고정 문구는 전부 core.config.PROPOSAL_WORDS["report"]에
# 있다 — 여기서 문자열을 직접 박지 않는다(근거는 config.py 자체 주석).
_W = C.PROPOSAL_WORDS["report"]


def _scale_sentence(evidence: dict) -> str | None:
    """"그래서 얼마인가"(3문장) — 연간 환산. 규모 근거가 없으면(사유가
    있으면) 아무 것도 돌려주지 않는다 — 없는 걸 억지로 문장에 넣지 않는다.
    """
    ev = evidence.get("규모") or {}
    if ev.get("사유"):
        return None
    conv = ev.get("환산_연간건수")
    if not conv:
        return None
    return (f"연간으로 환산하면 {conv['값']:,.0f}명 규모다"
            f"({_W['scale_assumption']}).")


def _sentence_현황(evidence: dict) -> list[str]:
    ev = evidence.get("현황") or {}
    if ev.get("사유"):
        return [ev["사유"]]
    f = ev["표"]
    ranked = f[f["step_rate"].notna()].sort_values("step_rate")
    if not len(ranked):
        return [_W["status_no_evidence"]]
    worst = ranked.iloc[0]
    pos = f.index.get_loc(worst.name)
    prev_n = int(f["n"].iloc[pos - 1]) if pos > 0 else int(worst["n"])

    sentences = [
        f"'{worst['label']}' 단계에서는 {prev_n:,}명 중 {int(worst['n']):,}명만 "
        f"넘어가, 전환율이 {float(worst['step_rate'])*100:.1f}%다.",
    ]
    if len(ranked) >= 2:
        second = ranked.iloc[1]
        gap_pp = (float(second["step_rate"]) - float(worst["step_rate"])) * 100
        sentences.append(
            f"다른 단계 중 가장 낮은 '{second['label']}'({float(second['step_rate'])*100:.1f}%)"
            f"보다도 {gap_pp:.1f}%p 더 낮아, 전체 흐름 중 이 지점이 가장 약하다.")
    scale = _scale_sentence(evidence)
    if scale:
        sentences.append(scale)
    return sentences


def _sentence_원인(evidence: dict) -> list[str]:
    ev = evidence.get("원인") or {}
    if ev.get("사유"):
        return [ev["사유"]]
    g = ev["표"]
    dim_col = g.columns[0]
    trusted = g[g["신뢰"] == ""]
    best = trusted[trusted["표시"] == "최고"]
    worst = trusted[trusted["표시"] == "최저"]
    if not len(best) or not len(worst):
        return [_W["cause_no_evidence"]]
    b, w = best.iloc[0], worst.iloc[0]
    gap_pp = (float(b["전환율"]) - float(w["전환율"])) * 100

    sentences = [
        f"'{w[dim_col]}'는 {int(w['도달']):,}명 중 {int(w['전환']):,}명만 넘어가, "
        f"전환율이 {float(w['전환율'])*100:.1f}%다.",
        f"가장 높은 '{b[dim_col]}'({float(b['전환율'])*100:.1f}%)보다 {gap_pp:.1f}%p "
        f"낮아, 두 집단 사이에 뚜렷한 차이가 있다.",
    ]
    scale = _scale_sentence(evidence)
    if scale:
        sentences.append(scale)
    return sentences


def _sentence_규모(evidence: dict) -> list[str]:
    ev = evidence.get("규모") or {}
    if ev.get("사유"):
        return [ev["사유"]]
    raw = ev["실측_원자료"]
    conv = ev["환산_연간건수"]
    return [
        f"이 문제와 관련된 인원은 실측 {raw['raw_count']:,.0f}명이다.",
        f"연간으로 환산하면 {conv['값']:,.0f}명 규모다({_W['scale_assumption']}).",
    ]


def _sentence_추세(evidence: dict) -> list[str]:
    ev = evidence.get("추세") or {}
    if ev.get("사유"):
        return [ev["사유"]]
    s = ev["표"]
    first_idx, first_v = s.index[0], float(s.iloc[0])
    last_idx, last_v = s.index[-1], float(s.iloc[-1])
    delta = last_v - first_v
    pct = (delta / first_v * 100) if first_v else 0.0

    sentences = [f"{first_idx}에 {first_v:,.1f}이던 값이 {last_idx}에는 "
                f"{last_v:,.1f}다."]
    if delta != 0:
        direction = "늘었다" if delta > 0 else "줄었다"
        sentences.append(f"{len(s)}개월 전 대비 {abs(pct):.1f}% {direction}.")
    scale = _scale_sentence(evidence)
    if scale:
        sentences.append(scale)
    return sentences


_SENTENCE_BUILDERS = {
    "현황": _sentence_현황, "원인": _sentence_원인,
    "규모": _sentence_규모, "추세": _sentence_추세,
}


def _auto_section(meta: dict, evidence: dict) -> dict:
    """자동 절 하나를 조립한다. 문장은 최대 세 개 — ①무슨 일이 일어나는가
    (숫자·분모) ②그게 왜 문제인가(비교 대상 대비 격차) ③그래서 얼마인가
    (연간 환산, 실측 문장과 분리하고 가정을 괄호로 붙인다). 근거가 없으면
    그 사유 한 문장만 담는다 — 절 자체는 지우지 않는다.

    check_phrasing()은 report/sections.py 것을 그대로 재사용한다 — 새로
    만들지 않는다. 자동 생성 문장이라도 인과를 단정하는 말이 섞이면
    "phrasing_flags"에 담아 알린다(값은 그대로 둔다 — 걸려도 절 자체를
    지우지 않는다는 이 프로젝트 전체 원칙과 같다).
    """
    key = meta["키"]
    ev = evidence.get(key) or {"표": None, "사유": _W["evidence_missing"].format(key=key)}
    문장 = " ".join(_SENTENCE_BUILDERS[key](evidence))

    if key == "규모":
        표 = None if ev.get("사유") else {
            _W["scale_raw_label"]: ev.get("실측_원자료"),
            _W["scale_annual_label"]: ev.get("환산_연간건수"),
        }
    else:
        표 = ev.get("표")

    return {
        "제목": meta["제목"], "질문": meta["질문"], "kind": "auto",
        "문장": 문장, "차트": (_CHART_KEYS.get(key) if 표 is not None else None),
        "표": 표, "phrasing_flags": check_phrasing(문장),
    }


def _find_matching_card(cards: dict | None, topic: dict) -> dict | None:
    """cards(report.card_parser.parse_file() 결과)에서 topic과 제목이 같은
    카드를 찾는다. 자동 생성 topic 제목과 사람이 쓴 카드 제목은 형식이
    달라 자주 못 찾는다 — 못 찾으면 None을 돌려줄 뿐 비슷한 걸로 추측해
    맞춰 넣지 않는다.
    """
    for c in (cards or {}).get("cards", []):
        if c.get("제목") == topic.get("제목"):
            return c
    return None


def _risk_section(meta: dict, topic: dict, cards: dict | None,
                   human: dict) -> dict:
    card = _find_matching_card(cards, topic)
    if card:
        표 = {"되돌림": card.get("되돌림", ""), "효과": card.get("효과", "")}
    else:
        표 = {"사유": _W["risk_no_card"]}
    문장 = human.get(meta["제목"], "")
    return {
        "제목": meta["제목"], "질문": meta["질문"], "kind": "human",
        "문장": 문장, "차트": None, "표": 표,
        "phrasing_flags": check_phrasing(문장),
    }


def _ask_section(meta: dict, human: dict) -> dict:
    문장 = human.get(meta["제목"], "")
    return {
        "제목": meta["제목"], "질문": meta["질문"], "kind": "human",
        "문장": 문장, "차트": None, "표": None,
        "phrasing_flags": check_phrasing(문장),
    }


def build(topic: dict, evidence: dict, cards: dict | None = None,
          human: dict | None = None) -> dict:
    """제안서를 조립한다. 이 함수는 데이터를 조회하지 않는다 — 전부
    호출하는 쪽이 이미 조회해 넘긴 값(topic·evidence·cards)만 문장으로
    옮긴다.

    topic     core.metrics.proposal_topics(t)가 돌려준 원소 하나(호출하는
              쪽이 기각되지 않은 것 중 규모 최상위 1건을 이미 골라 넘긴다
              — 여기서 다시 고르지 않는다).
    evidence  core.metrics.topic_evidence(t, topic)의 반환값. {"현황",
              "원인","규모","추세"} 네 키.
    cards     report.card_parser.parse_file("my-report/제안카드.md")의
              반환값(없으면 None) — "위험과 철회 기준은 무엇인가" 절의
              참고 자료를 찾는 데만 쓴다.
    human     사람이 쓴 절의 문장. {"위험과 철회 기준은 무엇인가?": "...",
              "무엇을 승인해 달라는 것인가?": "..."}처럼 절 제목을 키로 쓴다.

    반환: {"요약": {"제목","한줄"}, "절": [...]}

    "요약"은 topic의 제목·한줄을 그대로 옮긴 것뿐이다(proposal_topics()가
    이미 규모순으로 정렬해 뒀다 — 여기서 다시 순위를 매기지 않는다). 본문
    절 개수에는 안 들어간다.

    "절"은 core.config.PROPOSAL_SECTIONS 순서를 그대로 따른다(현황→원인→
    규모→추세→위험철회→요청) — 이 순서를 바꾸면 안 된다(교안 판단기준 ①).
    절 하나의 모양은 {"제목","질문","kind","문장","차트","표"} 여섯 키뿐이다.

    evidence[키]가 데이터를 못 냈으면(["사유"]가 있으면) 그 절을 빼지
    않는다 — "문장"에 사유를 그대로 담아 절 자체는 목록에 남긴다.
    """
    human = human or {}
    topic = topic or {}
    요약 = {"제목": topic.get("제목", ""), "한줄": topic.get("한줄", "")}

    절 = []
    for meta in C.PROPOSAL_SECTIONS:
        if meta["kind"] == "auto":
            절.append(_auto_section(meta, evidence))
        elif meta["키"] == "위험철회":
            절.append(_risk_section(meta, topic, cards, human))
        else:
            절.append(_ask_section(meta, human))

    return {"요약": 요약, "절": 절}


# ── HTML 내보내기 ────────────────────────────────────────────────────
# build()의 모양({"요약","절"} · 절 하나는 {"제목","질문","kind","문장",
# "차트","표"})에 맞춘 인쇄용 단일 문서다. A4 인쇄를 기준으로 한다
# (@page 규칙) — 화면 미리보기용이 아니라 실제로 뽑아 볼 문서다.
#
# 색은 viz/proposal_charts.py가 쓰는 config.COLORS 3색(ok·block·none)만
# 재사용한다 — warn·primary 등 새 색을 만들지 않는다. --ink(글자)·
# --line(테두리)·--bg·--surface(배경)는 데이터를 나타내는 색이 아니라
# 타이포·배경 톤이라 3색 예산에 넣지 않는다(viz/proposal_charts.py에서도
# 같은 이유로 INK를 3색 예산 밖에 뒀다).
_CSS = """
:root{
  --ok:#10b981; --block:#f43f5e; --none:#64748b;
  --ink:#0f172a; --line:#e2e8f0; --bg:#f8fafc; --surface:#ffffff;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:-apple-system,BlinkMacSystemFont,'Malgun Gothic','Apple SD Gothic Neo',sans-serif;
  background:var(--bg); color:var(--ink); font-size:14px; line-height:1.75;
}
.page{max-width:900px; margin:0 auto; padding:40px 36px 80px}
.num{font-variant-numeric:tabular-nums; font-feature-settings:"tnum"}

.summary{background:var(--surface); border:1px solid var(--line);
  border-top:3px solid var(--line); border-radius:14px; padding:26px 28px;
  margin-bottom:34px; page-break-inside:avoid; break-inside:avoid}
.summary .kicker{font-size:12px; font-weight:700; color:var(--none); letter-spacing:.08em}
.summary h1{font-size:22px; font-weight:800; margin:8px 0 6px; line-height:1.4}
.summary .sub{font-size:14px; color:var(--none); line-height:1.7}

/* 절 하나(제목·배지·질문·문장·차트·표)를 통째로 묶어, 페이지 중간에서
   안 잘리게 한다 — 절 사이가 아니라 절 "안"이 갈라지지 않는 게 목적이라
   page-break-inside를 쓴다. h2 자체는 page-break-after로 다음 내용과
   떨어져 혼자 페이지 끝에 남지 않게 한다. */
.sec-block{margin-bottom:30px; page-break-inside:avoid; break-inside:avoid}
h2.sec{font-size:19px; font-weight:800; margin:0 0 6px;
  display:flex; align-items:center; gap:10px;
  page-break-after:avoid; break-after:avoid-page}
.sec-lead{color:var(--none); font-size:13px; margin:0 0 14px}
.sec-body{font-size:14px; line-height:1.8; white-space:pre-line}

table{border-collapse:collapse; width:100%; font-size:12.5px; margin:12px 0 16px}
th,td{border:1px solid var(--line); padding:6px 9px; text-align:left; vertical-align:top}
th{background:#f8fafc; font-weight:700; font-size:11.5px; color:#334155}
.table-wrap{overflow-x:auto}

.badge{display:inline-flex; align-items:center; gap:5px; font-size:11px;
  font-weight:700; padding:3px 10px; border-radius:999px; white-space:nowrap}
.b-ok{background:rgba(16,185,129,.12); color:var(--ok)}
.b-none{background:rgba(100,116,139,.12); color:var(--none)}

.chart{margin:14px 0; border:1px solid var(--line); border-radius:10px;
  padding:14px 16px; background:var(--surface)}
.chart svg{max-width:100%; height:auto; display:block}

.todo{background:rgba(100,116,139,.10); color:#334155; border-radius:4px; padding:0 4px}

@page{size:A4; margin:18mm 16mm 20mm 16mm}
@media print{
  body{background:#fff; font-size:10.5pt}
  .page{max-width:none; padding:0}
  .todo{background:none}
}
"""

_NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?(?:%p|%|명|건|시간|점|배)?")

# "표"에 실리는 값 중 core/metrics.py 내부 계산에서 쓰던 영문·코드식 키를
# 팀장이 읽을 한글 라벨로 바꾸는 자리. 흩어지지 않게 이 한 곳에서만 관리한다
# — _flatten()(중첩 dict의 키)과 _table_html()의 DataFrame 컬럼 둘 다 이
# 딕셔너리 하나를 쓴다. 값(숫자)은 바꾸지 않는다 — 키 이름만 바꾼다.
_KEY_LABELS = {
    # core.metrics._evidence_scale()의 "실측_원자료"·"환산_연간건수" 안 키
    "raw_count": "실측 인원",
    "기간_년": "환산 기간(년)",
    # core.metrics.funnel()/retention_funnel()이 만드는 "현황" 표의 컬럼
    "step": "단계 순서",
    "label": "단계명",
    "n": "인원",
    "step_rate": "단계 전환율",
    "cum_rate": "누적 전환율",
    "drop": "감소 인원",
    "is_bottleneck": "병목 구간",
}


def _display(v):
    """"표"를 HTML로 그리기 직전, funnel()/retention_funnel() 등이 돌려준
    원본 값(예: "1년차_잔류")의 밑줄 이어붙임을 보여줄 때만 공백으로 푼다.
    원본 반환값 자체는 바꾸지 않는다 — 대시보드 등 다른 화면도 같은 값을
    그대로 쓰기 때문에, 여기 표 렌더링 자리에서만 처리한다. 이 파일 안에서
    "표"를 HTML로 옮기는 곳은 모두 이 함수 하나를 거친다.
    """
    if isinstance(v, str):
        return v.replace("_", " ")
    return v


def _todo(placeholder: str) -> str:
    return f'<span class="todo">{_html.escape(placeholder, quote=False)}</span>'


def _text(value: str) -> str:
    """문장을 이스케이프하고, 그 안의 숫자에 class="num"을 붙인다. 값이
    비어 있으면(사람 절을 아직 안 썼으면) todo로 남긴다 — 빈 문자열을
    그대로 보여주지 않는다.
    """
    value = (value or "").strip()
    if not value:
        return _todo(_W["human_unwritten_print"])
    escaped = _html.escape(value, quote=False)
    return _NUM.sub(lambda m: f'<span class="num">{m.group(0)}</span>', escaped)


def _flatten(v) -> str:
    """"표"의 dict 값이 한 겹 더 dict일 때(예: 규모의 "실측_원자료") 파이썬
    repr이 아니라 "key: value, key: value"로 풀어 쓴다 — 값은 그대로다.
    키는 _KEY_LABELS에 있으면 한글 라벨로 바꾸고, 없으면(이미 한글이면)
    그대로 쓴다.
    """
    if isinstance(v, dict):
        return ", ".join(f"{_KEY_LABELS.get(k, k)}: {_display(v2)}" for k, v2 in v.items())
    return str(_display(v))


def _table_html(표) -> str:
    """절의 "표"를 그대로 HTML로 옮긴다 — 형태(DataFrame·Series·dict)별로
    이미 정해진 값만 옮길 뿐 새로 계산하지 않는다. 표가 없으면 빈 문자열
    (그 절엔 표 자체가 없다는 뜻 — 자리를 만들어 비워 두지 않는다).
    """
    if 표 is None:
        return ""
    if isinstance(표, pd.DataFrame):
        if not len(표):
            return ""
        표 = 표.rename(columns=_KEY_LABELS)
        for col in 표.columns:
            if 표[col].dtype == object:
                표[col] = 표[col].map(_display)
        return f'<div class="table-wrap">{표.to_html(index=False, border=0, na_rep="—")}</div>'
    if isinstance(표, pd.Series):
        if not len(표):
            return ""
        rows = "".join(f'<tr><th>{_html.escape(str(_display(i)))}</th>'
                       f'<td class="num">{_html.escape(f"{_display(v)}")}</td></tr>'
                       for i, v in 표.items())
        return f'<div class="table-wrap"><table><tbody>{rows}</tbody></table></div>'
    if isinstance(표, dict):
        rows = "".join(f'<tr><th>{_html.escape(str(k))}</th><td>{_text(_flatten(v))}</td></tr>'
                       for k, v in 표.items())
        return f'<div class="table-wrap"><table><tbody>{rows}</tbody></table></div>'
    return ""


_BADGE = {"auto": ("b-ok", _W["badge"]["auto"]), "human": ("b-none", _W["badge"]["human"])}


def to_html(result: dict, charts: dict[str, str] | None = None) -> str:
    """제안서를 인쇄용 단일 HTML 파일로 만든다. build()의 반환값
    ({"요약","절"})을 그대로 받는다. A4(@page)를 기준으로 하고, 외부
    CSS·이미지·CDN·웹폰트 없이 시스템 폰트만 써서 문자열 하나로
    완결된다.

    charts는 절의 "차트" 값("funnel"/"gap"/"trend")을 키로, 이미 그려진
    SVG 문자열(viz/proposal_charts.py의 함수가 돌려준 것 그대로)을 값으로
    받는다 — 여기서 새로 그리지 않는다(report/proposal.py는 viz/를
    import하지 않는다 — 차트를 그리는 건 호출하는 쪽(pages/*.py)의
    몫이다). 안 넘기면(None) 차트 없이 문장·표만 인쇄한다.

    절마다 있는 값(제목·질문·문장·표·차트)만 그대로 옮긴다 — 여기서
    새로 판단하거나 거르지 않는다. **거르는 자리는 build() 한 곳뿐이다**
    — build()가 이미 "없으면 사유"로 채워 뒀으므로, 여기서는 그 문장을
    그대로 인쇄할 뿐 절을 숨기거나 빼지 않는다. 아직 안 쓴 사람 절도
    PROPOSAL_WORDS["report"]["human_unwritten_print"] 문구가 그대로
    인쇄된다(그 절을 채우는 로직 자체는 여기서 만들지 않는다).

    절 하나(제목·배지·질문·문장·차트·표 전부)를 하나의
    page-break-inside:avoid 블록으로 묶어, 절이 페이지 중간에서 잘리지
    않게 한다. 절 순서는 build()가 core.config.PROPOSAL_SECTIONS 순서로
    이미 정해 뒀으므로 여기서 바꾸지 않는다 — 마지막 절(요청)이 그대로
    문서의 마지막 내용이 된다.

    본문 안의 숫자에는 class="num"을 붙인다(font-variant-numeric으로만
    보이게 하는 순수 표시용 마크업이라, 값 자체를 바꾸지 않는다).
    """
    charts = charts or {}
    요약 = result.get("요약") or {}
    절들 = result.get("절") or []

    parts = ['<div class="page">', f"""<div class="summary">
  <div class="kicker">{_html.escape(_W["summary_kicker"])}</div>
  <h1>{_text(요약.get("제목", ""))}</h1>
  <div class="sub">{_text(요약.get("한줄", ""))}</div>
</div>"""]

    for sec in 절들:
        badge_cls, badge_label = _BADGE[sec["kind"]]
        block = [f"""<h2 class="sec">{_html.escape(sec["제목"])}
  <span class="badge {badge_cls}">{badge_label}</span></h2>
<p class="sec-lead">{_html.escape(sec["질문"])}</p>
<p class="sec-body">{_text(sec["문장"])}</p>"""]

        chart_key = sec.get("차트")
        svg = charts.get(chart_key) if chart_key else None
        if svg:
            block.append(f'<div class="chart">{svg}</div>')

        표_html = _table_html(sec.get("표"))
        if 표_html:
            block.append(표_html)

        parts.append(f'<div class="sec-block">{"".join(block)}</div>')

    parts.append('</div>')

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(_W["doc_title"])}</title>
<style>{_CSS}</style>
</head>
<body>
{"".join(parts)}
</body>
</html>
"""


def to_pdf(secs: list[dict]) -> bytes:
    """제안 리포트를 PDF로 만든다. report/to_pdf.py의 build_pdf()를 그대로
    재사용한다 — 새로 만들지 않는다. build_pdf()가 받는 sections 계약
    ({"title","kind","body","placeholder"(선택)})을 secs가 이미 그대로
    만족하므로 그냥 넘긴다. charts는 없다 — 제안 리포트는 카드 텍스트
    중심이라 sections.py의 리포트처럼 별도 차트 이미지를 붙이지 않는다.
    표지 제목만 "제안서"로 다르게 준다.
    """
    return _build_pdf(secs, charts={}, title="제안서")
