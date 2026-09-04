# -*- coding: utf-8 -*-
"""대시보드 — 여기서 발견이 일어난다.

반복해서 보는 화면이므로 실행 절차를 지나치지 않고 바로 지표에 닿게 한다.

이 화면은 Day2~3에 걸쳐 살아난다.
  Day2  지표 카드 · 획득 퍼널 · 유지 퍼널
  Day3  분해 · 실험 카드
"""
from urllib.parse import urlencode, urlsplit, urlunsplit

import pandas as pd
import streamlit as st

from core import config as C, load, metrics as M
from viz import charts, ui

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("dash")

if "run" not in st.session_state:
    st.session_state.run = None
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '대시보드</div>', unsafe_allow_html=True)

# ── 지표 카드 ─────────────────────────────────────────────────────
k = ui.guard(M.kpis, t)
if k:
    m = ui.guard(M.monthly, t)
    # kpis()가 돌려주는 참고용 필드(참고용_전사_입사1년내이탈률)는 카드 4개에서 뺀다.
    KPI_CARDS = ["재직인원", "입사1년내이탈률", "평균평가점수", "월평균초과근무시간"]
    # 높을수록 나쁜 지표 — metrics.status_of() 안의 higher_is_worse와 맞춰 둔다.
    # 늘어난 게 나쁜 신호인 지표는 delta_color="inverse"로 화살표 색을 뒤집는다
    # (예: 이탈률이 늘면 나쁜 것이므로 양수 delta를 빨강으로 보여줘야 한다).
    HIGHER_IS_WORSE = {"입사1년내이탈률", "월평균초과근무시간"}
    cols = st.columns(len(KPI_CARDS))
    for col, name in zip(cols, KPI_CARDS):
        v = k[name]
        with col:
            lv = M.status_of(name, v["value"])
            delta, delta_color = None, "normal"
            if m is not None and name in getattr(m, "columns", []) and len(m) >= 2:
                diff = m[name].iloc[-1] - m[name].iloc[-2]
                delta = v["fmt"].replace("{:", "{:+", 1).format(diff)
                delta_color = "inverse" if name in HIGHER_IS_WORSE else "normal"
            st.metric(name, v["fmt"].format(v["value"]), delta,
                      delta_color=delta_color)
            # 추이가 있으면 스파크라인. 지표 이름과 열 이름이 같아야 그려진다.
            if m is not None and name in getattr(m, "columns", []):
                st.plotly_chart(
                    charts.spark(m[name], C.COLORS[lv] if lv != "ok" else None),
                    width="stretch", config={"displayModeBar": False},
                    key=f"sp_{name}")
    if not C.THRESHOLDS:
        st.caption("config.THRESHOLDS 가 비어 있어 전부 정상으로 표시됩니다. "
                   "임계값을 채우면 색이 갈립니다.")

# ── 획득 퍼널 / 유지 퍼널 ─────────────────────────────────────────────
# st.tabs로 분리한다. 탭 렌더링 함수에 @st.fragment를 붙여 부분 재실행되게
# 한다. 다만 분해 축·구간 필터는 fragment 밖에 둔다 — st.query_params를
# fragment 안에서 갱신하면 부분 재실행이라 브라우저 주소창과 화면이
# 어긋날 수 있기 때문이다(_render_decomposition() 참고).
DIMS = ["부서", "직급", "채용경로"]  # 손을 쓸 수 있는 것만 — 식별자·날짜·
                                    # 재직상태(퍼널의 결과 그 자체)는 뺐다.


