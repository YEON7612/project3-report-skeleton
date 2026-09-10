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


# ── 최근 코호트 ───────────────────────────────────────────────────
# 화면에 보여줄 최근 코호트 개수. need_years가 1년이라 12개월이면 커버리지가
# ~8%(최신 달)에서 100%(1년 전 달)까지 걸쳐 있어 "관측 부족" 사례를 보여주는
# 목적에 맞는다 — 더 늘리면 이미 성숙한 달까지 같이 보여 화면이 늘어질 뿐이다.
RECENT_COHORT_MONTHS = 12


def _cohort_frame(emp: pd.DataFrame, sep: pd.DataFrame):
    """funnel()과 같은 조인·종료일 계산. 코호트(입사월) 열만 추가한다."""
    e = emp[["사번", "입사일", "재직상태"]].copy()
    e["입사일"] = to_dt(e["입사일"])
    s = sep[["사번", "퇴사일"]].copy()
    s["퇴사일"] = to_dt(s["퇴사일"])
    e = e.merge(s, on="사번", how="left")

    snapshot = pd.Timestamp(C.SNAPSHOT_DATE)
    e["종료일"] = e["퇴사일"].where(e["재직상태"] != "재직", snapshot)
    e["코호트"] = e["입사일"].dt.to_period("M")
    return e, snapshot


def _reach_rate(g: pd.DataFrame, term_col: str, need_years: float) -> tuple[int, float]:
    """이 그룹에서 term_col 기준 duration이 need_years 이상인 비율(%)."""
    dur = (g[term_col] - g["입사일"]).dt.days / 365.25
    reached = int((dur >= need_years).sum())
    n = len(g)
    return reached, (reached / n * 100 if n else np.nan)


@st.cache_data(show_spinner=False)
def recent_cohort_reach(emp: pd.DataFrame, sep: pd.DataFrame) -> dict:
    """최근 코호트 진단 — 코호트(입사월)별 실측 도달률과 관측커버리지를 그대로 보여준다.

    funnel()의 KM 추정은 전체 표본을 한 번에 본다. 이 표는 그것과 별개로,
    **코호트(입사월)별로** "이 코호트가 퍼널 첫 실제 단계(C.FUNNEL_STEPS[1] —
    지금은 "1년차_잔류")에 도달할 시간이 실제로 얼마나 지났는가"를 직접
    보여주는 진단용 표다. 새 임계값·새 그레인을 만들지 않는다 — 그레인은
    사번 1건(코호트 안에서), 기준 연차는 FUNNEL_STEP_YEARS를 그대로 쓴다.

        관측커버리지  = min((SNAPSHOT_DATE - 코호트월 첫날) / (기준연차×365.25일), 1.0) × 100.
                      최근에 입사한 코호트일수록 기준 연차(1년)가 아직 안
                      지나 이 값이 낮다 — 이탈이 아니라 **아직 그 나이에
                      이르지 않았을 뿐**이라는 뜻이다(funnel()이 KM으로
                      다루는 중도절단과 같은 문제를 코호트 단위로 단순화한
                      근사치).
        도달률       그 코호트 사번 중 duration(입사일→종료일, 년)이 기준
                      연차 이상인 비율. **실측값이며 보정하지 않는다.**

    ★ 처음엔 "도달률÷(관측커버리지/100)"로 선형 보정한 값을 냈었다. 백테스트로
      검증해 보니(성숙 코호트를 낮은 커버리지에서 관측한 것처럼 되짚어 실제
      최종값과 비교) 커버리지 수준과 무관하게 오차가 항상 ~100%에 가까웠다.
      원인은 버그가 아니라 이 지표의 성격이다 — "1년차_잔류"는 관측 기간
      내내 조금씩 쌓이는 지표가 아니라 **문턱값형(all-or-nothing)** 지표라,
      코호트 전체가 실제로 1년을 채우기 전까지는 도달률이 0%에 머물다가
      한꺼번에 뛴다. 이런 지표에 선형 보정을 적용하면 항상 과소추정된
      값(대개 0%)이 나와 의미가 없다. 억지로 다른 보정 공식을 새로 만들지
      않고, 보정 자체를 뺐다(판단기준.md 참고).

    ★ 표본이 C.MIN_SAMPLE 미만인 코호트는 trust_check()에 걸려 판정하지
      않는다 — 사유만 있고 도달률·관측커버리지 수치는 화면에서 뺀다
      (pages/2_대시보드.py가 funnel_by() 분해 표에 이미 쓰는 것과 같은
      마스킹 방식).

    판정:
        무효      trust_check() 표본부족
        관측부족  관측커버리지<100 — 좋다/나쁘다 방향 없이 "아직 판단하기엔
                  이르다"는 사실만 표시한다
        (빈 문자열) 관측커버리지=100·표본 충분 — 실측 도달률을 판정 없이
                  그대로 보여준다(보정도 비교 대상도 없으니 색을 넣지 않는다)

    반환: {"recent": DataFrame(최근 RECENT_COHORT_MONTHS개 코호트),
           "reach_step": str, "need_years": float}
    """
    e, snapshot = _cohort_frame(emp, sep)

    reach_step = C.FUNNEL_STEPS[1]
    need_years = FUNNEL_STEP_YEARS[reach_step]
    need_days = need_years * 365.25

    rows = []
    for co, g in e.groupby("코호트", observed=True):
        cohort_start = co.to_timestamp()
        elapsed_days = max((snapshot - cohort_start).days, 0)
        coverage = min(elapsed_days / need_days, 1.0) * 100
        reached, raw_rate = _reach_rate(g, "종료일", need_years)
        rows.append({
            "코호트": str(co), "코호트_ts": cohort_start, "n": len(g),
            "도달": reached, "도달률": raw_rate, "관측커버리지": coverage,
        })
    full = pd.DataFrame(rows).sort_values("코호트_ts").reset_index(drop=True)
    recent = full.tail(RECENT_COHORT_MONTHS).copy()

    verdicts, reasons, colors = [], [], []
    for _, row in recent.iterrows():
        reason = trust_check({"ok": True}, int(row["n"]))
        if reason:
            verdicts.append("무효"); reasons.append(reason)
            colors.append(C.COLORS["block"])
        elif row["관측커버리지"] < 100 - 1e-9:
            verdicts.append("관측부족")
            reasons.append("아직 판단하기엔 이르다")
            colors.append(C.COLORS["none"])
        else:
            verdicts.append(""); reasons.append(""); colors.append(None)
    recent["판정"] = verdicts
    recent["사유"] = reasons
    recent["색"] = colors

    return {"recent": recent, "reach_step": reach_step, "need_years": need_years}


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


