# -*- coding: utf-8 -*-
"""리포트 — 남에게 보내는 문서.

8장 중 5장은 자동으로 쓰고, **3장(배경·해석·제안)은 사람이 쓴다.**
자동 생성 문장은 인과를 단정하지 않는지 스스로 검사한다.
"""
from datetime import datetime

import pandas as pd
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

if "limits_items" not in st.session_state:
    st.session_state.limits_items = S.limits_items(t)

secs = S.build(t, st.session_state.human)
# "7. 한계"는 st.data_editor로 편집한 항목 기준으로 다시 조립한다 — 화면과
# PDF(아래 to_pdf.build_pdf(secs, ...))가 이 secs를 그대로 같이 쓰므로,
# 여기서 한 번만 바꿔 두면 둘 다 편집 결과를 반영한다.
_limits_idx = next(i for i, s in enumerate(secs) if s["title"] == "7. 한계")
secs[_limits_idx] = S._s7_limits(t, items=st.session_state.limits_items)

# 리포트 차트에 쓸 분해 축. 대시보드(pages/2_대시보드.py)와 같은 후보 중
# 부서 — 6칸 전부 MIN_SAMPLE(30) 이상이라 가장 안전하다.
DIM = "부서"

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
    if sec["kind"] == "human":
        st.markdown(
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
            '<div style="font-size:19px;font-weight:700">사람이 쓰는 장 '
            '(배경·해석·제안)</div>'
            f'{ui.badge("ok" if done == need else "warn", f"사람 작성 {done}/{need}장")}'
            '</div>', unsafe_allow_html=True)
    else:
        kind = {"auto": "자동 생성", "todo": "아직 안 만듦"}[sec["kind"]]
        lvl = {"auto": "ok", "todo": "none"}[sec["kind"]]
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
            f'<div style="font-size:19px;font-weight:700">{sec["title"]}</div>'
            f'{ui.badge(lvl, kind)}</div>', unsafe_allow_html=True)

    if sec["kind"] == "todo":
        ui.todo_card(sec["todo"])
    elif sec["kind"] == "auto":
        if sec["title"] == "7. 한계":
            st.caption("항목의 내용을 고치거나, '포함' 체크를 꺼서 리포트·PDF에서 "
                       "빼거나, 행을 추가·삭제할 수 있습니다. 아래 표 밑 두 문장은 "
                       "항상 고정이라 편집 대상이 아닙니다.")
            edited_df = st.data_editor(
                pd.DataFrame(st.session_state.limits_items),
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                column_order=["출처", "내용", "포함"],
                column_config={
                    "출처": st.column_config.SelectboxColumn(
                        "출처", options=["검증 경고", "표본 부족", "확인하지 못한 것"],
                        required=True),
                    "내용": st.column_config.TextColumn("내용", required=True),
                    "포함": st.column_config.CheckboxColumn("포함", default=True),
                },
                key="limits_editor",
            )
            edited_items = edited_df.to_dict("records")

            before_warn = sum(1 for it in st.session_state.limits_items
                              if it.get("출처") == "검증 경고")
            after_warn = sum(1 for it in edited_items
                             if it.get("출처") == "검증 경고")
            if after_warn < before_warn:
                st.warning("검증 경고를 뺐습니다.")

            st.session_state.limits_items = edited_items
            sec = S._s7_limits(t, items=edited_items)
            secs[_limits_idx] = sec

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
            g = M.funnel_by(t["HR_직원"], t["HR_퇴사이력"], DIM,
                            f.step.iloc[bi - 1], f.step.iloc[bi])
            # 대시보드 분해 표와 같은 마스킹 — 축이 바뀌어도 매번 검사한다.
            g["사유"] = g["도달"].apply(
                lambda n: M.trust_check({"ok": True}, int(n)))
            st.image(pdf_charts.device_png(g), width="stretch")
        if "experiments" in sec.get("charts", []):
            st.image(pdf_charts.experiments_png(M.experiment_results(t)),
                     width="stretch")
    else:
        # 2·6·8장(사람이 쓰는 장)을 폼 하나로 묶는다 — 어느 장을 골라도
        # 같은 폼이 뜨고, "저장" 한 번으로 셋 다 저장된다.
        human_secs = {s["title"]: s for s in secs if s["kind"] == "human"}
        # 작성 가이드 — 참고용. text_area의 value로는 절대 안 넣는다
        # (입력 칸은 항상 빈 채로 시작해야 한다). st.expander로 입력 칸과
        # 시각적으로 분명히 구분한다.
        guide_funcs = {
            "2. 배경": S.guide_background,
            "6. 해석": S.guide_interpretation,
            "8. 제안": S.guide_proposal,
        }
        guide_disclaimer = "이 내용은 가이드일 뿐입니다. 담당자가 최종 작성 후 확정해야 합니다."
        with st.form("사람이 쓰는 장"):
            inputs = {}
            for htitle in ["2. 배경", "6. 해석", "8. 제안"]:
                hs = human_secs[htitle]
                with st.expander(f"📋 {htitle} 작성 가이드 (참고용)"):
                    st.markdown(guide_funcs[htitle](t))
                    st.caption(guide_disclaimer)
                inputs[htitle] = st.text_area(
                    htitle, value=hs["body"], height=180,
                    placeholder=hs["placeholder"])
            submitted = st.form_submit_button("저장")

        if submitted:
            for htitle, txt in inputs.items():
                st.session_state.human[htitle] = txt

            # check_phrasing()은 자동 생성 장뿐 아니라 사람이 쓴 장에도
            # 걸어야 한다 — 사람이 인과 단정 표현을 더 자주 쓴다
            # (check_phrasing() 자체 docstring의 지시). 걸려도 저장은
            # 이미 했다 — 경고만 남긴다.
            bad_by_title = {htitle: S.check_phrasing(txt)
                            for htitle, txt in inputs.items()}
            bad_by_title = {k: v for k, v in bad_by_title.items() if v}
            if bad_by_title:
                detail = " / ".join(f"{t}: {', '.join(w)}"
                                    for t, w in bad_by_title.items())
                ui.callout(f"저장했습니다. 다만 인과를 단정하는 표현이 "
                           f"있습니다 — <b>{detail}</b>. 관측 데이터로는 "
                           f"인과를 주장할 수 없습니다.")
            else:
                st.success("저장했습니다 — 인과 단정 표현 검사 통과(세 장 전부).")