@st.fragment
def _render_acquisition_funnel(f):
    st.plotly_chart(charts.funnel_bars(f), width="stretch",
                    config={"displayModeBar": False})

    # cum_rate/step_rate는 0~1 비율이라 ProgressColumn/NumberColumn이
    # %로 읽게 표시용 사본에서만 ×100 한다(f 원본은 다른 계산에 계속 쓰이므로
    # 안 건드린다).
    f_disp = f.assign(cum_rate=f["cum_rate"] * 100,
                      step_rate=f["step_rate"] * 100)
    st.dataframe(
        f_disp,
        hide_index=True,
        column_order=["label", "n", "step_rate", "cum_rate", "drop",
                      "is_bottleneck"],
        column_config={
            "label": st.column_config.TextColumn("단계"),
            "n": st.column_config.NumberColumn("인원수", format="%,d"),
            # step_rate: 입사 단계는 직전 단계가 없어 NaN이다. ProgressColumn은
            # NaN을 빈 진행바(=0%처럼 보임)로 그려 오독하기 쉬워서, 값을 그대로
            # 텍스트로 보여주는 NumberColumn을 썼다.
            "step_rate": st.column_config.NumberColumn(
                "직전 단계 대비 유지율", format="%.1f%%"),
            "cum_rate": st.column_config.ProgressColumn(
                "누적 잔류율", format="%.1f%%",
                min_value=float(f_disp["cum_rate"].min()),
                max_value=float(f_disp["cum_rate"].max())),
            "drop": st.column_config.NumberColumn("감소 인원", format="%,d"),
            "is_bottleneck": st.column_config.CheckboxColumn("병목 구간"),
        },
    )

    bn = f[f.is_bottleneck].iloc[0]
    bi = max(int(f.index[f.label == bn.label][0]), 1)
    prev = f.iloc[bi - 1]
    ui.callout(
        f"<b>병목은 {prev.label} → {bn.label}</b> 구간입니다. "
        f"{prev.n:,} 중 {bn.n:,}만 넘어가 "
        f"<b>{(1-bn.step_rate)*100:.1f}%가 이탈</b>합니다.")
    st.caption(
        "10년차_잔류는 위험집합이 47명으로 다른 단계(200~296명)보다 "
        "뚜렷이 작습니다. MIN_SAMPLE(30) 기준은 통과하지만 추정 "
        "신뢰구간은 상대적으로 넓을 수 있습니다.")


