# -*- coding: utf-8 -*-
"""지표 계산.

**지표의 정의는 위키가 원본이다.** 이 파일은 위키에 적힌 정의를 코드로 옮긴 것일 뿐,
여기서 정의를 새로 만들지 않는다. 정의가 바뀌면 위키를 먼저 고친다.

────────────────────────────────────────────────────────────────────
★ 이 파일에는 통신사 컬럼명이 박혀 있다.

  billing_amount · is_churned · acquisition_channel · visitor_id ...

config.py 를 다 바꿔도 여기서 깨진다. **깨지는 것이 정상이다.**
컬럼명을 하나씩 내 것으로 맞추는 것이 이식 작업의 절반이다. → DESIGN.md §4-6
────────────────────────────────────────────────────────────────────

계산은 전부 pandas로 한다. 어디서 읽어왔든 입력은 동일한 DataFrame이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from lifelines import KaplanMeierFitter
from scipy import stats

from core import config as C
from core.load import to_dt
from core.todo import todo


# ── 퍼널 ──────────────────────────────────────────────────────────
# 연차 단계 -> 필요 연수. config.FUNNEL_STEPS 순서와 맞춰 둔다.
FUNNEL_STEP_YEARS = {"입사": 0, "1년차_잔류": 1, "3년차_잔류": 3,
                     "5년차_잔류": 5, "10년차_잔류": 10}


@st.cache_data(show_spinner=False)
def funnel(emp: pd.DataFrame, sep: pd.DataFrame) -> pd.DataFrame:
    """연차별 잔류 퍼널. Kaplan-Meier 생존함수로 계산한다.

    그레인은 사번 1건 — 한 직원이 같은 연차를 두 번 밟지 않는다.
    다만 재직 중인 직원은 아직 사건(퇴사)이 관측되지 않은 **중도절단**이라,
    이들을 그냥 "생존"으로 세면(=이전 방식) 우측절단 편향이 생긴다.
    Kaplan-Meier는 중도절단을 표본에서 빼지 않고 위험집합에 반영해 이 편향을 없앤다.

    HR_직원(사번, 입사일, 재직상태)과 HR_퇴사이력(사번, 퇴사일)을 조인해
    직원별 종료일을 만든다 — 재직 중이면 config.SNAPSHOT_DATE, 퇴사했다면 퇴사일.
    실행 시점(pd.Timestamp.now())을 쓰지 않는 이유는 그러면 앱을 돌릴 때마다
    재직자의 근속연수가 달라져 재현이 안 되기 때문이다 — 데이터가 끝나는
    시점(PERIOD의 끝)에 고정한다.

        duration        (종료일 - 입사일) 년 단위, 365.25로 나눈 값
        event_observed  퇴사이력에 있으면 1(사건 관측), 재직 중이면 0(중도절단)

    KaplanMeierFitter.fit(duration, event_observed) 로 생존함수 S(t)를 적합하고,
    survival_function_at_times([1, 3, 5, 10]) 로 연차별 누적 생존율을 읽는다.

    반환: DataFrame[step, label, n, step_rate, cum_rate, drop, is_bottleneck]

        step           config.FUNNEL_STEPS 의 값
        label          config.FUNNEL_LABELS 의 값 (화면 표시용)
        n              S(t) × 전체 코호트 규모를 반올림한 **추정 인원**.
                       중도절단이 섞여 있어 실제 헤드카운트가 아니다.
        step_rate      직전 연차까지 살아남은 사람 중 이번 연차까지도
                       살아남은 조건부 비율 = S(t) / S(t_prev) (첫 단계는 NaN)
        cum_rate       입사 시점(S(0)=1) 대비 누적 생존율 = S(t)
        drop           전 단계 대비 추정 인원 감소분
        is_bottleneck  step_rate 가 가장 낮은 구간이면 True
    """
    emp = emp[["사번", "입사일", "재직상태"]].copy()
    emp["입사일"] = to_dt(emp["입사일"])

    sep = sep[["사번", "퇴사일"]].copy()
    sep["퇴사일"] = to_dt(sep["퇴사일"])

    emp = emp.merge(sep, on="사번", how="left")
    snapshot = pd.Timestamp(C.SNAPSHOT_DATE)
    emp["종료일"] = emp["퇴사일"].where(emp["재직상태"] != "재직", snapshot)
    emp["duration"] = (emp["종료일"] - emp["입사일"]).dt.days / 365.25
    emp["event"] = emp["퇴사일"].notna().astype(int)

    kmf = KaplanMeierFitter()
    kmf.fit(durations=emp["duration"], event_observed=emp["event"])

    years = [FUNNEL_STEP_YEARS[step] for step in C.FUNNEL_STEPS]
    surv = kmf.survival_function_at_times(years)
    n_total = len(emp)

    rows = []
    base_s = None
    prev_s = None
    for step, y in zip(C.FUNNEL_STEPS, years):
        s = float(surv.loc[y])
        n = round(s * n_total)

        if base_s is None:
            base_s = s
        rows.append({
            "step": step,
            "label": C.FUNNEL_LABELS[step],
            "n": n,
            "step_rate": (s / prev_s) if prev_s else np.nan,
            "cum_rate": s / base_s,
        })
        prev_s = s

    f = pd.DataFrame(rows)
    f["drop"] = f["n"].diff().fillna(0).mul(-1).astype(int)
    rates = f["step_rate"].dropna()
    f["is_bottleneck"] = False
    if len(rates):
        f.loc[rates.idxmin(), "is_bottleneck"] = True
    return f


@st.cache_data(show_spinner=False)
def funnel_by(fe: pd.DataFrame, se: pd.DataFrame, dim: str,
              step_from: str, step_to: str) -> pd.DataFrame:
    """차원별 특정 구간 전환율. 평균 하나로는 어디를 고칠지 모른다.

    ★ Day3 실습 B에서 채웁니다.

    dim 은 분해 축이다. **무엇으로 쪼갤지는 내가 정한다.**
    기기·채널·지역·요금제·담당자·유입경로 — 도메인마다 다르다.

    쪼개는 기준은 이것이다: 그 축으로 나눴을 때 **손을 쓸 수 있는가.**
    나눠서 격차가 보여도 우리가 못 바꾸는 것이면 분해할 이유가 적다.

    반환: DataFrame[<dim>, 도달, 전환, 전환율, 비중]
    """
    todo("Day3 실습 B", "분해",
         "무엇으로 쪼갤지 정하십시오. 쪼개서 격차가 보이면 손을 쓸 수 있습니까?",
         "core/metrics.py  funnel_by()")


# ── 유지 퍼널 ─────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def retention_funnel(t: dict) -> pd.DataFrame:
    """유지 퍼널. config.RETENTION_STEPS 의 단계대로 센다.

    ★ Day2 실습 D에서 채웁니다.

    획득 퍼널과 다른 점 셋:

        단계    주어지지 않는다. **내가 정의한다**
        방향    한 방향이 아니다. 오갈 수 있다
        시간    며칠이 아니라 몇 달~몇 년

    그래서 그레인이 다르다. 획득은 **대상 하나**지만 유지는 흔히 **대상 × 기간**이다.
    같은 오류의 두 얼굴이다 — 그레인을 잘못 잡으면 둘 다 틀린다.

    **퍼널이 아니면 퍼널이라고 부르지 않는다.** 세 가지를 물어라.

        이 단계는 앞 단계를 반드시 거치는가?  아니면 그냥 분류다
        그레인이 무엇인가?
        기간을 어떻게 자르는가?

    그리고 **관측 기간이 다른 대상을 누적값으로 비교하지 않는다.**
    비교하려면 비율(단위 기간당)로 바꾸거나, 같은 시점에 시작한 것끼리 묶는다.
    7주차 토요일에 겪은 생존 편향이 여기서 다시 나온다.

    반환: DataFrame[step, label, n, step_rate, cum_rate]
    """
    todo("Day2 실습 D", "유지 퍼널",
         "7주차에 정한 유지·이탈의 정의를 config.RETENTION_STEPS 에 옮기고 "
         "그레인을 다시 확인하십시오.",
         "core/metrics.py  retention_funnel()")


# ── KPI ───────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def kpis(t: dict) -> dict:
    """지표 카드.

    ★ Day2 실습 E에서 채웁니다.

    ★ 아래 컬럼명은 전부 **통신사 것**이다. 내 데이터의 대응 컬럼으로 바꾼다.

        billing_amount  →  금액에 해당하는 컬럼
        is_churned      →  이탈 여부에 해당하는 컬럼

    없는 지표는 **빼면 된다.** 4개일 이유가 없다.

    반환: {"지표이름": {"value": float, "unit": str, "fmt": str}}
          fmt 은 화면 표시 형식이다. 예) "{:.2f}%"  "{:,.0f}원"

    예시 — 통신사:

        f = funnel(t["funnel_events"])
        return {
            "전환율": {"value": f.n.iloc[-1] / f.n.iloc[0] * 100,
                       "unit": "%", "fmt": "{:.2f}%"},
            "ARPU": {"value": float(t["usage_monthly"].billing_amount.mean()),
                     "unit": "원", "fmt": "{:,.0f}원"},
        }
    """
    todo("Day2 실습 E", "지표 카드",
         "내 데이터에서 금액·이탈에 해당하는 컬럼이 무엇입니까? 없는 지표는 빼십시오.",
         "core/metrics.py  kpis()")


@st.cache_data(show_spinner=False)
def monthly(t: dict) -> pd.DataFrame:
    """기간별 추이. 지표 카드의 스파크라인과 아카이브 비교에 쓴다.

    ★ Day2 실습 E에서 채웁니다. (kpis 와 함께)

    kpis() 가 돌려주는 지표 이름과 **열 이름이 대응**되어야 스파크라인이 그려진다.
    기간이 짧아 월별로 나눌 수 없으면 주별로 해도 되고, 아예 빼도 된다.

    반환: 인덱스가 기간(예 "2025-01"), 열이 지표인 DataFrame
    """
    todo("Day2 실습 E", "기간별 추이",
         "기간을 무엇으로 자릅니까? 월이 너무 길면 주로 자르십시오.",
         "core/metrics.py  monthly()")


def status_of(name: str, value: float) -> str:
    """지표 값을 상태 색으로 판정한다. 임계값은 config.THRESHOLDS 에 있다.

    이 함수는 **그대로 쓴다.** 판정 규칙이지 도메인이 아니다.
    THRESHOLDS 가 비어 있으면 전부 "ok"로 나온다 — 채우면 색이 갈린다.
    """
    th = C.THRESHOLDS.get(name)
    if not th:
        return "ok"
    # ★ 높을수록 나쁜 지표. 내 지표 이름을 넣는다.
    higher_is_worse = {"이탈률", "이탈율", "해지율", "불량률", "반품률"}
    if name in higher_is_worse:
        return ("block" if value > th["위험"]
                else "warn" if value > th["경고"] else "ok")
    return ("block" if value < th["위험"]
            else "warn" if value < th["경고"] else "ok")


# ── 실험 ──────────────────────────────────────────────────────────
# ★ 실험별로 어느 구간을 보는지. 도메인이 바뀌면 이 표를 갈아끼운다.
#   실험이 없는 도메인이면 비워 둔다.
EXP_STEPS: dict[str, tuple[str, str]] = {
    "EXP-001": ("랜딩방문", "요금제조회"),
    "EXP-002": ("요금제조회", "신청시작"),
    "EXP-003": ("신청시작", "신청완료"),
    "EXP-004": ("요금제조회", "신청시작"),
    "EXP-005": ("요금제조회", "신청시작"),
}


def _two_prop(sc, nc, stt, nt):
    """두 비율 비교. 차이·신뢰구간·p값을 함께 돌려준다.

    **그대로 쓴다.** 통계 계산은 도메인이 바뀌어도 같다.

    p값만 보면 '유의하지만 실질 효과가 없는' 경우를 놓친다.
    그래서 신뢰구간을 항상 함께 계산해 화면에 그린다.
    """
    rc, rt = sc / nc, stt / nt
    se = np.sqrt(rc * (1 - rc) / nc + rt * (1 - rt) / nt)
    if se == 0:
        return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=0, lo=0, hi=0, p=1.0, lift=0)
    z = (rt - rc) / se
    return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=rt - rc,
                lo=(rt - rc) - 1.96 * se, hi=(rt - rc) + 1.96 * se,
                p=2 * (1 - stats.norm.cdf(abs(z))),
                lift=(rt / rc - 1) if rc else 0)


def srm_check(asg: pd.DataFrame, exp_id: str) -> dict:
    """SRM(Sample Ratio Mismatch). 배정이 50:50인지 검정한다.

    **그대로 쓴다.** 7주차에 손으로 해본 그 계산이다.

    배정이 50:50이 아니면 배정 로직에 버그가 있다는 뜻이고,
    그 경우 어떤 효과가 나오든 해석할 수 없다.
    """
    a = asg[asg.experiment_id == exp_id]
    c = int((a.variant == "control").sum())
    t = int((a.variant == "treatment").sum())
    if c + t == 0:
        return {"ok": False, "c": 0, "t": 0, "p": 1.0, "ratio": (0.0, 0.0)}
    p = stats.chisquare([c, t]).pvalue
    return {"ok": p >= 0.001, "c": c, "t": t, "p": float(p),
            "ratio": (c / (c + t), t / (c + t))}


def trust_check(srm: dict, n_total: int, days: int | None = None) -> str | None:
    """이 실험을 믿을 수 있는가. **계산하기 전에** 묻는다.

    ★ Day3 실습 C에서 채웁니다. ← 오늘의 핵심

    ────────────────────────────────────────────────────────────
    오늘의 어려운 일은 계산이 아니다.
    **계산은 이미 할 수 있는데, 화면에 안 그리는 코드를 쓰는 것**이다.
    ────────────────────────────────────────────────────────────

    못 믿을 조건은 셋인데 **분기는 하나**다.

        배정이 깨졌다      srm["ok"] 가 False
                          → 어떤 효과가 나와도 해석할 수 없다
        표본이 모자란다    n_total 이 config.MIN_SAMPLE 미만
                          → 계산해도 못 믿는다. 내 데이터는 대개 여기 걸린다
        기간이 안 찼다     days 가 최소 기간 미만
                          → 초기 효과가 남아 있다

    하나라도 걸리면 **사유 문자열**을 돌려준다. 돌려주면
    experiment_results() 가 거기서 멈추고 **지표를 계산하지 않는다.**
    다 통과하면 None 을 돌려준다.

    "그래도 회색으로라도 보여주면 안 되나요?"

        안 됩니다. **사람은 본 숫자를 기억합니다.**
        옆에 아무리 경고를 붙여도 회의실에서 인용되는 것은 숫자입니다.

    반환: 못 믿을 이유(str) 또는 None
    """
    todo("Day3 실습 C", "못 믿을 조건 분기",
         "배정·표본·기간 셋 중 하나라도 걸리면 사유를 돌려주십시오. "
         "돌려주면 지표를 계산하지 않습니다.",
         "core/metrics.py  trust_check()")


@st.cache_data(show_spinner=False)
def experiment_results(t: dict) -> list[dict]:
    """실험 결과와 판정.

    **판정 순서가 이 함수의 전부다.** 믿을 수 있는지 먼저 묻고,
    믿을 수 있을 때만 계산한다.

    좋은 결과를 먼저 보면 경고를 무시하고 싶어진다. 그래서 사람의 규율에
    맡기지 않고 **코드로 순서를 박는다.**

    실험이 없는 도메인이면 이 함수는 빈 목록을 돌려준다. 대신 전후 비교
    카드를 만들되 **"인과 주장 불가"를 카드에 박아 둔다.** → DESIGN.md §4-4
    """
    if "experiments" not in t or "experiment_assignments" not in t:
        return []
    ex, asg, fe = t["experiments"], t["experiment_assignments"], t["funnel_events"]
    reach = {s: set(fe.loc[fe.funnel_step == s, "visitor_id"]) for s in C.FUNNEL_STEPS}
    out = []
    for _, e in ex.iterrows():
        eid = e.experiment_id
        srm = srm_check(asg, eid)
        n_total = int((asg.experiment_id == eid).sum())
        row = {
            "id": eid, "name": e.experiment_name, "hypothesis": e.hypothesis,
            "primary": e.primary_metric, "guardrail": e.guardrail_metric,
            "start": e.start_date, "end": e.end_date, "srm": srm,
        }

        # ★ 판정이 계산보다 먼저다. 못 믿으면 여기서 끝난다.
        reason = trust_check(srm, n_total)
        if reason:
            row["verdict"] = "무효"
            row["color"] = "block"
            row["reason"] = reason
            out.append(row)
            continue        # 지표를 계산하지 않는다. 숨기는 것이 아니다.

        # ── 여기부터 계산 ─────────────────────────────────────────
        if eid not in EXP_STEPS:
            row.update(verdict="데이터 없음", color="none",
                       reason="EXP_STEPS 에 이 실험의 구간이 없습니다.")
            out.append(row)
            continue
        sf, stp = EXP_STEPS[eid]
        a = asg[asg.experiment_id == eid][["visitor_id", "variant", "assigned_at"]]
        a = a[a.visitor_id.isin(reach[sf])]
        a = a.assign(conv=a.visitor_id.isin(reach[stp]).astype(int))
        g = a.groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(g) < 2:
            row.update(verdict="데이터 없음", color="none")
            out.append(row)
            continue
        r = _two_prop(g.loc["control", "sum"], g.loc["control", "count"],
                      g.loc["treatment", "sum"], g.loc["treatment", "count"])
        row.update(r, step_from=sf, step_to=stp, assignments=a)

        # 가드레일 — 주지표를 올리려 할 때 희생될 수 있는 것
        # ★ 아래는 통신사 컬럼(is_churned)이다. 내 가드레일 지표로 바꾼다.
        row["guard"] = None
        if "유지율" in str(e.guardrail_metric) and "customers" in t:
            cu = t["customers"]
            m = cu.merge(a[["visitor_id", "variant"]], on="visitor_id", how="inner")
            if len(m) and m.variant.nunique() == 2:
                ret = m.groupby("variant", observed=True).is_churned.mean()
                row["guard"] = {
                    "name": e.guardrail_metric,
                    "control": float(1 - ret["control"]),
                    "treatment": float(1 - ret["treatment"]),
                    "delta": float((1 - ret["treatment"]) - (1 - ret["control"])),
                }

        # 판정 — ★ 3%p 는 예시다. 내 가드레일 기준으로 바꾼다.
        sig = r["p"] < 0.05
        guard_bad = row["guard"] is not None and row["guard"]["delta"] < -0.03
        if guard_bad:
            # 주지표가 좋아져도 가드레일이 무너지면 성공이 아니다
            row.update(verdict="주의 필요", color="warn",
                       reason="주지표는 개선됐으나 가드레일이 악화됐습니다.")
        elif sig and r["lift"] > 0:
            row.update(verdict="성공", color="ok", reason="")
        elif sig:
            row.update(verdict="악화", color="block", reason="")
        else:
            row.update(verdict="효과 없음", color="none",
                       reason="통계적으로 유의한 차이가 없습니다.")
        out.append(row)
    return out


def peeking_curve(res: dict, start: str, cuts=(7, 14, 30, 60, 92)) -> pd.DataFrame:
    """관측 시점별 누적 결과. '그때 멈췄다면 무엇을 봤을까'를 재현한다.

    **그대로 쓴다.** 7주차에 겪은 조기 중단이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["d"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days
    rows = []
    for c in cuts:
        s = a[a.d <= c].groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(s) < 2 or s["count"].min() < 30:
            continue
        r = _two_prop(s.loc["control", "sum"], s.loc["control", "count"],
                      s.loc["treatment", "sum"], s.loc["treatment", "count"])
        rows.append({"cut": c, "lift": r["lift"], "p": r["p"], "sig": r["p"] < 0.05})
    return pd.DataFrame(rows)


def weekly_effect(res: dict, start: str, bucket_days: int = 14) -> pd.DataFrame:
    """기간을 쪼개 효과 추이를 본다. 신규성 효과는 전체 평균에 가려진다.

    **그대로 쓴다.** 7주차에 겪은 그것이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["b"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days // bucket_days
    g = (a[a.b >= 0].groupby(["b", "variant"], observed=True).conv
         .mean().unstack().dropna())
    if g.empty:
        return pd.DataFrame()
    g["lift"] = g.treatment / g.control - 1
    g = g.reset_index()
    g["label"] = g.b.apply(lambda i: f"{int(i)*2+1}~{int(i)*2+2}주")
    return g


# ── 채널 효율 (선택 과제) ─────────────────────────────────────────
@st.cache_data(show_spinner=False)
def channel_efficiency(t: dict) -> pd.DataFrame:
    """비용만 보면 순위가 뒤집힌다. 유지율까지 반영한 유효 비용을 함께 낸다.

    ★ Day3 선택 과제입니다. 안 만들어도 나머지가 돕니다.

    획득 비용이 싼 경로가 실제로 싼 것이 아니다 —
    데려온 대상이 남지 않으면 같은 자리를 다시 채워야 한다.

        유효 비용 = 획득 비용 / 유지율

    비용 개념이 없으면 **투입 공수(인시)**로 해도 된다.
    획득 경로 구분이 없으면 이 함수를 지운다.

    ★ 여기 쓰이는 CHANNEL_CAC 는 **가정값**이다. 광고비 실측 테이블에서
      유도하지 않는다 — 광고비는 개인 단위로 추적되지 않아 가입과 이을 수 없다.
      리포트에 이 값이 들어가면 "가정값 기반"을 문장에 남긴다. → DESIGN.md §4-3

    반환: DataFrame[채널, 방문, 가입, 전환율, CAC, 유지율, 유효CAC, 역전]
    """
    todo("Day3 선택 과제", "채널 효율",
         "내 도메인에 획득 경로 구분이 있습니까? 비용이 없으면 투입 공수로 바꾸십시오.",
         "core/metrics.py  channel_efficiency()")