# ── 내보내기 ──────────────────────────────────────────────────────
st.divider()
ui.section("내보내기")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**PDF** — 표지 · 목차 · 차트 포함")
    if st.button("PDF 만들기", type="primary"):
        made = False
        with st.status("리포트를 만드는 중", expanded=True) as box:
            try:
                st.write("1) 장별 내용 모으는 중")
                pdf_secs = secs  # 사람이 쓴 장 + 편집된 7.한계까지 이미 반영됨

                st.write("2) 차트 이미지 만드는 중")
                f = M.funnel(t["HR_직원"], t["HR_퇴사이력"])
                bi = max(int(f.index[f.is_bottleneck][0]), 1)
                g = M.funnel_by(t["HR_직원"], t["HR_퇴사이력"], DIM,
                                f.step.iloc[bi - 1], f.step.iloc[bi])
                # 대시보드 분해 표와 같은 마스킹 — 축이 바뀌어도 매번 검사한다.
                g["사유"] = g["도달"].apply(
                    lambda n: M.trust_check({"ok": True}, int(n)))
                charts = {
                    "funnel": pdf_charts.funnel_png(f),
                    "device": pdf_charts.device_png(g),
                    "experiments": pdf_charts.experiments_png(
                        M.experiment_results(t)),
                }

                st.write("3) PDF 조립하는 중")
                pdf = to_pdf.build_pdf(pdf_secs, charts)
            except Exception as e:
                box.update(label="실패", state="error")
                st.error(f"리포트 생성 실패: {e}")
            else:
                st.session_state.pdf = pdf
                # 파일명 표시용 실행 시각 — 계산 경로에는 안 들어간다.
                st.session_state.pdf_made_at = datetime.now().strftime(
                    "%Y%m%d_%H%M%S")
                box.update(label="완성", state="complete", expanded=False)
                made = True

        if made:
            st.toast("리포트가 만들어졌습니다", icon="📄")
    if st.session_state.get("pdf"):
        made_at = st.session_state.get("pdf_made_at", "")
        st.download_button(
            "PDF 내려받기", st.session_state.pdf,
            file_name=f"성장리포트_{C.PERIOD[0][:7]}_{made_at}.pdf",
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