def _render_decomposition(t, f, bi):
    """분해 축 + 구간 필터. fragment 밖에서 돈다 — query_params 동기화가
    이유다. st.query_params에서 초기값을 읽고, 없거나 이상한 값이면
    (DIMS에 없는 축, f.step에 없는 구간) 조용히 기본값으로 떨어진다 —
    에러를 내지 않는다.
    """
    qp = st.query_params

    axis_param = qp.get("axis")
    default_dim = axis_param if axis_param in DIMS else DIMS[0]
    dim = st.segmented_control("분해 축", DIMS, default=default_dim,
                               label_visibility="collapsed", key="dim_select")
    if dim not in DIMS:   # 선택 해제 등으로 None이 와도 기본값으로
        dim = default_dim

    seg_options = list(f.step.iloc[:-1])
    seg_param = qp.get("seg")
    default_i = (seg_options.index(seg_param) if seg_param in seg_options
                else min(bi - 1, len(f) - 2))
    i = st.selectbox(
        "구간", range(len(f) - 1),
        format_func=lambda i: f"{f.label.iloc[i]} → {f.label.iloc[i+1]}",
        index=default_i, key="seg_select")

    qp["axis"] = dim
    qp["seg"] = f.step.iloc[i]

    query_string = urlencode({"axis": dim, "seg": f.step.iloc[i]})
    base_url = st.context.url
    if base_url:
        p = urlsplit(base_url)
        link = urlunsplit((p.scheme, p.netloc, p.path, query_string, ""))
    else:
        link = f"?{query_string}"
    st.caption("현재 화면 링크 — 복사해서 새 탭에 붙이면 같은 화면이 뜹니다")
    st.code(link, language=None)

    g = ui.guard(M.funnel_by, t["HR_직원"], t["HR_퇴사이력"], dim,
                 f.step.iloc[i], f.step.iloc[i + 1])
    if g is not None and len(g):
        # 칸마다 trust_check() — 이 프로젝트에서 "못 믿을 항목"이 실제로
        # 나타나는 유일한 자리다(실험이 없어 experiment_results()는
        # 항상 빈 채로 있다). 걸리면 그 칸의 지표 값은 계산에서 빼고
        # 사유만 남긴다 — 숫자는 회색으로도 보여주지 않는다.
        g["사유"] = g["도달"].apply(
            lambda n: M.trust_check({"ok": True}, int(n)))
        trusted = g[g["사유"].isna()].drop(columns="사유")
        untrusted = g[g["사유"].notna()]

        if len(trusted):
            st.plotly_chart(charts.device_compare(trusted),
                            width="stretch",
                            config={"displayModeBar": False})
        if len(untrusted):
            st.caption(
                "표본 부족으로 차트·표에서 값을 빼고 사유만 남긴 칸: "
                + ", ".join(str(v) for v in untrusted[g.columns[0]]))

        # 전환율만 보면 규모(비중)를 놓친다 — 믿을 수 있는 칸만
        # 도달·비중을 표에 남긴다.
        if len(trusted):
            st.dataframe(
                trusted.assign(전환율=trusted["전환율"] * 100,
                               비중=trusted["비중"] * 100),
                hide_index=True,
                column_config={
                    dim: st.column_config.TextColumn(dim),
                    "도달": st.column_config.NumberColumn(
                        "도달", format="%,d"),
                    "전환": st.column_config.NumberColumn(
                        "전환", format="%,d"),
                    "전환율": st.column_config.NumberColumn(
                        "전환율", format="%.1f%%"),
                    "비중": st.column_config.NumberColumn(
                        "비중(도달 중)", format="%.1f%%"),
                },
            )

        # 못 믿는 칸 — 지표 값 대신 사유만, block 색으로 구분한다
        # (config.COLORS 재사용 — 실험 "무효" 카드와 같은 색·같은 원칙:
        # 계산해 놓고 숨기는 게 아니라 계산 자체를 안 한다).
        for _, r in untrusted.iterrows():
            st.markdown(
                f'<div style="border-left:3px solid {C.COLORS["block"]};'
                f'background:rgba(244,63,94,.06);padding:10px 14px;'
                f'border-radius:0 8px 8px 0;font-size:13.5px;'
                f'color:{C.COLORS["block"]};margin-top:8px">'
                f'<b>✕ {r[g.columns[0]]}</b> — {r["사유"]} — '
                f'지표를 계산하지 않습니다.</div>',
                unsafe_allow_html=True)

        if len(trusted) >= 2:
            hi = trusted.loc[trusted.전환율.idxmax()]
            lo = trusted.loc[trusted.전환율.idxmin()]
            if hi[g.columns[0]] != lo[g.columns[0]]:
                ui.callout(
                    f"<b>{lo[g.columns[0]]}</b>이(가) 전체의 "
                    f"<b>{lo.비중*100:.1f}%</b>인데 전환율은 "
                    f"<b>{lo.전환율*100:.1f}%</b>로 "
                    f"{hi[g.columns[0]]}({hi.전환율*100:.1f}%)보다 "
                    f"<b>{(hi.전환율-lo.전환율)*100:.1f}%p 낮습니다.</b>")


