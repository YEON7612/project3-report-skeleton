# -*- coding: utf-8 -*-
"""리포트 8장 조립.

────────────────────────────────────────────────────────────────────
자동으로 쓰는 장과 사람이 쓰는 장이 나뉜다. 가르는 질문은 하나다.

    이 문장이 틀렸을 때 누가 책임지는가?
        사람이 진다        → 사람이 쓴다   (2 배경 · 6 해석 · 8 제안)
        사실이 틀린 것뿐   → 자동으로 쓴다 (1 요약 · 3 방법 · 4 결과 · 5 실험 · 7 한계)

**해석과 제안을 자동화하는 순간 책임이 사라진다.** 그것이 이 수업의 결론이다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from datetime import datetime

from core import config as C, metrics as M, validate as V
from core.todo import todo

# ★ 자동 생성 문장에 인과를 단정하는 말을 쓰지 않는다.
#   관측 데이터로는 인과를 주장할 수 없는데, 방심하면 자동 문장이 인과를 쓴다.
#   내 도메인에만 있는 단정 표현이 있으면 여기에 더한다.
BANNED = ["때문에", "덕분에", "효과로", "입증되었", "증명되었", "확실히",
          "기여도가 높다", "영향을 미쳤다"]


def check_phrasing(text: str) -> list[str]:
    """자동 생성 문장에 인과 단정 표현이 섞였는지 스스로 검사한다.

    **그대로 쓴다.** 사람이 쓴 장에도 걸어라 — 사람이 더 자주 쓴다.
    """
    return [w for w in BANNED if w in text]


def _fmt(n, unit=""):
    return f"{n:,.0f}{unit}"


# ── 자동으로 쓰는 장 ──────────────────────────────────────────────
def _s1_summary(t: dict) -> dict:
    """1. 요약

    metrics.kpis() 가 돌려주는 이름·값·fmt를 그대로 쓴다 — 여기서 지표를
    다시 짓거나 다시 계산하지 않는다. 재직인원·월평균초과근무시간은
    monthly()에 전월 값이 있어 전월 대비 변화까지 적는다. 입사1년내이탈률·
    평균평가점수는 monthly()에 없다(전자는 매달 KM을 다시 적합해야 하고,
    후자는 HR_평가가 분기 단위라 월로 못 나눈다 — monthly() docstring과
    같은 이유) — 없는 값을 지어내지 않고 현재값만 적는다.

    **수치는 쓰되 인과는 쓰지 않는다.** "A가 낮다"는 되고 "B 때문에 A가 낮다"는 안 된다.
    다 쓰고 나서 check_phrasing() 으로 자기 문장을 검사한다.

    반환: {"title": "1. 요약", "kind": "auto", "body": "..."}
    """
    k = M.kpis(t)
    m = M.monthly(t)
    names = ["재직인원", "입사1년내이탈률", "평균평가점수", "월평균초과근무시간"]

    lines = []
    for name in names:
        v = k[name]
        cur = v["fmt"].format(v["value"])
        if m is not None and name in m.columns and len(m) >= 2:
            diff = m[name].iloc[-1] - m[name].iloc[-2]
            delta = v["fmt"].replace("{:", "{:+", 1).format(diff)
            lines.append(f"- {name}: {cur} ({m.index[-2]} → {m.index[-1]} "
                         f"대비 {delta})")
        else:
            lines.append(f"- {name}: {cur} (월별 비교값 없음 — monthly()에 "
                         f"포함되지 않는 지표)")

    body = (f"{C.PERIOD[0]} ~ {C.PERIOD[1]} 기준 지표는 다음과 같다.\n\n"
            + "\n".join(lines))

    return {"title": "1. 요약", "kind": "auto", "body": body}


def _s3_method(t: dict) -> dict:
    """3. 방법

    **분석 단위(그레인)를 반드시 밝힌다.** 읽는 사람이 숫자를 다시 세어볼 수 있어야 한다.
    무엇을 어떻게 셌는지, 무엇을 뺐는지, 어떤 검정을 썼는지.

    지표의 정의는 **위키가 원본**이다. 여기서 새로 정의하지 않는다.
    """
    n_emp = len(t["HR_직원"])
    n_att = len(t["HR_근태"])

    body = (
        f"분석 단위(그레인)는 사번 1건이다. 사번(직원 식별자)으로 고유하게 "
        f"센다 — 같은 사번이 여러 행으로 중복되지 않는다.\n\n"
        f"데이터 기간은 {C.PERIOD[0]} ~ {C.PERIOD[1]}이다. "
        f"HR_직원 {n_emp:,}건, HR_근태 {n_att:,}건을 썼다.\n\n"
        f"재직 중인 사번의 종료 시점은 실행 시각이 아니라 "
        f"config.SNAPSHOT_DATE({C.SNAPSHOT_DATE}, 고정값)로 둔다 — 실행 "
        f"시각을 쓰면 실행할 때마다 값이 달라져 재현이 안 된다.\n\n"
        f"연차별 잔류율(획득 퍼널)은 사번별 독립 비율이 아니라 "
        f"Kaplan-Meier 생존함수로 추정한다. 재직 중인 사번은 아직 사건"
        f"(퇴사)이 관측되지 않은 중도절단으로 두고 위험집합에 반영한다 — "
        f"SNAPSHOT_DATE 기준으로 아직 해당 연차에 이를 만큼 기간이 지나지 "
        f"않은 사번을 그 연차의 이탈로 세지 않는다. 아직 관측이 덜 찬 것과 "
        f"실제로 못 넘긴 것을 구분한다.\n\n"
        f"입사1년내이탈률은 전사 전체가 아니라 초과근무 상위 1/3 세그먼트를 "
        f"모집단으로 계산한다. 전사 전체 기준값은 참고용으로 별도 존재한다.\n\n"
        f"지표의 정의는 위키(지표정의서.md·내도메인.md)가 원본이며, 여기서 "
        f"새로 정의하지 않는다."
    )

    return {"title": "3. 방법", "kind": "auto", "body": body}


def _s4_results(t: dict) -> dict:
    """4. 결과

    숫자를 나열하되 **해석하지 않는다.** 해석은 6장이고 사람이 쓴다.
    "낮다"까지가 결과이고 "왜 낮은가"는 해석이다.

    funnel()·funnel_by()의 결과를 그대로 옮긴다 — 여기서 새로 계산하지
    않는다. 분해 축(부서·직급·채용경로)은 pages/2_대시보드.py와 같은
    구간(병목 구간)을 본다. funnel_by() 각 칸에 trust_check()를 그대로
    적용해, 표본 부족으로 걸린 칸은 사유만 적고 수치를 쓰지 않는다 —
    화면(대시보드)에서 감춘 숫자를 문서에 쓰면 감춘 의미가 없다.

    charts 키에 차트 이름을 넣으면 PDF에 그려진다. 예) ["funnel", "device"]
    """
    emp, sep = t["HR_직원"], t["HR_퇴사이력"]
    f = M.funnel(emp, sep)

    lines = ["획득 퍼널 단계별 값은 다음과 같다."]
    for r in f.itertuples():
        if r.step_rate == r.step_rate:  # NaN 아님
            lines.append(f"- {r.label}: {r.n:,}명 (직전 단계 대비 "
                         f"{r.step_rate*100:.1f}%, 누적 {r.cum_rate*100:.1f}%)")
        else:
            lines.append(f"- {r.label}: {r.n:,}명 (기준)")
    bn = f[f.is_bottleneck].iloc[0]
    lines.append(f"- 단계 중 직전 단계 대비 전환율이 가장 낮은 구간은 "
                 f"{bn.label}이다({bn.step_rate*100:.1f}%).")

    bi = max(int(f.index[f.is_bottleneck][0]), 1)
    step_from, step_to = f.step.iloc[bi - 1], f.step.iloc[bi]
    label_from, label_to = f.label.iloc[bi - 1], f.label.iloc[bi]

    lines.append("")
    lines.append(f"{label_from} → {label_to} 구간을 분해한 값은 다음과 같다.")
    for dim in ["부서", "직급", "채용경로"]:
        g = M.funnel_by(emp, sep, dim, step_from, step_to)
        g["사유"] = g["도달"].apply(lambda n: M.trust_check({"ok": True}, int(n)))
        lines.append(f"- {dim}")
        for _, r in g.iterrows():
            if r["사유"] is not None:
                lines.append(f"  - {r[dim]}: {r['사유']}")
            else:
                lines.append(
                    f"  - {r[dim]}: 도달 {r['도달']:,}명 중 전환 "
                    f"{r['전환']:,}명 (전환율 {r['전환율']*100:.1f}%, "
                    f"비중 {r['비중']*100:.1f}%)")

    body = "\n".join(lines)

    return {"title": "4. 결과", "kind": "auto", "body": body,
            "charts": ["funnel", "device"]}


def _s5_experiments(t: dict) -> dict:
    """5. 실험

    **무효 판정된 실험은 사유만 적고 수치를 쓰지 않는다.** 화면에서 감춘 숫자를
    리포트에 쓰면 감춘 의미가 없다. metrics.experiment_results() 의 verdict 를 보고
    분기한다.

    이 프로젝트엔 무작위 배정 실험이 없다(experiment_results()는 항상 빈
    리스트). 대신 monthly_verdict()가 이미 낸 월별 전후 비교(주지표=
    재직인원, 가드레일=월평균초과근무시간)를 그대로 옮긴다 — 여기서 새로
    계산하지 않는다. monthly_verdict()가 trust_check()에 걸려 "무효"를
    돌려주면 사유만 적고 수치는 쓰지 않는다.

    실험이 없으면 이 장을 빼거나, 전후 비교를 적되
    **"인과를 주장할 수 없다"를 같은 문단에 남긴다.**
    """
    v = M.monthly_verdict(t)

    lines = [
        "이 프로젝트에는 무작위 배정 실험이 없다. 아래는 월별 전후 비교이며, "
        "무작위 배정이 없었으므로 관측된 변화에 인과를 주장할 수 없다."
    ]
    lines.append("")

    if v["verdict"] == "무효":
        lines.append(f"- 판정: 무효 — {v['reason']}")
    else:
        p, g, period = v["primary"], v["guard"], v["period"]
        lines.append(f"- {p['name']}: {period['prev']} {p['prev']:,.0f}명 → "
                     f"{period['now']} {p['now']:,.0f}명 ({p['pct']:+.1f}%)")
        lines.append(f"- {g['name']}: {period['prev']} {g['prev']:.1f}시간 → "
                     f"{period['now']} {g['now']:.1f}시간 ({g['pct']:+.1f}%)")
        lines.append(f"- 판정: {v['verdict']}"
                     + (f" — {v['reason']}" if v["reason"] else ""))

    body = "\n".join(lines)

    return {"title": "5. 실험", "kind": "auto", "body": body}


def _s7_limits(t: dict, items: list[dict] | None = None) -> dict:
    """7. 한계 — 검증 경고에서 조립한다

    ★ Day4 실습 D에서 채웁니다. ← 오늘의 두 번째 장면

    **사람이 매번 쓰는 것이 아니라 경고를 그대로 옮긴다.**
    검증에서 경고가 났는데 한계에 안 적히면 **그 경고는 사라진 것과 같다.**

    한계는 세 곳에서 온다.

        검증 경고        validate.run_checks() 에서 level == "warn" 인 것
        못 한 것         표본이 모자라 판정 못 한 것 · 기간이 짧아 못 본 것
        찾았는데 없던 것  **"없음"도 결과다**

    7주차에 판정한 것들이 여기로 들어온다.

        생존 편향 판정          관측 기간이 다른 대상을 비교했던 것
        선행지표 부재           찾았지만 없었다 — 있었으면 무엇을 봤을까
        검출 불가 판정          표본·기간이 안 돼 못 돌린 실험

    그리고 **가정값이 들어간 문장에는 "가정값 기반"을 붙인다.**
    실측값과 가정값이 한 문단에 섞이면 읽는 사람은 둘 다 실측으로 읽는다.

    **사람이 매번 쓰는 게 아니라 자동으로 조립한다.** validate.run_checks()의
    경고와 funnel_by() 각 칸의 trust_check() 결과를 그대로 옮길 뿐, 여기서
    새로 판단하지 않는다.

    리포트 화면에서 st.data_editor로 이 항목들(검증 경고·표본 부족·확인하지
    못한 것)을 고치거나 빼거나 새로 추가할 수 있다 — limits_items()가 그
    편집 대상 행을, 이 함수가 편집된 행 + 항상 넣는 두 고정 문장을 최종
    본문으로 조립한다.
    """
    if items is None:
        items = limits_items(t)

    groups = [
        ("검증 경고", "**검증 경고**"),
        ("표본 부족", "**표본 부족으로 판정하지 않은 항목**"),
        ("확인하지 못한 것", "**이번 분석에서 확인하지 못한 것**"),
    ]
    lines = []
    for src, label in groups:
        rows = [it for it in items
                if it.get("출처") == src and it.get("포함", True)
                and str(it.get("내용", "")).strip()]
        lines.append(label)
        if rows:
            lines.extend(f"- {it['내용']}" for it in rows)
        else:
            lines.append("(해당 항목 없음 — 전부 빠지거나 삭제됨)")
        lines.append("")

    lines.extend(limits_fixed_sentences(t))

    body = "\n".join(lines).strip()

    return {"title": "7. 한계", "kind": "auto", "body": body}


def limits_items(t: dict) -> list[dict]:
    """7. 한계의 편집 가능한 행 — 검증 경고 · 표본 부족 · 확인하지 못한 것.

    항상 넣는 두 문장(인과 불가·기간 제약)은 여기 안 들어간다 — 고정이라
    st.data_editor 편집 대상이 아니다(limits_fixed_sentences() 몫).

    반환: [{"출처", "내용", "포함"}, ...]
    """
    checks = V.run_checks(t)
    warns = [c for c in checks if c["level"] == "warn"]

    items = []
    if warns:
        for w in warns:
            content = (f"{w['name']}: {w['msg']}"
                       + (f" — {w['detail']}" if w["detail"] else ""))
            items.append({"출처": "검증 경고", "내용": content, "포함": True})
    else:
        items.append({"출처": "검증 경고",
                      "내용": f"경고 없음, 검증 {len(checks)}건 전부 통과.",
                      "포함": True})

    emp, sep = t["HR_직원"], t["HR_퇴사이력"]
    f = M.funnel(emp, sep)
    bi = max(int(f.index[f.is_bottleneck][0]), 1)
    step_from, step_to = f.step.iloc[bi - 1], f.step.iloc[bi]

    n_before = len(items)
    for dim in ["부서", "직급", "채용경로"]:
        g = M.funnel_by(emp, sep, dim, step_from, step_to)
        g["사유"] = g["도달"].apply(lambda n: M.trust_check({"ok": True}, int(n)))
        for _, r in g[g["사유"].notna()].iterrows():
            items.append({"출처": "표본 부족",
                          "내용": f"{dim} · {r[dim]}: {r['사유']} — 판정하지 않음",
                          "포함": True})
    if len(items) == n_before:
        items.append({"출처": "표본 부족",
                      "내용": "표본 부족으로 판정하지 않은 항목 없음.",
                      "포함": True})

    items.append({"출처": "확인하지 못한 것",
                  "내용": ("퇴사사유 컬럼은 데이터에 있지만 이번 분석의 어떤 "
                          "지표에도 쓰이지 않았다. 퇴사 이유별 분석은 하지 "
                          "않았다."),
                  "포함": True})
    items.append({"출처": "확인하지 못한 것",
                  "내용": ("성별·나이 등 인구통계 컬럼은 데이터셋 자체에 없어 "
                          "이런 축으로는 분석할 수 없었다."),
                  "포함": True})
    items.append({"출처": "확인하지 못한 것",
                  "내용": ("2025-01~2026-03 15개월 동안 월별 전후 비교 14개 "
                          "구간을 모두 확인했으나, 주지표(재직인원)가 판정 "
                          "기준(3%)만큼 움직인 적이 없어 가드레일 판정 "
                          "단계로 넘어간 적조차 없었다."),
                  "포함": True})
    return items


def limits_fixed_sentences(t: dict) -> list[str]:
    """7. 한계에 항상 넣는 두 문장. 편집 대상이 아니다."""
    months = sorted(t["HR_근태"]["년월"].astype(str).unique())
    return [
        "관측 데이터이므로 인과를 주장할 수 없다.",
        f"기간이 {months[0]}~{months[-1]}({len(months)}개월, "
        f"config.SNAPSHOT_DATE={C.SNAPSHOT_DATE} 기준)이므로, 그보다 "
        f"긴 주기의 변화는 이 데이터로 관측되지 않는다.",
    ]


# ── 사람이 쓰는 장 (제공) ─────────────────────────────────────────
def _s2_background(human: dict) -> dict:
    return {
        "title": "2. 배경", "kind": "human",
        "body": human.get("2. 배경", ""),
        "placeholder": "이 분석을 왜 했는지, 어떤 의사결정을 앞두고 있는지 적으십시오.",
    }


def _s6_interpretation(human: dict) -> dict:
    return {
        "title": "6. 해석", "kind": "human",
        "body": human.get("6. 해석", ""),
        "placeholder": ("숫자가 무엇을 뜻하는지 적으십시오. "
                        "자동으로 쓰지 않습니다 — 해석은 사람의 책임입니다."),
    }


def _s8_proposal(human: dict) -> dict:
    return {
        "title": "8. 제안", "kind": "human",
        "body": human.get("8. 제안", ""),
        "placeholder": ("무엇을 할 것인지, 무엇을 하지 않을 것인지 적으십시오. "
                        "선택하지 않으면 제안이 아니라 보고입니다."),
    }


# ── 조립 ──────────────────────────────────────────────────────────
def _safe(title: str, fn, *args) -> dict:
    """아직 안 채운 장은 "todo" 종류로 돌려준다. 골격 전용."""
    from core.todo import NotYet
    try:
        return fn(*args)
    except NotYet as e:
        return {"title": title, "kind": "todo", "body": "", "todo": e}


def build(t: dict, human: dict | None = None) -> list[dict]:
    """8장을 조립한다. human 은 사람이 쓴 장의 본문 딕셔너리.

    **순서와 자동/사람 구분은 바꾸지 않는다.** 장 개수는 도메인에 맞게 줄여도 되지만,
    해석과 제안을 자동으로 돌리는 것만은 하지 않는다.
    """
    human = human or {}
    return [
        _safe("1. 요약", _s1_summary, t),
        _s2_background(human),
        _safe("3. 방법", _s3_method, t),
        _safe("4. 결과", _s4_results, t),
        _safe("5. 실험", _s5_experiments, t),
        _s6_interpretation(human),
        _safe("7. 한계", _s7_limits, t),
        _s8_proposal(human),
    ]


def email_draft(t: dict, sections: list[dict]) -> dict:
    """이메일 초안. **실제로 보내지 않는다.**

    그대로 쓴다. 이메일 HTML은 인라인 스타일과 표 레이아웃만 쓴다 —
    외부 CSS·자바스크립트·이미지는 대부분의 메일 클라이언트가 막는다.

    받을 사람이 없으면 초안까지만 만들고, 게이트 3은 "보냈다고 치고" 기록만 남긴다.
    """
    summary = next((s["body"] for s in sections if s["title"].startswith("1.")), "")
    subject = f"[성장 리포트] {C.PERIOD[0][:7]}~{C.PERIOD[1][:7]}"
    html = (
        f'<div style="font-family:sans-serif;color:#0f172a;max-width:640px">'
        f'<h2 style="font-size:18px">{subject}</h2>'
        f'<p style="font-size:14px;line-height:1.7;white-space:pre-line">'
        f'{summary}</p>'
        f'<p style="font-size:12px;color:#64748b;margin-top:20px">'
        f'자동 생성 · {datetime.now().strftime("%Y-%m-%d %H:%M")}</p></div>')
    return {"to": C.EMAIL_TO_EXAMPLE, "subject": subject, "html": html}