@st.cache_data(show_spinner=False)
def quarterly_eval_score(t: dict) -> pd.Series:
    """평균평가점수의 분기별 추이. HR_평가가 분기 단위라 monthly()에 못 넣고
    따로 낸다(monthly() docstring과 같은 이유).

    kpis()의 "평균평가점수"와 모집단은 같다 — 지금 재직 중인 사번만. 다만
    kpis()는 그 사번들의 4개 분기 점수를 전부 평균해 **하나의 값**으로
    합치고, 이 함수는 분기마다 따로 평균 낸다 — 그래서 kpis() 값과 이
    시리즈의 마지막 분기 값이 다를 수 있다(둘 다 맞다, 합치는 범위가 다를
    뿐이다 — 월평균초과근무시간을 "전체기간 평균"과 "이번 달"로 갈랐던 것과
    같은 문제라, 화면에서 대시보드 카드 값(4분기 통합)과 스파크라인(분기별)이
    서로 다른 것을 잰다는 점을 캡션에 밝힌다).

    반환: 인덱스가 분기("2025Q1" 등), 값이 그 분기 평균점수인 Series
    """
    emp = t["HR_직원"]
    active_ids = emp.loc[emp["재직상태"] == "재직", "사번"]
    ev = t["HR_평가"]
    ev_active = ev[ev["사번"].isin(active_ids)].copy()
    ev_active["점수"] = ev_active["평가등급"].map(GRADE_SCORE).astype(float)
    return (ev_active.groupby("분기", observed=True)["점수"]
            .mean().sort_index())


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


