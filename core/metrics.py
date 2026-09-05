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
def funnel_by(emp: pd.DataFrame, sep: pd.DataFrame, dim: str,
              step_from: str, step_to: str) -> pd.DataFrame:
    """차원별 특정 구간 전환율. 평균 하나로는 어디를 고칠지 모른다.

    dim 은 분해 축이다. **무엇으로 쪼갤지는 내가 정한다.**
    부서·직급·채용경로 — 손을 쓸 수 있는 축만 후보로 남겼다(내도메인.md
    명세대로 사번·날짜·재직상태는 후보에서 제외했다. 재직상태는 이 퍼널이
    측정하는 결과 그 자체라 이걸로 쪼개면 순환논리가 된다).

    쪼개는 기준은 이것이다: 그 축으로 나눴을 때 **손을 쓸 수 있는가.**
    나눠서 격차가 보여도 우리가 못 바꾸는 것이면 분해할 이유가 적다.

    HR_직원·HR_퇴사이력을 조인해 직원별 duration을 구하는 방식은 funnel()과
    같다 — 같은 조건인데 계산 방식이 갈리면 두 화면의 숫자가 어긋난다.
    다만 도달·전환은 funnel()처럼 KM으로 추정하지 않고, duration을
    step_from·step_to의 연차 기준선과 직접 비교한 **실측값**이다 — 세그먼트
    비교는 "그 연차를 이미 넘겼는가"를 실제로 알 수 있어 추정이 필요 없다.

        도달   duration이 step_from 연차 이상인 사번 수
        전환   그중 duration이 step_to 연차 이상인 사번 수(아직 재직 중이면
               그 연차를 못 넘겼을 뿐 — 왜 이탈했는지 물을 대상이 아니다)

    반환: DataFrame[<dim>, 도달, 전환, 전환율, 비중]
    """
    e = emp[["사번", "입사일", "재직상태", dim]].copy()
    e["입사일"] = to_dt(e["입사일"])
    s = sep[["사번", "퇴사일"]].copy()
    s["퇴사일"] = to_dt(s["퇴사일"])
    e = e.merge(s, on="사번", how="left")

    snapshot = pd.Timestamp(C.SNAPSHOT_DATE)
    e["종료일"] = e["퇴사일"].where(e["재직상태"] != "재직", snapshot)
    e["duration"] = (e["종료일"] - e["입사일"]).dt.days / 365.25

    y_from = FUNNEL_STEP_YEARS[step_from]
    y_to = FUNNEL_STEP_YEARS[step_to]
    reached = e[e["duration"] >= y_from].copy()
    reached["전환"] = reached["duration"] >= y_to

    g = reached.groupby(dim, observed=True)["전환"].agg(["size", "sum"])
    g.columns = ["도달", "전환"]
    g["전환율"] = g["전환"] / g["도달"]
    g["비중"] = g["도달"] / g["도달"].sum()
    return g.reset_index()


# ── 유지 퍼널 ─────────────────────────────────────────────────────
# config.RETENTION_STEPS 의 단계 -> 요구되는 최소 연속 개월 수.
RETENTION_STEP_MONTHS = {"상위진입": 1, "2개월연속": 2, "3개월연속": 3}


