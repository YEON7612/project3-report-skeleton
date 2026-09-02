# -*- coding: utf-8 -*-
"""검증.

검증은 **자동으로 통과시키지 않는다.** 결과를 사람 앞에 놓고 게이트에서 판단하게 한다.
경고를 앱이 마음대로 무시하면, 사람은 무엇을 승인했는지 모른 채 승인하게 된다.

판정 3종:

  ok    통과
  warn  경고 — **정상일 수도 있다. 사람이 판단한다.**
  block 차단 — 이 상태로는 분석할 수 없다.

────────────────────────────────────────────────────────────────────
차단과 경고를 가르는 것은 한 질문이다.

    이 규칙이 깨진 채로 계산하면 값이 틀리는가?
        틀린다              → block
        해석만 조심하면 된다 → warn

차단을 늘리면 안전해 보이지만, 실무 데이터는 늘 어딘가 깨져 있어서
앱이 아무것도 못 돌리게 된다. **차단은 "이대로 계산하면 확실히 틀리는 것"에만 건다.**
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import pandas as pd

from core import config as C
from core.load import to_dt


def _r(name, level, msg, detail=""):
    """검증 결과 한 줄. 그대로 쓴다."""
    return {"name": name, "level": level, "msg": msg, "detail": detail}


def profile(t: dict) -> pd.DataFrame:
    """적재 직후 개요. 게이트 1에서 사람이 보는 화면.

    **그대로 쓴다.** 어느 도메인이든 행수·컬럼·기간·결측은 먼저 본다.
    """
    rows = []
    for name, df in t.items():
        date_col = next((c for c in df.columns
                         if c.endswith("_date") or c == "year_month"), None)
        span = ""
        if date_col is not None:
            s = df[date_col].astype(str)
            span = f"{s.min()} ~ {s.max()}"
        rows.append({
            "테이블": name, "행수": len(df), "컬럼": df.shape[1],
            "기간": span,
            "결측 컬럼": int(df.isna().any().sum()),
            "메모리(MB)": round(df.memory_usage(deep=True).sum() / 1e6, 1),
        })
    return pd.DataFrame(rows)


def run_checks(t: dict) -> list[dict]:
    """정합성 검증. 결과는 게이트 1에서 사람에게 보여준다.

    ★ Day1 실습 D — 규칙 3건. 내 도메인(HR 근속) 기준으로 작성했다.

        1. 행 수      — HR_직원 표본이 코호트 분석이 성립하는 최소치(n≥30)보다 적은가
        2. 필수 컬럼  — 퍼널·유지이탈 판정에 반드시 필요한 사번·입사일·재직상태가 있는가
        3. 날짜 범위  — HR_근태가 config.PERIOD(근태 수집 기간)를 벗어나는가

    각 규칙마다 물었다: **이게 깨지면 계산이 틀리는가, 해석만 조심하면 되는가.**
    셋 다 "틀린다" 쪽이라 block으로 걸었다 — 표본이 30명 밑이면 코호트 자체가
    안 되고, 사번·입사일·재직상태가 없으면 잔류율을 계산할 수 없고, 근태가
    기간 밖이면 초과근무 월평균·3분위가 그대로 왜곡된다. 통신사 참고 검증에서
    warn으로 둔 것(결측·응답률 등)과 달리, 이 셋은 "해석 주의"로 넘길 수 없다.

    다 쓰고 나면 **정상 파일을 일부러 망가뜨려 넣어 본다** (실습 E).
    """
    out = []
    emp = t["HR_직원"]

    # 1. 행 수 — 코호트 분석이 성립하는 최소 표본(n≥30)보다 적으면
    #    근거: 내도메인.md 명세4행 — 세그먼트 분석에 이미 쓰고 있는 최소표본 기준.
    n_emp = len(emp)
    out.append(_r(
        "행 수", "block" if n_emp < 30 else "ok",
        (f"HR_직원 {n_emp}명 — 최소 표본(30명) 미만이라 어떤 코호트 분석도 "
         f"성립하지 않습니다") if n_emp < 30 else
        f"HR_직원 {n_emp}명 — 최소 표본(30명) 이상입니다",
        "코호트 분석이 성립하는 최소 표본 n≥30 (내도메인.md 명세4행과 동일 기준)",
    ))

    # 2. 필수 컬럼 — 연차별 잔류율 퍼널과 유지/이탈 판정의 근거
    required = ["사번", "입사일", "재직상태"]
    missing = [c for c in required if c not in emp.columns]
    out.append(_r(
        "필수 컬럼", "block" if missing else "ok",
        (f"HR_직원에서 컬럼 누락: {', '.join(missing)}") if missing else
        "HR_직원에 사번·입사일·재직상태 컬럼이 모두 있습니다",
        "연차별 잔류율 퍼널과 유지/이탈 판정(내도메인.md 명세5행)에 반드시 필요합니다",
    ))

    # 3. 날짜 범위 — 근태 데이터가 config.PERIOD를 벗어나면
    #    근거: 기간 밖 데이터가 섞이면 초과근무 월평균·3분위 계산이 왜곡된다.
    att = t["HR_근태"]
    d = pd.to_datetime(att["년월"], format="%Y-%m", errors="coerce")
    lo, hi = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    out_of_range = int(((d < lo) | (d > hi)).sum())
    out.append(_r(
        "날짜 범위", "block" if out_of_range else "ok",
        (f"HR_근태 {len(att):,}건 중 {out_of_range:,}건이 "
         f"{C.PERIOD[0]} ~ {C.PERIOD[1]} 밖입니다") if out_of_range else
        f"HR_근태 {len(att):,}건 전체가 {C.PERIOD[0]} ~ {C.PERIOD[1]} 안에 있습니다",
        "기간 밖 데이터가 섞이면 초과근무 월평균·3분위 구간 계산이 왜곡됩니다",
    ))

    return out


def summarize(checks: list[dict]) -> dict:
    """통과·경고·차단을 센다. 차단이 하나라도 있으면 게이트를 못 넘는다.

    **그대로 쓴다.**
    """
    n = {"ok": 0, "warn": 0, "block": 0}
    for c in checks:
        n[c["level"]] += 1
    return {**n, "total": len(checks), "can_pass": n["block"] == 0}


# ══════════════════════════════════════════════════════════════════
# 참고 — 통신사 데이터에서 쓴 검증 12건
#
# **이 함수는 호출되지 않는다.** 읽고 필요한 것만 위 run_checks() 로 옮긴다.
# 대부분은 통신사 테이블·컬럼에 묶여 있어서 그대로는 안 돌아간다.
#
# 눈여겨볼 것은 규칙 자체가 아니라 **무엇을 block 으로 두고 무엇을 warn 으로
# 뒀는가**이다.
#
#   block  기간 정합성 · 퍼널 순서 · 신규 고객 일치 · 배정 중복 ·
#          중도절단 · 참조 무결성        ← 깨지면 계산이 틀린다
#   warn   월 커버리지 · 결측률 2건 · 응답률 · 표본 수 · 배정 균형
#                                        ← 정상일 수도 있다. 사람이 판단한다
# ══════════════════════════════════════════════════════════════════
def reference_checks_telecom(t: dict) -> list[dict]:
    out = []
    lo, hi = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    cu, se, fe = t["customers"], t["sessions"], t["funnel_events"]
    um, asg, ad = t["usage_monthly"], t["experiment_assignments"], t["ad_spend"]

    # 1. 기간 — 기간이 어긋나면 조인에 구멍이 생긴다
    bad = []
    for label, s in [("sessions", se.session_date), ("funnel_events", fe.event_date),
                     ("ad_spend", ad.spend_date)]:
        d = to_dt(s)
        if d.min() < lo or d.max() > hi:
            bad.append(f"{label} {d.min().date()}~{d.max().date()}")
    out.append(_r("기간 정합성", "block" if bad else "ok",
                  "기간을 벗어난 테이블이 있습니다" if bad else
                  f"모든 테이블이 {C.PERIOD[0]} ~ {C.PERIOD[1]} 안에 있습니다",
                  "; ".join(bad)))

    # 2. 월 커버리지 — 빠진 달이 있어도 정상일 수 있다
    m = sorted(um.year_month.astype(str).unique())
    out.append(_r("월 커버리지", "ok" if len(m) == 12 else "warn",
                  f"{m[0]} ~ {m[-1]} ({len(m)}개월)"))

    # 3. 퍼널 역행 — 앞 단계를 안 거치고 뒤 단계에 온 대상
    piv = (fe.pivot_table(index="visitor_id", columns="step_order",
                          values="event_id", aggfunc="count").fillna(0) > 0)
    cols = sorted(piv.columns)
    viol = sum(int(((~piv[a]) & piv[b]).sum()) for a, b in zip(cols, cols[1:]))
    out.append(_r("퍼널 순서", "block" if viol else "ok",
                  f"단계 역행 {viol}건" if viol else "단계 역행 없음"))

    # 4. 신규 고객 = 최종 통과자
    paid = set(fe.loc[fe.funnel_step == C.FUNNEL_STEPS[-1], "visitor_id"])
    newc = set(cu.loc[cu.visitor_id.notna(), "visitor_id"])
    out.append(_r("신규 고객 일치", "ok" if newc == paid else "block",
                  f"신규 {len(newc):,}명 / 최종 통과 {len(paid):,}명"))

    # 5. 실험 배정 중복 — 한 대상이 두 번 배정되면 결과를 못 믿는다
    dup = int(asg.duplicated(["experiment_id", "visitor_id"]).sum())
    out.append(_r("배정 중복", "block" if dup else "ok",
                  f"중복 {dup}건" if dup else "중복 없음"))

    # 6. 중도절단 — 떠난 뒤의 기록이 있으면 데이터가 잘못됐다
    ch = cu[cu.is_churned][["customer_id", "churn_date"]].copy()
    ch["cm"] = to_dt(ch.churn_date).dt.strftime("%Y-%m")
    mg = um.merge(ch, on="customer_id", how="inner")
    after = int((mg.year_month.astype(str) > mg.cm).sum())
    out.append(_r("중도절단", "block" if after else "ok",
                  f"이탈 이후 사용 기록 {after}건" if after else
                  "이탈 이후 사용 기록 없음"))

    # 7. 참조 무결성 — 끊어진 참조가 있으면 조인에서 조용히 사라진다
    fk_bad = []
    if not set(um.customer_id) <= set(cu.customer_id):
        fk_bad.append("usage_monthly")
    if not set(fe.session_id) <= set(se.session_id):
        fk_bad.append("funnel_events")
    out.append(_r("참조 무결성", "block" if fk_bad else "ok",
                  f"끊어진 참조: {', '.join(fk_bad)}" if fk_bad else "모든 참조 정상"))

    # 8. 결측 — 경고로만 낸다. **구조적 결측은 오류가 아니다.**
    nn = int(cu.visitor_id.isna().sum())
    if nn:
        out.append(_r("visitor_id 결측", "warn",
                      f"고객 {len(cu):,}명 중 {nn:,}명({nn/len(cu)*100:.0f}%)이 "
                      f"퍼널 이력이 없습니다",
                      "기존 고객은 이번 기간 퍼널을 거치지 않았으므로 정상일 수 있습니다. "
                      "다만 퍼널 테이블과 INNER JOIN하면 이 인원이 전부 사라집니다."))

    # 9. 캠페인 결측 — 자연 유입은 캠페인이 없다
    cn = int(se.campaign_id.isna().sum())
    if cn:
        out.append(_r("campaign_id 결측", "warn",
                      f"세션 {len(se):,}건 중 {cn:,}건({cn/len(se)*100:.0f}%)에 "
                      f"캠페인이 없습니다",
                      "자연 유입(검색·직접 방문)은 캠페인이 없으므로 정상일 수 있습니다."))

    # 10. 응답률 — 응답자 평균은 전체 평균이 아니다
    st_ = t["support_tickets"]
    resp = st_.satisfaction_score.notna().mean()
    if resp < 0.5:
        out.append(_r("만족도 응답률", "warn",
                      f"응답률 {resp*100:.1f}% — 응답자 평균은 전체 만족도가 아닙니다",
                      "극단적 경험을 한 쪽이 더 많이 응답하는 경향이 있습니다. "
                      "이 경고는 리포트 7장 한계로 옮깁니다."))

    # 11. 표본 크기
    small = []
    for _, e in t["experiments"].iterrows():
        n = int((asg.experiment_id == e.experiment_id).sum())
        if n < C.MIN_SAMPLE:
            small.append(f"{e.experiment_id}({n:,})")
    out.append(_r("실험 표본", "warn" if small else "ok",
                  f"표본 부족: {', '.join(small)}" if small else
                  "모든 실험이 최소 표본을 넘습니다"))

    # 12. SRM — 실험 결과를 보기 전에 반드시 확인
    from core.metrics import srm_check
    broken = []
    for _, e in t["experiments"].iterrows():
        s = srm_check(asg, e.experiment_id)
        if not s["ok"]:
            broken.append(f"{e.experiment_id} ({s['ratio'][0]*100:.1f}:"
                          f"{s['ratio'][1]*100:.1f}, p={s['p']:.1e})")
    out.append(_r("실험 배정 균형(SRM)", "warn" if broken else "ok",
                  f"배정이 깨진 실험: {', '.join(broken)}" if broken else
                  "모든 실험의 배정이 균형입니다",
                  "배정이 깨진 실험은 어떤 효과가 나와도 해석할 수 없습니다. "
                  "결과를 쓰지 말고 재실험해야 합니다." if broken else ""))

    return out