# ── 제안 주제 후보 ────────────────────────────────────────────────
# 추세(④)에서 "최근 N개월 평균 vs 직전 N개월"의 N. RECENT_COHORT_MONTHS와
# 같은 성격의 그레인 선택이라 config가 아니라 여기 둔다 — monthly()가
# 15개월치(config.PERIOD)라 3(분기 단위)을 써도 비교에 6개월만 쓰고 9개월치
# 여유가 남는다. monthly_verdict()가 이미 하는 "전월 대비"(1개월) 비교와는
# 다른, 더 완만한 추세를 보려는 목적이라 1이 아니라 3으로 뒀다.
TREND_WINDOW_MONTHS = 3


def _swing_pp(n: int) -> float:
    """표본 n에서 1건이 바뀔 때 흔들리는 폭(%p) = 100/n. 새 공식이 아니다 —
    판단기준.md(2026-09-08) "표본 한 건이 바뀌면 얼마나 흔들리는가"를 그대로
    쓴다. n이 0이면 비교 자체가 안 되므로 무한대를 돌려준다(항상 기각).
    """
    return 100.0 / n if n else float("inf")


def _period_years() -> float:
    """config.PERIOD 길이(년). 여기서만 계산하고 datetime.now()는 쓰지
    않는다 — 앱을 언제 켜도 같은 값이 나와야 한다."""
    start, end = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    return (end - start).days / 365.25


def _topic_funnel_gaps(f: pd.DataFrame, key: str, label: str,
                        n_total: int, years: float) -> list[dict]:
    """퍼널 하나(f) 안에서 "전환율이 가장 낮은 구간 vs 그다음으로 낮은
    구간"의 격차 후보 하나를 만든다. trust_check()에 걸리는 구간은 비교
    대상에서 아예 뺀다(못 믿을 조건 — 후보 자체를 안 만든다). 남은 구간이
    2개 미만이면 비교할 게 없어 후보가 없다.
    """
    ranked = f[f["step_rate"].notna()].copy()
    ranked["_못믿음"] = ranked["n"].apply(
        lambda n: trust_check({"ok": True}, int(n)) is not None)
    ranked = ranked[~ranked["_못믿음"]].sort_values("step_rate")
    if len(ranked) < 2:
        return []

    worst, second = ranked.iloc[0], ranked.iloc[1]
    gap_frac = float(second["step_rate"] - worst["step_rate"])
    gap_pp = gap_frac * 100
    비중 = float(worst["drop"]) / n_total if n_total else 0.0
    raw_count = float(worst["drop"])
    연간_건수 = raw_count / years if years else 0.0
    규모 = gap_frac * 비중 * 연간_건수

    prev_idx = f.index.get_loc(worst.name) - 1
    구간 = (f"{f['step'].iloc[prev_idx]}→{worst['step']}"
           if prev_idx >= 0 else str(worst["step"]))

    swing = _swing_pp(int(worst["n"]))
    기각 = (f"흔들림 ±{swing:.2f}%p ≥ 격차 {gap_pp:.2f}%p(표본 {int(worst['n'])}건)"
          if gap_pp < swing else "")

    return [{
        "키": f"funnel_gap:{key}:{worst['step']}",
        "제목": f"{label} '{worst['label']}' 구간 전환율이 가장 낮다",
        "한줄": (f"{label} 단계 전환율: {worst['label']} {worst['step_rate']*100:.2f}% "
               f"vs 다음으로 낮은 {second['label']} {second['step_rate']*100:.2f}% "
               f"— 격차 {gap_pp:.2f}%p. 이 구간 감소 {int(worst['drop']):,}명"
               f"(전체 {n_total:,}명의 {비중*100:.1f}%)"),
        "규모_연간건수": 규모,
        "근거축": None,
        "구간": 구간,
        "기각사유": 기각,
    }]


