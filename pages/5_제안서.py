# -*- coding: utf-8 -*-
"""제안서 — proposal_topics()가 찾은 문제 후보 중 하나를 골라 근거를 본다.

거르는 자리는 core.metrics.proposal_topics()와 report.proposal.build()
둘뿐이다(기각·못 믿을 조건 판정, "없으면 사유"로 채우는 것 모두 그 두
함수 안에서 끝난다). 이 화면은 그 결과를 그대로 보여줄 뿐, 여기서 다시
후보를 거르거나 절을 숨기지 않는다 — 기각된 후보도 selectbox에 그대로
남고, 근거가 없는 절도 목록에서 빠지지 않는다.
"""
import streamlit as st

from core import config as C, load, metrics as M
from report import card_parser as CP, proposal as PR, proposal_draft as PD
from viz import proposal_charts as PC, ui

# to_html()이 요구하는 그레인 — CLAUDE.md "그레인" 절과 같은 문구다(새로
# 짓지 않는다). 추세 차트의 단위는 어느 monthly() 지표인지에 따라 다르다.
GRAIN = "사번(직원) 1명 = 1행"
_TREND_UNIT = {"재직인원": "명", "월평균초과근무시간": "시간"}

# 이 화면에 쓰이는 고정 문구는 전부 core.config.PROPOSAL_WORDS["page"]에
# 있다 — 여기서 문자열을 직접 박지 않는다. 배지 라벨(자동/사람)은
# report/proposal.py의 인쇄본과 같은 곳(["report"]["badge"])을 그대로
# 재사용한다 — 화면과 인쇄본에서 같은 말을 따로 골라 어긋나지 않게 한다.
_W = C.PROPOSAL_WORDS["page"]
_BADGE_LABEL = C.PROPOSAL_WORDS["report"]["badge"]

