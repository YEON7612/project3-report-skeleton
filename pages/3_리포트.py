# -*- coding: utf-8 -*-
"""리포트 — 남에게 보내는 문서.

8장 중 5장은 자동으로 쓰고, **3장(배경·해석·제안)은 사람이 쓴다.**
자동 생성 문장은 인과를 단정하지 않는지 스스로 검사한다.
"""
import streamlit as st

from core import config as C, gates, load, metrics as M
from report import sections as S, to_pdf
from viz import pdf_charts, ui

st.set_page_config(page_title="리포트", page_icon="📄", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("report")

if "run" not in st.session_state:
    st.session_state.run = None
if "human" not in st.session_state:
    st.session_state.human = {}
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()
secs = S.build(t, st.session_state.human)

# ★ 리포트 차트에 쓸 분해 축. 내 데이터의 컬럼명으로 바꾼다.
DIM = "device"

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '리포트</div>', unsafe_allow_html=True)

nav, body = st.columns([1, 3.4])

with nav:
    titles = [s["title"] for s in secs]
    pick = st.radio("목차", titles, label_visibility="collapsed")
    st.divider()
    done = sum(1 for s in secs if s["kind"] == "human" and s["body"].strip())
    need = sum(1 for s in secs if s["kind"] == "human")
    left = sum(1 for s in secs if s["kind"] == "todo")
    st.caption(f"사람 작성 {done}/{need}장")
    st.progress(done / need if need else 0)
    if left:
        st.caption(f"아직 안 만든 장 {left}개")

sec = next(s for s in secs if s["title"] == pick)

with body:
    kind = {"auto": "자동 생성", "human": "사람 작성",
            "todo": "아직 안 만듦"}[sec["kind"]]
    lvl = {"auto": "ok", "todo": "none"}.get(
        sec["kind"], "ok" if sec["body"].strip() else "warn")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
        f'<div style="font-size:19px;font-weight:700">{sec["title"]}</div>'
        f'{ui.badge(lvl, kind)}</div>', unsafe_allow_html=True)

    if sec["kind"] == "todo":
        ui.todo_card(sec["todo"])
    elif sec["kind"] == "auto":
        st.markdown(
            f'<div class="card"><div style="white-space:pre-line;'
            f'font-size:14px;line-height:1.75">{sec["body"]}</div></div>',
            unsafe_allow_html=True)
        bad = S.check_phrasing(sec["body"])
        if bad:
            ui.callout(f"자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                       f"<b>{', '.join(bad)}</b>. 관측 데이터로는 인과를 "
                       f"주장할 수 없습니다.")
        else:
            st.caption("✓ 인과 단정 표현 검사 통과")

        if "funnel" in sec.get("charts", []):
            f = M.funnel(t["HR_직원"], t["HR_퇴사이력"])
            st.image(pdf_charts.funnel_png(f), width="stretch")
        if "device" in sec.get("charts", []):
            f = M.funnel(t["HR_직원"], t["HR_퇴사이력"])
            bi = max(int(f.index[f.is_bottleneck][0]), 1)
            g = M.funnel_by(t["funnel_events"], t["sessions"], DIM,
                            f.step.iloc[bi - 1], f.step.iloc[bi])
            st.image(pdf_charts.device_png(g), width="stretch")
        if "experiments" in sec.get("charts", []):
            st.image(pdf_charts.experiments_png(M.experiment_results(t)),
                     width="stretch")
    else:
        st.caption(sec["placeholder"])
        if sec.get("hint"):
            ui.callout(sec["hint"], "info")
        txt = st.text_area("본문", value=sec["body"], height=280,
                           key=f"h_{sec['title']}", label_visibility="collapsed")
        if st.button("저장", type="primary"):
            st.session_state.human[sec["title"]] = txt
            st.rerun()

# ── 내보내기 ──────────────────────────────────────────────────────
st.divider()
ui.section("내보내기")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**PDF** — 표지 · 목차 · 차트 포함")
    if st.button("PDF 만들기", type="primary"):
        with st.spinner("차트를 그리고 PDF를 조립하는 중..."):
            f = M.funnel(t["HR_직원"], t["HR_퇴사이력"])
            bi = max(int(f.index[f.is_bottleneck][0]), 1)
            g = M.funnel_by(t["funnel_events"], t["sessions"], DIM,
                            f.step.iloc[bi - 1], f.step.iloc[bi])
            charts = {
                "funnel": pdf_charts.funnel_png(f),
                "device": pdf_charts.device_png(g),
                "experiments": pdf_charts.experiments_png(M.experiment_results(t)),
            }
            pdf = to_pdf.build_pdf(secs, charts)
        st.session_state.pdf = pdf
        st.success(f"생성 완료 · {len(pdf)/1024:.0f}KB")
    if st.session_state.get("pdf"):
        st.download_button("PDF 내려받기", st.session_state.pdf,
                           file_name=f"성장리포트_{C.PERIOD[0][:7]}.pdf",
                           mime="application/pdf")

with c2:
    st.markdown("**이메일 초안** — 실제로 보내지 않습니다")
    draft = S.email_draft(t, secs)
    st.text_input("받는 사람", draft["to"], disabled=True)
    st.text_input("제목", draft["subject"], disabled=True)
    with st.expander("본문 미리보기"):
        st.markdown(draft["html"], unsafe_allow_html=True)

    run = st.session_state.run
    if run and gates.is_passed(run, 2):
        st.markdown('<div class="gate final" style="margin-top:12px">'
                    '<div class="q">게이트 3 · 발송</div>'
                    '<div style="font-size:12.5px;color:#9f1239;margin-top:6px">'
                    '<b>되돌릴 수 없습니다.</b> 통과시키면 발송 기록이 남습니다.</div>'
                    '</div>', unsafe_allow_html=True)
        if gates.is_passed(run, 3):
            st.success("게이트 3 통과 기록됨 · 실제 발송은 하지 않았습니다.")
        else:
            ok = st.text_input('확인 문구로 "발송"을 입력하십시오', key="g3")
            if st.button("확정", disabled=(ok != "발송")):
                gates.pass_gate(run, 3, "초안 확정 (실제 발송 없음)")
                gates.save(run)
                st.rerun()
    else:
        st.caption("게이트 2를 통과해야 발송 확정 단계가 열립니다.")