def _topic_axis_gaps(emp: pd.DataFrame, sep: pd.DataFrame, step_from: str,
                      step_to: str, n_total: int, years: float) -> list[dict]:
    """config.FUNNEL_DIMS 각 축에서 "전환율 최고 칸 vs 최저 칸"의 격차
    후보를 축마다 하나씩 만든다. 구간은 획득 퍼널의 병목 구간(다른 화면·
    리포트가 이미 쓰는 것과 같은 구간)으로 고정한다 — 매번 다른 구간을
    보면 화면마다 숫자가 어긋난다.

    trust_check()에 걸리는 칸은 최고/최저 후보에서 뺀다. 기각 여부는 그
    축에서 가장 표본이 작은(가장 흔들리기 쉬운) 칸 기준으로 본다 —
    제안카드.md 제안8에서 쓴 것과 같은 축 전체 최악의 경우 검사다.
    """
    out = []
    for dim in C.FUNNEL_DIMS:
        g = funnel_by(emp, sep, dim, step_from, step_to)
        g = g.copy()
        g["_못믿음"] = g["도달"].apply(
            lambda n: trust_check({"ok": True}, int(n)) is not None)
        trustworthy = g[~g["_못믿음"]]
        if len(trustworthy) < 2:
            continue

        best = trustworthy.loc[trustworthy["전환율"].idxmax()]
        worst = trustworthy.loc[trustworthy["전환율"].idxmin()]
        if best[dim] == worst[dim]:
            continue
        gap_frac = float(best["전환율"] - worst["전환율"])
        gap_pp = gap_frac * 100
        비중 = float(worst["비중"])
        raw_count = float(worst["도달"])
        연간_건수 = raw_count / years if years else 0.0
        규모 = gap_frac * 비중 * 연간_건수

        min_n = int(trustworthy["도달"].min())
        swing = _swing_pp(min_n)
        기각 = (f"흔들림 ±{swing:.2f}%p ≥ 격차 {gap_pp:.2f}%p"
              f"(축 최소 표본 {min_n}건 기준)" if gap_pp < swing else "")

        out.append({
            "키": f"axis_gap:{dim}:{step_from}->{step_to}",
            "제목": f"'{dim}' 축, {step_from}→{step_to} 전환율 격차",
            "한줄": (f"{dim} 축 {step_from}→{step_to} 구간: {best[dim]} "
                   f"{best['전환율']*100:.2f}% vs {worst[dim]} "
                   f"{worst['전환율']*100:.2f}% — 격차 {gap_pp:.2f}%p. "
                   f"비중 축 전체의 {비중*100:.1f}%({int(worst['도달'])}명)"),
            "규모_연간건수": 규모,
            "근거축": dim,
            "구간": f"{step_from}→{step_to}",
            "기각사유": 기각,
        })
    return out


def _topic_threshold_breaches(t: dict, years: float) -> list[dict]:
    """config.THRESHOLDS 를 벗어난 지표를 후보로 만든다. 새 임계값을 만들지
    않는다 — status_of()가 이미 쓰는 그 THRESHOLDS를 그대로 재사용한다.
    벗어나지 않은 지표는 후보 자체를 만들지 않는다("기각"이 아니라 해당
    없음 — 실제 위반이 있어야 후보다).
    """
    emp = t["HR_직원"]
    n_total = int(len(emp))
    if trust_check({"ok": True}, n_total):
        return []  # 전체 표본 자체를 못 믿으면 후보를 만들지 않는다.

    n_active = int((emp["재직상태"] == "재직").sum())
    k = kpis(t)
    out = []
    for name, th in C.THRESHOLDS.items():
        row = k.get(name)
        if row is None:
            continue
        value = float(row["value"])
        status = status_of(name, value)
        if status == "ok":
            continue

        boundary_key = "위험" if status == "block" else "경고"
        boundary = th[boundary_key]
        gap_frac = abs(value - boundary) / boundary if boundary else 0.0
        raw_count = float(n_active)
        연간_건수 = raw_count / years if years else 0.0
        규모 = gap_frac * 1.0 * 연간_건수  # 비중 1.0 — 조직 전체 집계값이라 축 분해가 없다.

        out.append({
            "키": f"threshold:{name}",
            "제목": f"'{name}'가 {boundary_key} 기준을 벗어났다",
            "한줄": (f"{name} {value:.2f}{row['unit']} — {boundary_key} 기준 "
                   f"{boundary:.2f}{row['unit']} 대비 {gap_frac*100:.1f}% 초과"),
            "규모_연간건수": 규모,
            "근거축": None,
            "구간": status,
            "기각사유": "",  # 실제 임계값 위반이라 격차 크기로 기각하지 않는다.
        })
    return out


