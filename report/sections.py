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

from core import config as C, metrics as M
from core.todo import todo

# ★ 자동 생성 문장에 인과를 단정하는 말을 쓰지 않는다.
#   관측 데이터로는 인과를 주장할 수 없는데, 방심하면 자동 문장이 인과를 쓴다.
#   내 도메인에만 있는 단정 표현이 있으면 여기에 더한다.
BANNED = ["때문에", "덕분에", "효과로", "입증되었", "증명되었", "확실히"]


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

    ★ Day4 실습 A에서 채웁니다.

    **수치는 쓰되 인과는 쓰지 않는다.** "A가 낮다"는 되고 "B 때문에 A가 낮다"는 안 된다.
    다 쓰고 나서 check_phrasing() 으로 자기 문장을 검사한다.

    반환: {"title": "1. 요약", "kind": "auto", "body": "..."}
    """
    todo("Day4 실습 A", "1. 요약",
         "무슨 수치를 요약에 넣습니까? 인과를 단정하지 않고 쓸 수 있습니까?",
         "report/sections.py  _s1_summary()")


def _s3_method(t: dict) -> dict:
    """3. 방법

    ★ Day4 실습 A에서 채웁니다.

    **분석 단위(그레인)를 반드시 밝힌다.** 읽는 사람이 숫자를 다시 세어볼 수 있어야 한다.
    무엇을 어떻게 셌는지, 무엇을 뺐는지, 어떤 검정을 썼는지.

    지표의 정의는 **위키가 원본**이다. 여기서 새로 정의하지 않는다.
    """
    todo("Day4 실습 A", "3. 방법",
         "분석 단위가 무엇입니까? 무엇을 세고 무엇을 뺐습니까?",
         "report/sections.py  _s3_method()")


def _s4_results(t: dict) -> dict:
    """4. 결과

    ★ Day4 실습 A에서 채웁니다.

    숫자를 나열하되 **해석하지 않는다.** 해석은 6장이고 사람이 쓴다.
    "낮다"까지가 결과이고 "왜 낮은가"는 해석이다.

    charts 키에 차트 이름을 넣으면 PDF에 그려진다. 예) ["funnel", "device"]
    """
    todo("Day4 실습 A", "4. 결과",
         "결과와 해석을 섞지 않았습니까? '왜'가 들어갔으면 6장으로 옮기십시오.",
         "report/sections.py  _s4_results()")


def _s5_experiments(t: dict) -> dict:
    """5. 실험

    ★ Day4 실습 A에서 채웁니다.

    **무효 판정된 실험은 사유만 적고 수치를 쓰지 않는다.** 화면에서 감춘 숫자를
    리포트에 쓰면 감춘 의미가 없다. metrics.experiment_results() 의 verdict 를 보고
    분기한다.

    실험이 없으면 이 장을 빼거나, 전후 비교를 적되
    **"인과를 주장할 수 없다"를 같은 문단에 남긴다.**
    """
    todo("Day4 실습 A", "5. 실험",
         "무효 실험의 수치를 쓰지 않았습니까? 실험이 없으면 이 장을 뺍니까?",
         "report/sections.py  _s5_experiments()")


def _s7_limits(t: dict) -> dict:
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
    """
    todo("Day4 실습 D", "7. 한계",
         "검증 경고를 전부 옮겼습니까? 7주차에 판정한 것 3건이 들어갔습니까?",
         "report/sections.py  _s7_limits()")


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