st.set_page_config(page_title=_W["title"], page_icon="📝", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("proposal")

if "run" not in st.session_state:
    st.session_state.run = None
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

CARD_PATH = C.ROOT / "my-report" / "제안카드.md"  # 읽기만 한다 — 고치지 않는다.

st.markdown(f'<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            f'📝 {_W["title"]}</div>', unsafe_allow_html=True)

# ── ① 주제 ────────────────────────────────────────────────────────
topics = M.proposal_topics(t)


def _label(i: int) -> str:
    if i == 0:
        return _W["topic_default"]
    top = topics[i - 1]
    tail = f" {_W['rejected_suffix']}" if top["기각사유"] else ""
    return f"{top['제목']} · 규모(연 {top['규모_연간건수']:.0f}건){tail}"


choice = st.selectbox(_W["topic_label"], list(range(len(topics) + 1)),
                      format_func=_label, index=0)

if choice == 0:
    st.info(_W["no_topic_info"])
    st.stop()

topic = topics[choice - 1]

# 주제별로 나눈 session_state 키(topic["키"] 기준 — 제목이 아니라 키를
# 쓴다. 제목은 사람이 읽는 문서용이고, 키가 이 주제의 진짜 식별자다)라
# 다른 주제로 바꿔도 이 주제의 입력 칸만 보이고 값이 섞이지 않는다. 처음
# 보는 주제면 PD.DRAFT_PATH에 저장된 값으로 한 번만 채운다 — 그 뒤로는
# 사용자가 입력한 값을 그대로 둔다(새로고침 전까지는 세션에, 저장 버튼을
# 누르면 파일에 남는다).
_draft_for_topic = PD.load().get(topic["제목"], {})
for _sec_title in PD.HUMAN_TITLES:
    _k = PD.session_key(topic["키"], _sec_title)
    if _k not in st.session_state:
        st.session_state[_k] = _draft_for_topic.get(_sec_title, "")

human = {sec_title: st.session_state[PD.session_key(topic["키"], sec_title)]
         for sec_title in PD.HUMAN_TITLES}

# ── ② 근거 한 줄 요약 ────────────────────────────────────────────
evidence = M.topic_evidence(t, topic)
cards = CP.parse_file(CARD_PATH) if CARD_PATH.exists() else None
result = PR.build(topic, evidence, cards, human)

요약 = result["요약"]
st.markdown(
    f'<div class="card" style="margin:14px 0 22px">'
    f'<div style="font-size:12px;font-weight:700;color:{C.BRAND["primary"]};'
    f'letter-spacing:.04em;margin-bottom:6px">{_W["evidence_card_label"]}</div>'
    f'<div style="font-size:17px;font-weight:700;margin-bottom:6px">'
    f'{요약["제목"]}</div>'
    f'<div style="font-size:14px;color:{C.BRAND["muted"]}">{요약["한줄"]}</div>'
    f'</div>', unsafe_allow_html=True)

# ── ③ 절별 미리보기 ──────────────────────────────────────────────
ui.section(_W["preview_section"])
for sec in result["절"]:
    lvl, kind_label = (("ok", _BADGE_LABEL["auto"]) if sec["kind"] == "auto"
                       else ("warn", _BADGE_LABEL["human"]))
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin:16px 0 2px">'
        f'<div style="font-size:15px;font-weight:700">{sec["제목"]}</div>'
        f'{ui.badge(lvl, kind_label)}</div>', unsafe_allow_html=True)
    st.caption(sec["질문"])

    if sec["kind"] == "human":
        # 위험철회 절만 "표"(어제 카드의 되돌림·효과, 또는 카드가 없다는
        # 사유)를 갖는다(report/proposal.py의 _risk_section() 참고) — 입력
        # 칸을 새로 놓는다고 이 읽기 전용 참고를 없애지 않는다.
        참고 = sec.get("표") or {}
        if 참고.get("되돌림") or 참고.get("효과"):
            st.markdown(
                f'<div class="card tight" style="margin-bottom:8px">'
                f'<div style="font-size:12px;font-weight:700;'
                f'color:{C.BRAND["muted"]};margin-bottom:4px">'
                f'{_W["card_reference_label"]}</div>'
                f'<b>되돌림</b> · {참고.get("되돌림", "")}<br>'
                f'<b>효과</b> · {참고.get("효과", "")}</div>',
                unsafe_allow_html=True)
        elif 참고.get("사유"):
            st.caption(참고["사유"])

        st.text_area(
            sec["제목"], key=PD.session_key(topic["키"], sec["제목"]),
            height=120, label_visibility="collapsed",
            placeholder=_W["human_unwritten_screen"])
    else:
        # ★ 근거가 안 나오면(문장이 "없다"는 사유뿐이어도) 빈 화면 대신 그
        #   사유 문장을 그대로 보여준다 — build()가 이미 채워 둔 값이라
        #   여기서 다시 판단하지 않는다.
        st.markdown(f'<div class="card tight">{sec["문장"]}</div>',
                   unsafe_allow_html=True)

if st.button(_W["save_button"]):
    draft = PD.load()
    draft[topic["제목"]] = {sec_title: st.session_state[PD.session_key(topic["키"], sec_title)]
                           for sec_title in PD.HUMAN_TITLES}
    PD.save(draft)
    st.success(_W["save_success"])

# ── ④ HTML 내려받기 ──────────────────────────────────────────────
# 차트는 여기(pages/*.py)에서 그린다 — report/proposal.py는 viz/를
# import하지 않는다. 절의 "표"를 그대로 viz/proposal_charts.py에 넘길
# 뿐 새로 계산하지 않는다.
charts = {}
for sec in result["절"]:
    chart_key, 표 = sec.get("차트"), sec.get("표")
    if chart_key is None or 표 is None:
        continue
    if chart_key == "funnel":
        charts["funnel"] = PC.funnel_svg(표, GRAIN)
    elif chart_key == "gap":
        charts["gap"] = PC.gap_svg(표, GRAIN)
    elif chart_key == "trend":
        unit = _TREND_UNIT.get(getattr(표, "name", ""), "")
        charts["trend"] = PC.trend_svg(표, GRAIN, unit=unit)

st.divider()
ui.section(_W["export_section"])
st.download_button(
    _W["download_button"], PR.to_html(result, charts),
    file_name=_W["download_filename"], mime="text/html")