def _topic_trend_drops(t: dict, years: float) -> list[dict]:
    """monthly()의 각 지표에서 "최근 TREND_WINDOW_MONTHS개월 평균이 직전
    TREND_WINDOW_MONTHS개월 평균보다 낮은" 것을 후보로 만든다. 방향(좋다/
    나쁘다)은 안 따진다 — 추세 자체가 후보다.

    기각 기준은 새로 만들지 않는다 — monthly_verdict()가 이미 쓰는
    PRIMARY_MOVE_PCT(재직인원)·GUARDRAIL_MOVE_PCT(월평균초과근무시간)를
    "의미 있는 변화"의 문턱으로 빌려 쓴다. monthly()에 있는 두 지표가
    정확히 그 둘이라 전부 커버된다.
    """
    n_total = int(len(t["HR_직원"]))
    if trust_check({"ok": True}, n_total):
        return []

    m = monthly(t)
    n_active = int((t["HR_직원"]["재직상태"] == "재직").sum())
    move_pct = {C.PRIMARY_METRIC: C.PRIMARY_MOVE_PCT,
                C.GUARDRAIL_METRIC: C.GUARDRAIL_MOVE_PCT}

    out = []
    N = TREND_WINDOW_MONTHS
    if len(m) < 2 * N:
        return []  # 비교할 만큼 개월 수가 안 쌓였다.

    for col in m.columns:
        recent = m[col].iloc[-N:].mean()
        prev = m[col].iloc[-2 * N:-N].mean()
        if not (recent < prev):
            continue  # 떨어진 지표만 후보다.

        gap = float(prev - recent)
        gap_frac = gap / prev if prev else 0.0
        raw_count = float(n_active)
        연간_건수 = raw_count / years if years else 0.0
        규모 = gap_frac * 1.0 * 연간_건수

        th_pct = move_pct.get(col)
        기각 = ""
        if th_pct is not None and gap_frac * 100 < th_pct:
            기각 = (f"{gap_frac*100:.1f}% 하락 < 판단기준 {th_pct:.0f}%"
                  f"({'PRIMARY_MOVE_PCT' if col == C.PRIMARY_METRIC else 'GUARDRAIL_MOVE_PCT'})")

        out.append({
            "키": f"trend:{col}",
            "제목": f"'{col}' 최근 {N}개월 평균이 직전 {N}개월보다 낮다",
            "한줄": (f"{col} 최근 {N}개월 평균 {recent:.2f} vs 직전 {N}개월 평균 "
                   f"{prev:.2f} ({-gap_frac*100:+.1f}%)"),
            "규모_연간건수": 규모,
            "근거축": None,
            "구간": f"최근{N}개월 vs 직전{N}개월",
            "기각사유": 기각,
        })
    return out


