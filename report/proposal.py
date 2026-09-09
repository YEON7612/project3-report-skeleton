# -*- coding: utf-8 -*-
"""제안 리포트 7절 조립. /제안 이 만든 my-report/제안카드.md를 그대로 옮긴다.

자동: 한 장 요약·하지 말 것·다시 할 것·할 것·부록(근거 상세)
      — 전부 제안카드.md에 이미 적힌 값을 그대로 옮길 뿐 새로 판단하지 않는다.
사람: 이 제안이 틀린다면·적용 — 반증 종합과 다음에 무엇을 볼지는 사람이
      정한다. 여기서 대신 판단하지 않는다. "적용"은 판단기준.md의 최근
      "오늘 내가 내린 결정" 문장을 읽기 전용 후보로 먼저 보여주지만, 그
      후보 중 무엇을 참고할지 고르고 다음에 볼 것을 쓰는 것은 사람이 한다.
"""
from __future__ import annotations

import re

from report.sections import BANNED, check_phrasing

CLASSES = ["하지 말 것", "다시 할 것", "할 것"]

# 판단기준.md의 "### 오늘 ~ 결정/판단" 절 헤더. 문서마다 "오늘 내가 실제로
# 내린 결정" · "오늘 실제로 내린 판단" · "오늘 내린 결정"처럼 표현이 조금씩
# 다르지만 전부 "오늘"과 "결정"/"판단"을 담고 있어 이 둘로만 잡는다.
_DECISION_HEADER = re.compile(r"^###\s*오늘.*?(?:결정|판단).*$", re.MULTILINE)
_BULLET = re.compile(r"^-\s+(.+)$", re.MULTILINE)


def _card_lines(c: dict) -> list[str]:
    return [
        f"### {c.get('제목', '')}",
        f"- 근거: {c.get('근거', '')}",
        f"- 비용: {c.get('비용', '')}",
        f"- 효과: {c.get('효과', '')}",
        f"- 되돌림: {c.get('되돌림', '')}",
        "",
    ]


def _card_size(c: dict) -> float | None:
    """카드의 크기(격차×비중). 두 필드(gap_pp·weight_pct)가 다 있어야 계산된다 —
    카드에 없으면 None. 텍스트 "근거"를 여기서 정규식으로 억지로 뜯지 않는다
    (깨지기 쉽고, 잘못 뜯으면 지어낸 숫자가 된다) — 그건 card_parser.py의
    몫이고, 거기서도 못 찾으면 이 두 필드가 None으로 넘어온다.
    """
    gap, weight = c.get("gap_pp"), c.get("weight_pct")
    if gap is None or weight is None:
        return None
    return gap * weight / 100


def _s1_summary(cards: dict) -> dict:
    """한 장 요약. 정확히 넉 줄 — 발견 / 제안 / 불확실 / 근거. 그 이상도
    이하도 아니다. 카드에 없는 값은 만들지 않고 "todo"라고 적는다.
    """
    items = cards.get("cards", [])
    sized = [(c, _card_size(c)) for c in items]
    sized = [(c, s) for c, s in sized if s is not None]

    # 1) 발견 — 크기(격차×비중) 최대 1건 + 분모
    if sized:
        top, score = max(sized, key=lambda x: x[1])
        denom = top.get("weight_denom") or "todo(분모 미기재)"
        line1 = (f"발견: {top.get('제목', '(제목 없음)')} — 격차 "
                 f"{top['gap_pp']:.2f}%p × 비중 {top['weight_pct']:.2f}% = "
                 f"{score:.2f}(카드 중 최대), 분모 {denom}")
    else:
        line1 = "발견: todo — 카드에 격차×비중(gap_pp·weight_pct) 수치가 없다"

    # 2) 제안 — 본문과 같은 순서(하지 말 것 → 다시 할 것 → 할 것)로 제목만
    groups = []
    for cls in CLASSES:
        titles = [c.get("제목", "") for c in items if c.get("분류") == cls]
        if titles:
            groups.append(f"[{cls}] " + ", ".join(titles))
    line2 = ("제안: " + " / ".join(groups)) if groups else "제안: todo — 카드가 없다"

    # 3) 불확실 — "발견"(크기 계산 가능한 카드 중 최대)과 같은 카드를 다시
    #    보여주지 않는다. 확신도는 반증 전(화요일)엔 전 카드가 예외 없이
    #    비어 있어 그 필터만으로는 "발견"과 항상 같은 카드로 수렴한다(항등
    #    필터가 되어버림 — 사용자 확인, 우연이 아니라 구조적으로 매번 그렇다).
    #    대신 "영향 범위(비중)는 있는데 격차를 %p로 못 낸 카드"를 찾는다 —
    #    비중이 커서 중요한 건 아는데, 다른 카드와 같은 잣대로 비교할 근거가
    #    카드에 없다는 게 진짜 약점이다.
    unquantified = [
        c for c in items
        if c.get("gap_pp") is None and c.get("weight_pct") is not None
    ]
    if unquantified:
        top_u = max(unquantified, key=lambda c: c["weight_pct"])
        denom_u = top_u.get("weight_denom") or "todo(분모 미기재)"
        line3 = (f"불확실: {top_u.get('제목', '(제목 없음)')} — 비중 "
                 f"{top_u['weight_pct']:.2f}%(분모 {denom_u})로 비중은 카드 "
                 f"중 최대인데, 격차를 %p로 못 냄(gap_pp 없음)")
    else:
        line3 = ("불확실: todo — 비중은 있는데 격차를 못 낸 카드가 없다"
                 "(전부 격차·비중 다 있거나, 둘 다 없다)")

    # 4) 근거 — 발견.md의 조회 일시·표본, 상세는 부록으로 미룬다
    src = cards.get("출처") or {}
    when = src.get("조회일시") or "todo(발견.md에 조회 일시 없음)"
    sample = src.get("표본") or "todo(발견.md에 단일 표본 값 없음)"
    line4 = f"근거: 조회 일시 {when} · 표본 {sample} · 상세는 부록"

    body = "\n".join([line1, line2, line3, line4])
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