@st.fragment
def _render_retention_funnel(t):
    if not C.RETENTION_STEPS:
        st.caption("config.RETENTION_STEPS 가 비어 있습니다. "
                   "7주차에 정한 유지·이탈의 정의를 옮기면 여기에 그려집니다.")
        return
    rf = ui.guard(M.retention_funnel, t)
    if rf is None or not len(rf):
        return
    if "is_bottleneck" not in rf.columns:
        rf = rf.assign(is_bottleneck=False)
    c1, c2 = st.columns([1.15, 1])
    with c1:
        st.plotly_chart(charts.funnel_bars(rf), width="stretch",
                        config={"displayModeBar": False})

        # 획득 퍼널 표와 같은 구성 — cum_rate/step_rate를 표시용 사본에서만 ×100.
        rf_disp = rf.assign(cum_rate=rf["cum_rate"] * 100,
                            step_rate=rf["step_rate"] * 100)
        st.dataframe(
            rf_disp,
            hide_index=True,
            column_order=["label", "n", "step_rate", "cum_rate", "drop",
                          "is_bottleneck"],
            column_config={
                "label": st.column_config.TextColumn("단계"),
                "n": st.column_config.NumberColumn("인원수", format="%,d"),
                "step_rate": st.column_config.NumberColumn(
                    "직전 단계 대비 유지율", format="%.1f%%"),
                "cum_rate": st.column_config.ProgressColumn(
                    "누적 잔류율", format="%.1f%%",
                    min_value=float(rf_disp["cum_rate"].min()),
                    max_value=float(rf_disp["cum_rate"].max())),
                "drop": st.column_config.NumberColumn("감소 인원", format="%,d"),
                "is_bottleneck": st.column_config.CheckboxColumn("병목 구간"),
            },
        )
    with c2:
        ui.callout(
            "유지는 <b>관측 기간이 대상마다 다릅니다.</b> "
            "먼저 들어온 대상은 오래 관측됐고 나중에 들어온 대상은 짧게 관측됐습니다. "
            "<b>누적값으로 비교하면 기간의 그림자를 효과로 착각합니다.</b> "
            "비율(단위 기간당)로 바꾸거나 같은 시점에 시작한 것끼리 묶으십시오.",
            "info")


tab_acq, tab_ret = st.tabs(["획득 퍼널", "유지 퍼널"])
with tab_acq:
    ui.section("획득 퍼널", "그레인을 먼저 확인한다")
    f = ui.guard(M.funnel, t["HR_직원"], t["HR_퇴사이력"])
    if f is not None:
        bn = f[f.is_bottleneck].iloc[0]
        bi = max(int(f.index[f.label == bn.label][0]), 1)
        left, right = st.columns([1.15, 1])
        with left:
            _render_acquisition_funnel(f)
        with right:
            _render_decomposition(t, f, bi)
with tab_ret:
    ui.section("유지 퍼널", "데려온 대상이 남는가")
    _render_retention_funnel(t)

@st.dialog("이 값을 왜 보여주지 않나")
def _why_hidden_dialog(n_total: int) -> None:
    # 표본 수·최소 기준값만 보여준다. 지표 값·증감·p값은 절대 넣지 않는다 —
    # 판단 기준②(계산 자체를 안 한다)를 이 모달에서도 그대로 지킨다.
    st.table(pd.DataFrame([
        {"항목": "걸린 조건", "내용": "표본 부족"},
        {"항목": "실제 표본 수", "내용": f"{n_total}건"},
        {"항목": "최소 기준값", "내용": f"{C.MIN_SAMPLE}건"},
    ]).set_index("항목"))
    st.caption(f"표본이 {C.MIN_SAMPLE}건 이상 모이면 지표 값을 계산해 보여줍니다.")