@st.cache_data(show_spinner=False)
def proposal_topics(t: dict) -> list[dict]:
    """제안서 주제 후보를 가능한 만큼 뽑는다. 하나만 고르지 않는다.

    넷에서 뽑는다: ① 퍼널 구간(전환율 최저 vs 그다음 최저 구간 격차,
    획득·유지 퍼널 각각) ② config.FUNNEL_DIMS 각 축의 전환율 최고 vs
    최저 칸 격차(구간은 획득 퍼널의 병목 구간으로 고정) ③ config.THRESHOLDS
    를 벗어난 지표 ④ monthly()에서 최근 N개월 평균이 직전 N개월보다
    떨어진 지표.

    새 임계값을 만들지 않는다 — 전부 이미 있는 값을 빌려 쓴다:
    trust_check()/config.MIN_SAMPLE(못 믿을 조건), 판단기준.md의 "표본
    1건 흔들림=100/n" 공식(①·②의 기각 기준), config.THRESHOLDS(③),
    config.PRIMARY_MOVE_PCT·GUARDRAIL_MOVE_PCT(④의 기각 기준).

    못 믿을 조건에 걸린 칸/구간은 애초에 후보를 만들지 않는다 — 이건
    "비교 자체가 안 된다"이고, 기각("비교했는데 차이가 작다")과 다르다.
    기각된 후보도 지우지 않고 "기각사유"만 채워 목록에 남긴다.

    규모_연간건수 = 격차(비율) × 비중(비율) × 연간_건수. 연간_건수는
    관측된 건수를 config.PERIOD 기간(년)으로 나눠 연간 단위로 맞춘
    것이다 — datetime.now()를 쓰지 않는다.

    반환: 규모_연간건수 내림차순으로 정렬한 리스트. 기각된 후보는
    (기각 여부가 먼저이므로) 맨 뒤로 밀린다. 각 원소는
    {"키","제목","한줄","규모_연간건수","근거축","구간","기각사유"}.
    """
    emp, sep = t["HR_직원"], t["HR_퇴사이력"]
    years = _period_years()
    n_total = int(len(emp))

    topics: list[dict] = []

    # ① 퍼널 구간 — 획득 퍼널 + 유지 퍼널 각각 하나씩.
    topics += _topic_funnel_gaps(funnel(emp, sep), "획득", "획득 퍼널",
                                  n_total, years)
    topics += _topic_funnel_gaps(retention_funnel(t), "유지", "유지 퍼널",
                                  n_total, years)

    # ② 분해 축 — 획득 퍼널의 병목 구간을 기준으로 쪼갠다(다른 화면·
    #   리포트와 같은 구간을 써야 숫자가 어긋나지 않는다).
    f_acq = funnel(emp, sep)
    bottleneck_positions = f_acq.index[f_acq["is_bottleneck"]]
    if len(bottleneck_positions):
        bi = max(int(bottleneck_positions[0]), 1)
        step_from = f_acq["step"].iloc[bi - 1]
        step_to = f_acq["step"].iloc[bi]
        topics += _topic_axis_gaps(emp, sep, step_from, step_to, n_total, years)

    # ③ 임계값을 벗어난 지표.
    topics += _topic_threshold_breaches(t, years)

    # ④ 최근 N개월 평균이 직전 N개월보다 떨어진 지표.
    topics += _topic_trend_drops(t, years)

    topics.sort(key=lambda x: (bool(x["기각사유"]), -x["규모_연간건수"]))
    return topics


# ── 제안 주제 근거 조회 ───────────────────────────────────────────
# "추세"에서 볼 개월 수. 사용자가 직접 "최근 12개월"이라고 정했다 —
# RECENT_COHORT_MONTHS(12)와 값은 같지만 용도(코호트 진단)가 달라 같은
# 이름을 쓰지 않는다.
EVIDENCE_TREND_MONTHS = 12

# 달마다 추적되지 않는 지표를 topic_evidence()의 threshold 유형에서 만나면
# 왜 없는지를 사람이 읽을 말로 적는다(monthly()가 이 지표를 빼는 이유를
# 그대로 풀어 쓴 것 — 새로 사유를 짓지 않는다). 함수 이름·테이블 이름은
# 문장에 넣지 않는다 — 읽는 사람은 코드를 안 본다.
_THRESHOLD_TREND_REASONS = {
    "입사1년내이탈률": "이 지표는 매달 새로 다시 계산해야 해서, 지금은 달마다의 추세를 볼 수 없다.",
    "평균평가점수": "평가가 분기 단위로만 있어서, 달마다의 추세를 볼 수 없다.",
}


def _evidence_funnel_status(t: dict, kind: str, rest: list[str]) -> dict:
    """현황 — 그 주제가 속한 퍼널 전체(단계·도달·전환율·병목 표시)."""
    emp, sep = t["HR_직원"], t["HR_퇴사이력"]
    cols = ["step", "label", "n", "step_rate", "cum_rate", "drop", "is_bottleneck"]
    if kind == "funnel_gap":
        f = funnel(emp, sep) if rest[0] == "획득" else retention_funnel(t)
        return {"표": f[cols].copy(), "사유": None}
    if kind == "axis_gap":
        # axis_gap 후보는 언제나 획득 퍼널의 병목 구간에서 쪼갠 것이다
        # (proposal_topics() ②의 구현) — 그 획득 퍼널 전체를 보여준다.
        return {"표": funnel(emp, sep)[cols].copy(), "사유": None}
    reason = ("이 문제는 특정 퍼널 구간이 아니라 조직 전체를 하나로 집계한 "
              "값에서 나왔다 — 그래서 속한 퍼널이 없다." if kind == "threshold" else
              "이 문제는 특정 퍼널 구간이 아니라 여러 달에 걸친 추세에서 나왔다 "
              "— 그래서 속한 퍼널이 없다.")
    return {"표": None, "사유": reason}


