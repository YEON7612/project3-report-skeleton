# -*- coding: utf-8 -*-
"""대시보드 — 여기서 발견이 일어난다.

반복해서 보는 화면이므로 실행 절차를 지나치지 않고 바로 지표에 닿게 한다.

이 화면은 Day2~3에 걸쳐 살아난다.
  Day2  지표 카드 · 획득 퍼널 · 유지 퍼널
  Day3  분해 · 실험 카드
"""
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
    cols = st.columns(len(k))
    for col, (name, v) in zip(cols, k.items()):
        with col:
            lv = M.status_of(name, v["value"])
            st.markdown(ui.kpi_card(name, v["fmt"].format(v["value"]), "", lv),
                        unsafe_allow_html=True)
            # 추이가 있으면 스파크라인. 지표 이름과 열 이름이 같아야 그려진다.
            if m is not None and name in getattr(m, "columns", []):
                st.plotly_chart(
                    charts.spark(m[name], C.COLORS[lv] if lv != "ok" else None),
                    width="stretch", config={"displayModeBar": False},
                    key=f"sp_{name}")
    if not C.THRESHOLDS:
        st.caption("config.THRESHOLDS 가 비어 있어 전부 정상으로 표시됩니다. "
                   "임계값을 채우면 색이 갈립니다.")

# ── 획득 퍼널 ─────────────────────────────────────────────────────
ui.section("획득 퍼널", "그레인을 먼저 확인한다")
f = ui.guard(M.funnel, t["HR_직원"], t["HR_퇴사이력"])
if f is not None:
    left, right = st.columns([1.15, 1])
    with left:
        st.plotly_chart(charts.funnel_bars(f), width="stretch",
                        config={"displayModeBar": False})
        bn = f[f.is_bottleneck].iloc[0]
        bi = max(int(f.index[f.label == bn.label][0]), 1)
        prev = f.iloc[bi - 1]
        ui.callout(
            f"<b>병목은 {prev.label} → {bn.label}</b> 구간입니다. "
            f"{prev.n:,} 중 {bn.n:,}만 넘어가 "
            f"<b>{(1-bn.step_rate)*100:.1f}%가 이탈</b>합니다.")

    with right:
        # ★ Day3 — 분해 축. 내 데이터의 컬럼명으로 바꾼다.
        DIMS = ["device", "channel"]
        dim = st.radio("분해 축", DIMS, horizontal=True,
                       label_visibility="collapsed")
        i = st.selectbox(
            "구간", range(len(f) - 1),
            format_func=lambda i: f"{f.label.iloc[i]} → {f.label.iloc[i+1]}",
            index=min(bi - 1, len(f) - 2))
        g = ui.guard(M.funnel_by, t["funnel_events"], t["sessions"], dim,
                     f.step.iloc[i], f.step.iloc[i + 1])
        if g is not None and len(g):
            st.plotly_chart(charts.device_compare(g), width="stretch",
                            config={"displayModeBar": False})
            hi = g.loc[g.전환율.idxmax()]
            lo = g.loc[g.전환율.idxmin()]
            if hi[g.columns[0]] != lo[g.columns[0]]:
                ui.callout(
                    f"<b>{lo[g.columns[0]]}</b>이(가) 전체의 "
                    f"<b>{lo.비중*100:.1f}%</b>인데 전환율은 "
                    f"<b>{lo.전환율*100:.1f}%</b>로 "
                    f"{hi[g.columns[0]]}({hi.전환율*100:.1f}%)보다 "
                    f"<b>{(hi.전환율-lo.전환율)*100:.1f}%p 낮습니다.</b>")

# ── 유지 퍼널 ─────────────────────────────────────────────────────
ui.section("유지 퍼널", "데려온 대상이 남는가")
if not C.RETENTION_STEPS:
    st.caption("config.RETENTION_STEPS 가 비어 있습니다. "
               "7주차에 정한 유지·이탈의 정의를 옮기면 여기에 그려집니다.")
rf = ui.guard(M.retention_funnel, t)
if rf is not None and len(rf):
    if "is_bottleneck" not in rf.columns:
        rf = rf.assign(is_bottleneck=False)
    c1, c2 = st.columns([1.15, 1])
    with c1:
        st.plotly_chart(charts.funnel_bars(rf), width="stretch",
                        config={"displayModeBar": False})
    with c2:
        ui.callout(
            "유지는 <b>관측 기간이 대상마다 다릅니다.</b> "
            "먼저 들어온 대상은 오래 관측됐고 나중에 들어온 대상은 짧게 관측됐습니다. "
            "<b>누적값으로 비교하면 기간의 그림자를 효과로 착각합니다.</b> "
            "비율(단위 기간당)로 바꾸거나 같은 시점에 시작한 것끼리 묶으십시오.",
            "info")

# ── 실험 ──────────────────────────────────────────────────────────
ui.section("실험 결과", "믿을 수 있는지 먼저 보고, 그 다음에 지표를 본다")
res = ui.guard(M.experiment_results, t)
if res is not None and not res:
    st.caption("실험이 없습니다. 전후 비교로 대신하되 "
               "**인과를 주장할 수 없다**를 카드에 남기십시오.")
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
