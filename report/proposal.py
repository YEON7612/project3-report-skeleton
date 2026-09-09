# -*- coding: utf-8 -*-
"""제안 리포트 7절 조립. /제안 이 만든 my-report/제안카드.md를 그대로 옮긴다.

자동: 한 장 요약·하지 말 것·다시 할 것·할 것·부록(근거 상세)
      — 전부 제안카드.md에 이미 적힌 값을 그대로 옮길 뿐 새로 판단하지 않는다.
사람: 이 제안이 틀린다면·적용 — 반증 종합과 실제로 무엇을 고를지는 사람이
      정한다. 여기서 대신 판단하지 않는다.
"""
from __future__ import annotations

from report.sections import BANNED, check_phrasing

CLASSES = ["하지 말 것", "다시 할 것", "할 것"]


def _card_lines(c: dict) -> list[str]:
    return [
        f"### {c.get('제목', '')}",
        f"- 근거: {c.get('근거', '')}",
        f"- 비용: {c.get('비용', '')}",
        f"- 효과: {c.get('효과', '')}",
        f"- 되돌림: {c.get('되돌림', '')}",
        "",
    ]


def _s1_summary(cards: dict) -> dict:
    """한 장 요약. 분류별 건수와 제목만 나열한다 — 순서를 매기지 않는다."""
    items = cards.get("cards", [])
    by_cls = {cls: [c for c in items if c.get("분류") == cls] for cls in CLASSES}

    lines = [
        f"총 {len(items)}개 제안 — "
        + " · ".join(f"{cls} {len(by_cls[cls])}건" for cls in CLASSES),
        "",
        "**나열 순서는 우선순위가 아니다** — 하지 말 것 → 다시 할 것 → 할 것 순으로",
        "고정해 뽑았을 뿐, 무엇을 먼저 할지는 적용 절에서 사람이 정한다.",
        "",
    ]
    for cls in CLASSES:
        if not by_cls[cls]:
            continue
        lines.append(f"**{cls}**")
        for c in by_cls[cls]:
            lines.append(f"- {c.get('제목', '')}")
        lines.append("")
    body = "\n".join(lines).strip()
    return {"title": "한 장 요약", "kind": "auto", "body": body}


def _s_class(cards: dict, cls: str) -> dict:
    """분류 하나(하지 말 것 / 다시 할 것 / 할 것)를 근거·비용·효과·되돌림과 함께 옮긴다."""
    items = [c for c in cards.get("cards", []) if c.get("분류") == cls]
    if not items:
        body = "해당 분류에 카드가 없습니다."
    else:
        lines: list[str] = []
        for c in items:
            lines.extend(_card_lines(c))
        body = "\n".join(lines).strip()
    return {"title": cls, "kind": "auto", "body": body}


def _s_falsification(human: dict) -> dict:
    """이 제안이 틀린다면. 사람이 쓴다 — "적용"과 같은 패턴이다.

    카드별 "반증" 칸(제안카드.md 안, 수요일에 채우는 자리)과는 다른 자리다 —
    거긴 카드마다 있는 개별 기록이고, 이 절은 문서 전체에 **하나만** 있는
    종합 판단이다. 카드마다 반복해서 만들지 않는다.
    """
    return {
        "title": "이 제안이 틀린다면", "kind": "human",
        "body": human.get("이 제안이 틀린다면", ""),
        "placeholder": (
            "이 제안이 틀렸다면 무엇 때문인지, 확인하려면 무엇을 보면 되는지 "
            "적으십시오."),
    }


def _s_application(human: dict) -> dict:
    """적용. "할 것" 중 실제로 무엇을 고를지는 사람이 쓴다 — 자동 조립하지 않는다."""
    return {
        "title": "적용", "kind": "human",
        "body": human.get("적용", ""),
        "placeholder": (
            "\"할 것\" 후보 중 이번에 실제로 무엇을 적용하기로 했는지 적으십시오. "
            "전부 고를 필요는 없고, 순서를 바꿔도 됩니다 — 선택은 사람이 합니다."),
    }


def _s_appendix(cards: dict) -> dict:
    """부록(근거 상세). 분류 구분 없이 카드 전체를 그대로 옮긴다 — 참고용 원문."""
    items = cards.get("cards", [])
    if not items:
        body = "카드가 없습니다."
    else:
        lines = []
        for c in items:
            lines.append(f"### [{c.get('분류', '')}] {c.get('제목', '')}")
            lines.extend(_card_lines(c)[1:])
            fb = c.get("받은반박")
            if fb:
                lines.append(f"- 받은 반박: {fb}")
                lines.append("")
        body = "\n".join(lines).strip()
    return {"title": "부록(근거 상세)", "kind": "auto", "body": body}


# ── 조립 ──────────────────────────────────────────────────────────
def build(cards: dict, human: dict | None = None) -> list[dict]:
    """제안 리포트 7절을 조립한다. cards는 my-report/제안카드.md를 파싱한 딕셔너리.

    cards 형태: {"cards": [{"제목", "분류", "근거", "비용", "효과", "되돌림",
                            "반증": {"가정","확인방법","확인결과","확신도"},
                            "받은반박": {...}}, ...]}

    **순서와 자동/사람 구분은 바꾸지 않는다**(sections.py의 build()와 같은 규칙).
    한 장 요약 → 하지 말 것 → 다시 할 것 → 할 것 → 이 제안이 틀린다면 → 적용 → 부록.

    check_phrasing()은 sections.py 것을 그대로 재사용한다 — 여기서 새로 만들지
    않는다. 자동 절뿐 아니라 사람이 쓰는 "이 제안이 틀린다면"·"적용" 절에도
    반드시 걸어, 걸린 절은 "phrasing_flags"에 걸린 단어를 담아 돌려준다(화면
    경고용, 값은 그대로 둔다 — 걸려도 저장은 한다는 원칙은 sections.py와 같다).
    """
    human = human or {}
    sections = [
        _s1_summary(cards),
        _s_class(cards, "하지 말 것"),
        _s_class(cards, "다시 할 것"),
        _s_class(cards, "할 것"),
        _s_falsification(human),
        _s_application(human),
        _s_appendix(cards),
    ]
    for sec in sections:
        sec["phrasing_flags"] = check_phrasing(sec["body"])
    return sections