def _evidence_axis_cause(t: dict, kind: str, rest: list[str]) -> dict:
    """원인 — 그 주제의 분해 축 표(칸·도달·전환·전환율·비중·최고/최저 표시).
    trust_check()에 걸리는 칸은 지우지 않고 "신뢰"열에 사유를 남긴다(값을
    숨기는 게 아니라 판정만 다는 것 — 다른 화면과 같은 마스킹 방식).
    """
    if kind != "axis_gap":
        reason = {
            "funnel_gap": ("이 후보는 분해 축 비교가 아니라 퍼널 구간 자체의 "
                          "격차에서 나왔다 — 분해 축 표가 없다."),
            "threshold": ("이 후보는 분해 축이 없는 조직 전체 집계값(임계값 "
                         "위반)이라 분해 축 표가 없다."),
            "trend": ("이 후보는 분해 축이 없는 조직 전체 월별 집계값(추세)"
                     "이라 분해 축 표가 없다."),
        }.get(kind, "이 유형은 분해 축 표를 만들 수 없다.")
        return {"표": None, "사유": reason}

    dim, seg = rest[0], rest[1]
    step_from, step_to = seg.split("->")
    emp, sep = t["HR_직원"], t["HR_퇴사이력"]
    g = funnel_by(emp, sep, dim, step_from, step_to).copy()
    g["신뢰"] = g["도달"].apply(lambda n: trust_check({"ok": True}, int(n)) or "")
    g["표시"] = ""
    trustworthy = g[g["신뢰"] == ""]
    if len(trustworthy):
        g.loc[trustworthy["전환율"].idxmax(), "표시"] = "최고"
        g.loc[trustworthy["전환율"].idxmin(), "표시"] = "최저"
    return {"표": g, "사유": None}


def _evidence_scale(t: dict, kind: str, rest: list[str]) -> dict:
    """규모 — 연간 건수와 환산에 쓴 가정 목록. 실측(raw_count)과 환산
    (연간_건수)을 서로 다른 키("실측_원자료"·"환산_연간건수")에 담아
    같은 항목에 섞지 않는다.
    """
    emp, sep = t["HR_직원"], t["HR_퇴사이력"]
    years = _period_years()
    가정 = [f"1년을 365.25일로 계산해, 관측 기간을 {years:.2f}년으로 봤다."]

    if kind == "funnel_gap":
        f = funnel(emp, sep) if rest[0] == "획득" else retention_funnel(t)
        ranked = f[f["step_rate"].notna()].copy()
        ranked["_못믿음"] = ranked["n"].apply(
            lambda n: trust_check({"ok": True}, int(n)) is not None)
        ranked = ranked[~ranked["_못믿음"]].sort_values("step_rate")
        if len(ranked) < 2:
            return {"실측_원자료": None, "환산_연간건수": None,
                    "환산_가정": 가정,
                    "사유": "비교 가능한 구간이 2개 미만이라 다시 계산할 수 없다."}
        worst = ranked.iloc[0]
        raw_count = float(worst["drop"])
        raw_desc = (f"{rest[0]} 퍼널에서 전환율이 가장 낮은 구간('{worst['step']}')의 "
                   "감소 인원(실측)")
        가정.append("이 구간에서 실제로 줄어든 인원 수를 그대로 썼다 — 새로 "
                  "추정하지 않았다.")
    elif kind == "axis_gap":
        dim, seg = rest[0], rest[1]
        step_from, step_to = seg.split("->")
        g = funnel_by(emp, sep, dim, step_from, step_to).copy()
        g["_못믿음"] = g["도달"].apply(
            lambda n: trust_check({"ok": True}, int(n)) is not None)
        trustworthy = g[~g["_못믿음"]]
        if len(trustworthy) < 2:
            return {"실측_원자료": None, "환산_연간건수": None,
                    "환산_가정": 가정,
                    "사유": "비교 가능한 칸이 2개 미만이라 다시 계산할 수 없다."}
        worst = trustworthy.loc[trustworthy["전환율"].idxmin()]
        raw_count = float(worst["도달"])
        raw_desc = (f"'{dim}' 축 {step_from}→{step_to} 구간에서 전환율이 가장 "
                   f"낮은 칸('{worst[dim]}')의 도달 인원(실측)")
        가정.append("이 칸에 실제로 도달한 인원 수를 그대로 썼다 — 새로 "
                  "추정하지 않았다.")
    elif kind in ("threshold", "trend"):
        raw_count = float((emp["재직상태"] == "재직").sum())
        raw_desc = "이 지표가 대표하는 재직 인원(실측) — 조직 전체 집계값이라 축 분해가 없다."
        가정.append("개인별로 나눌 수 없는 조직 전체 집계값이라, 재직 인원 "
                  "전체를 기준으로 근사했다 — 실제 영향 인원을 새로 추정하지 "
                  "않았다.")
    else:
        return {"실측_원자료": None, "환산_연간건수": None, "환산_가정": 가정,
                "사유": "이 유형은 규모를 다시 계산할 수 없다."}

    연간_건수 = raw_count / years if years else 0.0
    가정.append("이 값을 관측 기간의 길이로 나눠 연간 단위로 바꿨다 — 사건이 "
              "그 기간 내내 고르게 일어났다고 본 값이며, 계절에 따른 차이는 "
              "반영하지 않았다.")

    return {
        "실측_원자료": {"raw_count": raw_count, "설명": raw_desc},
        "환산_연간건수": {"값": 연간_건수, "기간_년": years},
        "환산_가정": 가정,
        "사유": None,
    }