@st.cache_data(show_spinner=False)
def retention_funnel(t: dict) -> pd.DataFrame:
    """유지 퍼널. config.RETENTION_STEPS 의 단계대로 센다.

    개념은 "초과근무 고부담 지속" — 어느 달에 초과근무시간이 상위 33% 기준선
    (config.OVERTIME_TOP33_HOURS)을 넘으면 그 달을 "상위진입"으로 표시하고,
    그 상태가 **연속된 달로** 몇 개월이나 이어지는지를 본다.

    그레인은 **사번 1건**이다(대상 × 기간이 아니라). "그 사번이 도달한
    최장 연속 상위진입 길이가 몇 개월인가"로 각 사번을 한 번만 센다 — 관측
    기간이 사번마다 다른데(재직 중 이탈 등) 월 개수를 누적으로 비교하면
    7주차에 겪은 생존 편향이 다시 나오므로, 절대 개월 수가 아니라 **최장
    연속 길이**라는 사번당 하나의 값으로 바꿔서 비교한다.

    "연속"은 데이터상 인접한 행이 아니라 **달력상 인접한 달**로 판정한다
    (HR_근태에 월이 비어 있으면 거기서 연속이 끊긴 것으로 본다).

    반환: DataFrame[step, label, n, step_rate, cum_rate, drop, is_bottleneck]

        n              그 단계 요구 연속 개월 수 이상을 달성한 사번 수
        step_rate      직전 단계 달성자 중 이번 단계도 달성한 조건부 비율
        cum_rate       전체 사번(HR_근태에 있는 전원) 대비 이 단계 달성 비율
        drop           전 단계 대비 인원 감소분
        is_bottleneck  step_rate 가 가장 낮은 구간이면 True
    """
    a = t["HR_근태"][["사번", "년월", "초과근무시간"]].copy()
    a["ord"] = pd.PeriodIndex(a["년월"].astype(str), freq="M").asi8
    a = a.sort_values(["사번", "ord"])
    a["상위진입"] = a["초과근무시간"] >= C.OVERTIME_TOP33_HOURS

    # 상위진입이 아니거나, 직전 행과 달이 안 이어지면(결측월) 새 구간 시작
    gap = a.groupby("사번", observed=True)["ord"].diff() != 1
    new_run = (~a["상위진입"]) | gap
    a["run_id"] = new_run.groupby(a["사번"], observed=True).cumsum()

    run_len = (a[a["상위진입"]].groupby(["사번", "run_id"], observed=True)
               .size())
    longest = run_len.groupby("사번", observed=True).max()
    all_emp = a["사번"].unique()
    longest = longest.reindex(all_emp, fill_value=0)
    n_total = len(all_emp)

    rows = []
    prev_n = None
    for step, _cond in C.RETENTION_STEPS:
        need = RETENTION_STEP_MONTHS[step]
        n = int((longest >= need).sum())
        rows.append({
            "step": step,
            "label": step,
            "n": n,
            "step_rate": (n / prev_n) if prev_n else np.nan,
            "cum_rate": n / n_total,
        })
        prev_n = n

    f = pd.DataFrame(rows)
    f["drop"] = f["n"].diff().fillna(0).mul(-1).astype(int)
    rates = f["step_rate"].dropna()
    f["is_bottleneck"] = False
    if len(rates):
        f.loc[rates.idxmin(), "is_bottleneck"] = True
    return f


# HR_평가.평가등급 -> 점수 환산. 지표정의서.md "4. 평가점수" 그대로.
GRADE_SCORE = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}


def _eval_score_by_emp(ev: pd.DataFrame) -> pd.Series:
    """사번별 평가점수 평균. 등급을 점수로 바꾼 뒤 사번별로 평균 낸다(분기 수가
    사번마다 달라 — 재직 기간만큼만 있음 — 전체를 그냥 평균 내면 분기 많은
    사번에 가중치가 더 실린다. 지표정의서.md ②정의를 그대로 따른다)."""
    s = ev["평가등급"].map(GRADE_SCORE).astype(float)
    return s.groupby(ev["사번"], observed=True).mean()


# ── KPI ───────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def kpis(t: dict) -> dict:
    """지표 카드. 4개 — 내도메인.md 명세3행·4행, 지표정의서.md 4번을 따른다.

        규모       재직인원          HR_직원.재직상태='재직' 인원 수
        전환       입사1년내이탈률    **초과근무 상위 1/3 구간**(사번별 전체
                                    기간 평균 초과근무시간이 상위 33% 기준선을
                                    넘는 사번) 한정, KM 생존함수 기준 1년차
                                    누적 이탈률. 명세3·4행의 "주지표"·경고
                                    6%/위험 8% 임계값이 이 모집단(n≈100)
                                    기준으로 잡혀 있어 전사 전체가 아니라
                                    이 구간으로 계산한다(사용자 확인).
        품질/가드레일 평균평가점수    재직자만, 등급→점수 환산 후 사번별 평균의 평균
                                    (지표정의서.md 4번)
        부작용     월평균초과근무시간  monthly()의 가장 최근 달 값을 그대로 씀(새로
                                    계산하지 않음). 전체 기간 원본 행을 그대로
                                    평균내면(구 방식) 사번마다 근태 기록 개월 수가
                                    달라(재직 기간이 짧을수록 적음) 근속이 긴
                                    사번에 가중치가 더 실리고, monthly()의 "지금"
                                    값과도 어긋난다(15.46 vs 15.52) — 카드가 "현재"
                                    라고 표시하는 값은 monthly()가 말하는 "현재"와
                                    같아야 한다.

    "입사1년내이탈률"과 별개로 "참고용_전사_입사1년내이탈률"(전사 300명 전체
    기준, 세그먼트 제한 없음)도 함께 돌려준다 — 나중에 두 값을 비교할 수
    있도록 버리지 않고 남겨 둔 것(사용자 지시).

    반환: {"지표이름": {"value": float, "unit": str, "fmt": str}}
    """
    emp = t["HR_직원"]
    sep = t["HR_퇴사이력"]
    n_active = int((emp["재직상태"] == "재직").sum())

    f_all = funnel(emp, sep)
    leave_1y_all = float(
        (1 - f_all.loc[f_all.step == "1년차_잔류", "cum_rate"].iloc[0]) * 100)

    avg_overtime_by_emp = (t["HR_근태"].groupby("사번", observed=True)
                            ["초과근무시간"].mean())
    top_ids = avg_overtime_by_emp[avg_overtime_by_emp
                                   > C.OVERTIME_TOP33_HOURS].index
    emp_top = emp[emp["사번"].isin(top_ids)]
    f_top = funnel(emp_top, sep)
    leave_1y_top = float(
        (1 - f_top.loc[f_top.step == "1년차_잔류", "cum_rate"].iloc[0]) * 100)

    active_ids = emp.loc[emp["재직상태"] == "재직", "사번"]
    ev_active = t["HR_평가"][t["HR_평가"]["사번"].isin(active_ids)]
    avg_score = float(_eval_score_by_emp(ev_active).mean())

    avg_overtime = float(monthly(t)["월평균초과근무시간"].iloc[-1])

    return {
        "재직인원": {"value": n_active, "unit": "명", "fmt": "{:,.0f}명"},
        "입사1년내이탈률": {"value": leave_1y_top, "unit": "%", "fmt": "{:.1f}%"},
        "참고용_전사_입사1년내이탈률": {"value": leave_1y_all, "unit": "%",
                              "fmt": "{:.1f}%"},
        "평균평가점수": {"value": avg_score, "unit": "점", "fmt": "{:.2f}점"},
        "월평균초과근무시간": {"value": avg_overtime, "unit": "시간",
                        "fmt": "{:.1f}시간"},
    }