# ── 실험 ──────────────────────────────────────────────────────────
ui.section("실험 결과", "믿을 수 있는지 먼저 보고, 그 다음에 지표를 본다")
res = ui.guard(M.experiment_results, t)
if res is not None and not res:
    # 실험이 없어 monthly() 전후 비교 카드로 대신한다 — 인과는 주장하지
    # 않는다. 실험 카드와 같은 .exp 스타일·config.COLORS를 그대로 쓴다.
    v = ui.guard(M.monthly_verdict, t)
    if v is not None:
        cls = v["color"]
        head = (
            f'<div class="exp {cls}">'
            f'<div style="display:flex;align-items:flex-start;gap:12px">'
            f'<div style="flex:1"><div class="id">전후 비교 · 인과 주장 불가</div>'
            f'<div class="nm">{C.PRIMARY_METRIC} ↑ → {C.GUARDRAIL_METRIC} 가드레일</div>'
            f'<div class="hy">실험이 없어 monthly() 월별 추이로 대신합니다. '
            f'배정이 없어 인과는 주장할 수 없고, 상관만 봅니다.</div></div>'
            f'<div>{ui.badge(cls, v["verdict"])}</div></div>')
        if v["verdict"] == "무효":
            head += (f'<div class="blocked"><b>✕ 지표를 표시하지 않습니다</b><br>'
                     f'{v["reason"]}</div>')
        else:
            p, g = v["primary"], v["guard"]
            head += (
                f'<div style="margin-top:14px;display:flex;gap:28px;'
                f'align-items:baseline;flex-wrap:wrap">'
                f'<div><div style="font-size:11px;color:#64748b">{p["name"]}</div>'
                f'<div class="mv">{p["prev"]:,.0f} → {p["now"]:,.0f} '
                f'({p["pct"]:+.1f}%)</div></div>'
                f'<div><div style="font-size:11px;color:#64748b">{g["name"]}</div>'
                f'<div class="mv">{g["prev"]:.1f} → {g["now"]:.1f}시간 '
                f'({g["pct"]:+.1f}%)</div></div></div>')
            if v["reason"]:
                head += (f'<div style="margin-top:10px;font-size:13px;color:#64748b">'
                         f'{v["reason"]}</div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)

        # 지표 이름 옆 "정의" — 계산식·임계값 근거를 짧게. 감춰졌든 아니든
        # 항상 보여준다(값이 아니라 정의라 판단 기준②에 안 걸린다).
        d1, d2 = st.columns(2)
        with d1:
            st.caption(C.PRIMARY_METRIC)
            with st.popover("정의"):
                st.markdown(
                    f"**계산식**: monthly()의 그 달 말 재직 중인 사번 수.\n\n"
                    f"**임계값**: 전월 대비 {C.PRIMARY_MOVE_PCT:.0f}% 이상 증가 "
                    f"— monthly() 실측 변동폭(평소 최대 1.5%)보다 확실히 크게 "
                    f"잡음(config.py 근거 주석).")
        with d2:
            st.caption(C.GUARDRAIL_METRIC)
            with st.popover("정의"):
                st.markdown(
                    f"**계산식**: monthly()의 그 달 HR_근태 초과근무시간 평균.\n\n"
                    f"**임계값**: 같은 기간 {C.GUARDRAIL_MOVE_PCT:.0f}% 이상 증가"
                    f"(악화) — 평소 최대 3.6%보다 확실히 크게 잡음"
                    f"(config.py 근거 주석).")

        if v["verdict"] == "무효" and st.button("왜 감췄나?", key="why_hidden"):
            _why_hidden_dialog(v["n_total"])

        # 판정 과정 — 접힌 채로 시작해 결과(위 카드)가 먼저 보이게 하고,
        # 펼치면 어디서 갈렸는지 순서대로 남긴다. 못 믿을 조건에 걸리면
        # 2)·3)에 값을 넣지 않는다 — 판단 기준②(계산해 놓고 숨기는 게
        # 아니라 계산 자체를 안 한다)를 로그에서도 그대로 지킨다.
        with st.status("판정 과정", expanded=False) as box:
            if v["verdict"] == "무효":
                st.write(f"1) 못 믿을 조건 확인 — 걸림: {v['reason']}")
                st.write("2) 주지표 — 계산하지 않음")
                st.write("3) 가드레일 — 계산하지 않음")
            else:
                p, g = v["primary"], v["guard"]
                st.write("1) 못 믿을 조건 확인 — 통과")
                p_ok = p["pct"] >= C.PRIMARY_MOVE_PCT
                st.write(
                    f"2) 주지표({p['name']}) — {p['prev']:,.0f}명 → "
                    f"{p['now']:,.0f}명 ({p['pct']:+.1f}%) — "
                    f"기준({C.PRIMARY_MOVE_PCT:.0f}% 이상) "
                    + (f"충족" if p_ok
                       else f'미달 → 여기서 "{v["verdict"]}" 확정'))
                if p_ok:
                    g_bad = g["pct"] >= C.GUARDRAIL_MOVE_PCT
                    st.write(
                        f"3) 가드레일({g['name']}) — {g['prev']:.1f}시간 → "
                        f"{g['now']:.1f}시간 ({g['pct']:+.1f}%) — "
                        f"기준({C.GUARDRAIL_MOVE_PCT:.0f}% 이상) "
                        + (f'악화 → "{v["verdict"]}" 확정' if g_bad
                           else f'미달 → "{v["verdict"]}" 확정'))
                else:
                    st.write(
                        f"3) 가드레일({g['name']}) — {g['prev']:.1f}시간 → "
                        f"{g['now']:.1f}시간 ({g['pct']:+.1f}%) — "
                        f"2번에서 이미 판정이 끝나 반영되지 않음")
            box.update(label=f"판정 과정 — {v['verdict']}",
                      state="error" if v["verdict"] == "무효" else "complete")
    st.caption("실험이 없습니다. 위 카드는 전후 비교이며 "
               "**인과를 주장할 수 없습니다**.")
for r in (res or []):
    cls = r["color"]
    head = (f'<div class="exp {cls}">'
            f'<div style="display:flex;align-items:flex-start;gap:12px">'
            f'<div style="flex:1"><div class="id">{r["id"]}</div>'
            f'<div class="nm">{r["name"]}</div>'
            f'<div class="hy">{r["hypothesis"]}</div></div>'
            f'<div>{ui.badge(cls, r["verdict"])}</div></div>')

    if r["verdict"] == "무효":
        # 못 믿을 실험의 숫자는 보여주지 않는다.
        # 계산해 놓고 숨기는 것이 아니라 계산 자체를 하지 않았다.
        head += (f'<div class="blocked"><b>✕ 지표를 표시하지 않습니다</b><br>'
                 f'{r["reason"]}</div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)
        continue

    if "rc" not in r:
        head += (f'<div style="margin-top:12px;font-size:13px;color:#64748b">'
                 f'{r.get("reason", "")}</div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)
        continue

    head += (f'<div style="margin-top:14px;display:flex;gap:28px;'
             f'align-items:baseline;flex-wrap:wrap">'
             f'<div><div style="font-size:11px;color:#64748b">{r["primary"]}</div>'
             f'<div class="mv">{r["rc"]*100:.2f}% → {r["rt"]*100:.2f}%</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">상대 효과</div>'
             f'<div class="mv">{r["lift"]*100:+.1f}%</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">p값</div>'
             f'<div class="mv">{r["p"]:.4f}</div></div>'
             f'<div><div style="font-size:11px;color:#64748b">표본</div>'
             f'<div style="font-size:13px;color:#475569" class="num">'
             f'{r["nc"]:,} / {r["nt"]:,}</div></div></div>')
    st.markdown(head + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1.1])
    with c1:
        st.caption("효과 크기와 95% 신뢰구간 (0을 지나면 유의하지 않음)")
        st.plotly_chart(charts.forest(r), width="stretch",
                        config={"displayModeBar": False}, key=f"fr_{r['id']}")
    with c2:
        if r.get("guard"):
            gd = r["guard"]
            bad = gd["delta"] < -0.03
            st.markdown(
                f'<div class="card tight" style="border-color:'
                f'{C.COLORS["warn"] if bad else C.BRAND["line"]}">'
                f'<div style="font-size:11px;color:#64748b">가드레일 · {gd["name"]}</div>'
                f'<div style="font-size:20px;font-weight:700;margin-top:4px" class="num">'
                f'{gd["control"]*100:.1f}% → {gd["treatment"]*100:.1f}% '
                f'<span style="color:{C.COLORS["warn"] if bad else C.COLORS["ok"]}">'
                f'({gd["delta"]*100:+.1f}%p)</span></div>'
                + ('<div class="note">주지표는 개선됐지만 가드레일이 무너졌습니다.</div>'
                   if bad else
                   '<div style="font-size:12px;color:#64748b;margin-top:6px">'
                   '이상 없음</div>')
                + '</div>', unsafe_allow_html=True)
        elif r.get("reason"):
            st.markdown(f'<div class="card tight">'
                        f'<div style="font-size:13px;color:#64748b">{r["reason"]}</div>'
                        f'</div>', unsafe_allow_html=True)

    # 기간을 쪼개야 드러나는 것 — 초기 효과가 남아 있는가
    w = M.weekly_effect(r, r["start"])
    if not w.empty and len(w) >= 3:
        with st.expander("기간을 쪼개서 보기 — 효과가 유지되는가"):
            st.plotly_chart(charts.effect_decay(w), width="stretch",
                            config={"displayModeBar": False})
            ui.callout(
                f"전체 평균은 <b>{r['lift']*100:+.1f}%</b>인데 "
                f"초반 <b>{w.lift.iloc[0]*100:+.0f}%</b>에서 "
                f"후반 <b>{w.lift.iloc[-1]*100:+.0f}%</b>로 갑니다. "
                f"기간 평균만 보면 안 보이는 것입니다.")

    # 그때 멈췄다면 무엇을 봤을까
    pc = M.peeking_curve(r, r["start"])
    if not pc.empty and len(pc) >= 3:
        with st.expander("만약 여기서 멈췄다면? — 조기 중단 시뮬레이터"):
            cuts = list(pc.cut.astype(int))
            sel = st.select_slider("실험 종료일", options=cuts, value=cuts[0],
                                   key=f"peek_{r['id']}")
            row = pc[pc.cut == sel].iloc[0]
            a, b = st.columns([1, 1.4])
            with a:
                lv = "warn" if row.sig else "none"
                st.markdown(
                    ui.kpi_card(f"{sel}일차에 종료했다면", f"{row.lift*100:+.1f}%",
                                "유의 — 성공으로 보고" if row.sig
                                else "유의하지 않음", lv),
                    unsafe_allow_html=True)
                st.caption(f"p = {row.p:.3f}")
            with b:
                st.plotly_chart(charts.peeking(pc, r["lift"]), width="stretch",
                                config={"displayModeBar": False})
            ui.callout("종료 시점은 실험을 **시작하기 전에** 정해야 합니다.")

# ── 채널 효율 (선택 과제) ─────────────────────────────────────────
ui.section("획득 경로 효율", "비용만 보면 순위가 뒤집힌다")
ce = ui.guard(M.channel_efficiency, t)
if ce is not None and len(ce):
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.plotly_chart(charts.cac_compare(ce), width="stretch",
                        config={"displayModeBar": False})
    with c2:
        naive = list(ce.sort_values("CAC").channel)
        real = list(ce.sort_values("유효CAC").channel)
        st.markdown(
            f'<div class="card tight">'
            f'<div style="font-size:12px;color:#64748b">단순 비용 순위</div>'
            f'<div style="font-size:14px;margin:4px 0 12px">{" < ".join(naive)}</div>'
            f'<div style="font-size:12px;color:#64748b">유지율 반영 순위</div>'
            f'<div style="font-size:14px;font-weight:700;color:{C.COLORS["block"]}">'
            f'{" < ".join(real)}</div></div>', unsafe_allow_html=True)
        st.caption("비용은 가정값입니다. 리포트에 쓸 때 '가정값 기반'을 남기십시오.")