def _recent_decisions(judgment_text: str) -> list[str]:
    """판단기준.md에서 가장 최근 "오늘 ~ 결정/판단" 절의 불릿만 뽑는다.

    여러 날짜의 절을 다 모으지 않고 **가장 최근 절 하나만** 쓴다 — "오늘"은
    그 절이 쓰인 날 하루를 가리키는 말이라, 여러 날짜를 섞으면 다른 날의
    "오늘"이 뒤섞여 더 이상 오늘이 아니게 된다. 문장은 원문 그대로 옮긴다 —
    요약하거나 새로 쓰지 않는다.
    """
    headers = list(_DECISION_HEADER.finditer(judgment_text))
    if not headers:
        return []
    last = headers[-1]
    start = last.end()
    next_header = re.search(r"^#{2,3}\s", judgment_text[start:], re.MULTILINE)
    end = start + next_header.start() if next_header else len(judgment_text)
    block = judgment_text[start:end]
    return [m.group(1).strip() for m in _BULLET.finditer(block)]


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


def _s_application(human: dict, judgment_text: str = "") -> dict:
    """적용. kind는 human이지만 판단기준.md의 가장 최근 "오늘 내가 내린
    결정" 문장을 참고 후보로 먼저 자동으로 보여준다 — 후보는 여기서도
    화면에서도 읽기 전용이다(고치지 않고 그대로 옮긴 값이라 편집 대상이
    아니다). 사람이 실제로 쓰는 건 그 후보를 보고 "다음에 무엇을 볼
    것인가" 한 가지뿐이다 — 후보 중 무엇을 참고할지 고르는 것과, 다음에
    볼 것을 쓰는 것만 사람이 한다.
    """
    return {
        "title": "적용", "kind": "human",
        "candidates": _recent_decisions(judgment_text),
        "body": human.get("적용", ""),
        "placeholder": (
            "위 후보(오늘 내가 내린 결정)를 참고해, 다음에 무엇을 볼 것인지 "
            "적으십시오."),
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
def build(cards: dict, human: dict | None = None, judgment_text: str = "") -> list[dict]:
    """제안 리포트 7절을 조립한다. cards는 my-report/제안카드.md를 파싱한 딕셔너리.

    cards 형태: {"cards": [{"제목", "분류", "근거", "비용", "효과", "되돌림",
                            "gap_pp", "weight_pct", "weight_denom"(선택 —
                            "한 장 요약"의 크기 계산에만 쓴다. card_parser.py가
                            근거 문장에서 정규식으로 뽑아 채운다 — 못 찾으면
                            None이고, 그 카드는 크기 비교에서 빠진다),
                            "반증": {"가정","확인방법","확인결과","확신도"},
                            "받은반박": {...}}, ...],
                "출처": {"조회일시", "표본"}(선택 — 발견.md에서 옮겨 온 메타.
                        없으면 "한 장 요약"의 근거 줄이 todo로 나온다)}

    cards는 보통 report.card_parser.parse_file("my-report/제안카드.md")의
    결과를 그대로 넣는다.

    judgment_text는 판단기준.md 원문 텍스트(호출하는 쪽이 읽어서 넘긴다 —
    여기서는 파일을 직접 읽지 않는다). "적용" 절의 후보 목록(candidates)을
    뽑는 데만 쓴다. 안 넘기면(빈 문자열) 후보 없이 빈 목록으로 나온다.

    **순서와 자동/사람 구분은 바꾸지 않는다**(sections.py의 build()와 같은 규칙).
    한 장 요약 → 하지 말 것 → 다시 할 것 → 할 것 → 이 제안이 틀린다면 → 적용 → 부록.

    "적용" 절은 kind가 human이지만 "candidates"(판단기준.md 최근 절의 "오늘
    내가 내린 결정" 문장 — 읽기 전용) 키를 함께 돌려준다. 화면은 이 후보를
    편집 UI 없이 그대로 보여주고, 사람은 그 아래에 "다음에 무엇을 볼
    것인가"만 쓴다.

    check_phrasing()은 sections.py 것을 그대로 재사용한다 — 여기서 새로 만들지
    않는다. 자동 절뿐 아니라 사람이 쓰는 "이 제안이 틀린다면"·"적용" 절에도
    반드시 걸어, 걸린 절은 "phrasing_flags"에 걸린 단어를 담아 돌려준다(화면
    경고용, 값은 그대로 둔다 — 걸려도 저장은 한다는 원칙은 sections.py와 같다).
    candidates는 판단기준.md에서 그대로 옮긴 과거 기록이라 이 검사 대상이
    아니다 — body(사람이 지금 쓴 문장)만 검사한다.
    """
    human = human or {}
    sections = [
        _s1_summary(cards),
        _s_class(cards, "하지 말 것"),
        _s_class(cards, "다시 할 것"),
        _s_class(cards, "할 것"),
        _s_falsification(human),
        _s_application(human, judgment_text),
        _s_appendix(cards),
    ]
    for sec in sections:
        sec["phrasing_flags"] = check_phrasing(sec["body"])
    return sections