@st.cache_data(show_spinner=False)
def monthly(t: dict) -> pd.DataFrame:
    """기간별 추이. kpis() 4개 중 월 단위로 자연스럽게 나뉘는 2개만 담는다.

    "재직인원" · "월평균초과근무시간" 만 포함한다.

        입사1년내이탈률  월별로 다시 넣으려면 그 달까지의 데이터로 KM을
                        다시 적합해야 한다(방법론 자체가 새로 필요) — 이번엔
                        빼고 kpis()의 스냅샷 값만 낸다.
        평균평가점수     HR_평가가 분기 단위라 월로 못 나눈다(지표정의서.md
                        "2025년 4개 분기만 존재").

    kpis() docstring이 허용한 대로("없는 지표는 빼면 된다") 나머지 둘은 뺐다
    — 화면 스파크라인은 monthly()에 없는 지표 이름은 그냥 안 그린다.

    반환: 인덱스가 기간("YYYY-MM"), 열이 지표인 DataFrame
    """
    emp = t["HR_직원"][["사번", "입사일", "재직상태"]].copy()
    emp["입사일"] = to_dt(emp["입사일"])
    sep = t["HR_퇴사이력"][["사번", "퇴사일"]].copy()
    sep["퇴사일"] = to_dt(sep["퇴사일"])
    emp = emp.merge(sep, on="사번", how="left")

    ot = t["HR_근태"][["사번", "년월", "초과근무시간"]].copy()
    months = sorted(ot["년월"].astype(str).unique())

    rows = []
    for ym in months:
        month_end = pd.Period(ym, freq="M").end_time.normalize()
        active = ((emp["입사일"] <= month_end)
                   & (emp["퇴사일"].isna() | (emp["퇴사일"] > month_end)))
        rows.append({
            "기간": ym,
            "재직인원": int(active.sum()),
            "월평균초과근무시간": float(ot.loc[ot["년월"].astype(str) == ym,
                                       "초과근무시간"].mean()),
        })
    return pd.DataFrame(rows).set_index("기간")