def _evidence_trend(t: dict, kind: str, rest: list[str]) -> dict:
    """추세 — 관련 지표의 최근 EVIDENCE_TREND_MONTHS개월. monthly()에 없는
    지표는 지어내지 않고 없는 이유만 적는다.
    """
    m = monthly(t)
    col = None
    if kind == "trend":
        col = rest[0]
    elif kind == "threshold":
        name = rest[0]
        if name in m.columns:
            col = name
        else:
            reason = _THRESHOLD_TREND_REASONS.get(
                name, f"'{name}'는 달 단위로 추적되지 않아 추세를 낼 수 없다.")
            return {"표": None, "사유": reason}
    else:
        reason = ("이 흐름의 단계별 전환율은 달 단위로 추적되지 않아 추세를 "
                  "낼 수 없다." if kind == "funnel_gap" else
                  "이 축의 칸별 전환율은 달 단위로 추적되지 않아 추세를 낼 수 없다.")
        return {"표": None, "사유": reason}

    return {"표": m[col].tail(EVIDENCE_TREND_MONTHS).copy(), "사유": None}


def topic_evidence(t: dict, topic: dict) -> dict:
    """제안 주제 하나(proposal_topics()가 돌려준 원소 하나)에 대해, 제안서가
    쓸 근거를 조회만 해서 한 번에 모아 돌려준다. **이 함수는 조회만 한다 —
    문장을 만들지 않는다.** 숫자·표만 돌려주고, 그걸로 어떤 문장을 쓸지는
    여기서 정하지 않는다(report 쪽 몫).

    반환: {"현황","원인","규모","추세"} 네 키.

        현황  그 주제가 속한 퍼널 전체(단계·도달·전환율·병목 표시)
        원인  그 주제의 분해 축 표(칸·도달·전환·전환율·비중·최고/최저 표시)
        규모  연간 건수 + 환산에 쓴 가정 목록
        추세  관련 지표의 최근 EVIDENCE_TREND_MONTHS(12)개월

    없는 것은 지어내지 않고 그 항목을 None으로 두되, 왜 없는지를 같은
    항목의 "사유"에 적는다(현황·원인·추세는 {"표": None, "사유": str},
    규모는 없을 때 {"실측_원자료": None, "환산_연간건수": None,
    "환산_가정": [...], "사유": str}).

    "규모" 안에서는 실측(raw_count — 실제 관측된 값)과 환산(연간_건수 —
    기간으로 나눠 바꾼 값)을 각각 "실측_원자료"·"환산_연간건수"로 키를
    나눠 돌려준다 — 같은 항목에 섞지 않는다.
    """
    kind = topic["키"].split(":")[0]
    rest = topic["키"].split(":")[1:]
    return {
        "현황": _evidence_funnel_status(t, kind, rest),
        "원인": _evidence_axis_cause(t, kind, rest),
        "규모": _evidence_scale(t, kind, rest),
        "추세": _evidence_trend(t, kind, rest),
    }


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