@st.cache_data(show_spinner=False)
def monthly_verdict(t: dict) -> dict:
    """주지표+가드레일 판정 카드. 실험이 없어 experiment_results() 대신
    monthly() 월별 추이로 전후 비교를 대신한다 — **배정이 없으니 인과는
    주장할 수 없고, 상관만 본다**(DESIGN.md §4-4).

    판정 순서(고정) — 순서가 이 함수의 전부다:

        1. 믿을 수 있는가(trust_check) — 아니면 여기서 끝, 계산하지 않는다
        2. 주지표(config.PRIMARY_METRIC)가 전월 대비
           config.PRIMARY_MOVE_PCT% 이상 늘었는가 — 아니면 "효과 없음"
        3. 가드레일(config.GUARDRAIL_METRIC)이 같은 기간
           config.GUARDRAIL_MOVE_PCT% 이상 늘었는가(나빠졌는가) —
           그러면 "주의 필요"
        4. 둘 다 통과하면 "성공"

    ★ 2번을 1번 통과 직후에 둔다. 1번(믿을 수 있다)을 통과했다고 곧장
    "성공"으로 가지 않는다 — 주지표가 실제로 안 움직였는데 성공이라
    부르면 안 되기 때문이다.

    반환: {"verdict", "color", "reason", "primary"?, "guard"?, "period"?, "n_total"?}
        color 는 config.COLORS 의 키(ok/warn/none/block) 그대로다.
        무효일 때만 primary·guard·period가 없다 — 계산 자체를 안 했기 때문이다.
        period는 {"prev", "now"} — monthly()가 비교한 두 기간(m.index)을
        그대로 담는다. "전월 대비"가 실제로 어느 두 달인지 문장에 밝히는 데 쓴다.
        n_total은 무효일 때만 있다 — "왜 감췄나" 화면이 지표 값 없이
        조건 값(표본 수·최소 기준)만 보여주는 데 쓴다.
    """
    n_total = int(t["HR_직원"].shape[0])
    reason = trust_check({"ok": True}, n_total)
    if reason:
        return {"verdict": "무효", "color": "block", "reason": reason,
                "n_total": n_total}

    m = monthly(t)
    period = {"prev": m.index[-2], "now": m.index[-1]}
    p_prev, p_now = m[C.PRIMARY_METRIC].iloc[-2], m[C.PRIMARY_METRIC].iloc[-1]
    g_prev, g_now = m[C.GUARDRAIL_METRIC].iloc[-2], m[C.GUARDRAIL_METRIC].iloc[-1]
    p_pct = float((p_now / p_prev - 1) * 100)
    g_pct = float((g_now / g_prev - 1) * 100)
    primary = {"name": C.PRIMARY_METRIC, "prev": float(p_prev),
               "now": float(p_now), "pct": p_pct}
    guard = {"name": C.GUARDRAIL_METRIC, "prev": float(g_prev),
             "now": float(g_now), "pct": g_pct}

    if p_pct < C.PRIMARY_MOVE_PCT:
        return {"verdict": "효과 없음", "color": "none", "primary": primary,
                "guard": guard, "period": period, "reason": (
                    f"{C.PRIMARY_METRIC}이 전월 대비 {p_pct:+.1f}%로 "
                    f"기준({C.PRIMARY_MOVE_PCT:.0f}% 이상)에 못 미칩니다.")}

    if g_pct >= C.GUARDRAIL_MOVE_PCT:
        return {"verdict": "주의 필요", "color": "warn", "primary": primary,
                "guard": guard, "period": period, "reason": (
                    f"{C.PRIMARY_METRIC}은 늘었지만 {C.GUARDRAIL_METRIC}도 "
                    f"{g_pct:+.1f}% 늘어 기준({C.GUARDRAIL_MOVE_PCT:.0f}% "
                    f"이상)에 걸렸습니다.")}

    return {"verdict": "성공", "color": "ok", "primary": primary,
            "guard": guard, "period": period, "reason": ""}


def status_of(name: str, value: float) -> str:
    """지표 값을 상태 색으로 판정한다. 임계값은 config.THRESHOLDS 에 있다.

    이 함수는 **그대로 쓴다.** 판정 규칙이지 도메인이 아니다.
    THRESHOLDS 가 비어 있으면 전부 "ok"로 나온다 — 채우면 색이 갈린다.
    """
    th = C.THRESHOLDS.get(name)
    if not th:
        return "ok"
    # ★ 높을수록 나쁜 지표. 내 지표 이름을 넣는다.
    higher_is_worse = {"이탈률", "이탈율", "해지율", "불량률", "반품률",
                       "입사1년내이탈률", "월평균초과근무시간"}
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
    """이 숫자를 믿을 수 있는가. **계산하기 전에** 묻는다.

    조건은 하나뿐이다 — 표본이 config.MIN_SAMPLE 미만이면 못 믿는다.
    배정(srm)·기간(days) 조건은 넣지 않았다. 실험 없음 + 위험집합이
    이미 다 MIN_SAMPLE 통과 확인됨 → 조건 1개로 충분(교안 원칙: 조건은
    하나뿐이어도 된다). srm·days는 experiment_results()와 시그니처를
    맞추려 남겨 뒀을 뿐 판정에는 쓰지 않는다.

    하나라도 걸리면 **사유 문자열**을 돌려준다(숫자를 반드시 넣는다 —
    "표본 부족"이 아니라 "표본 27건 (최소 30)"). 돌려주면
    experiment_results() 가 거기서 멈추고 **지표를 계산하지 않는다.**
    통과하면 None 을 돌려준다.

    반환: 못 믿을 이유(str, 실제 숫자 포함) 또는 None
    """
    if n_total < C.MIN_SAMPLE:
        return f"표본 {n_total}건 (최소 {C.MIN_SAMPLE})"
    return None


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
