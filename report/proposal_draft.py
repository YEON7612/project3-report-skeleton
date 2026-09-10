# -*- coding: utf-8 -*-
"""위험철회·요청(사람이 쓰는 두 절) 초안을 읽고 쓴다.

my-report/제안카드.md와 같은 경로 규칙(my-report/ 아래 markdown 파일
하나)·같은 패턴(주제별 "## " 구역으로 한 파일에 다 담는다)을 따른다 —
스키마(분류·근거·비용·효과·되돌림)는 카드와 다르므로 같은 파일에 억지로
끼워 넣지 않고 새 파일(제안서_작성.md)을 쓴다.

pages/5_제안서.py(쓰기)와 tests/test_proposal.py(읽기 전용 자가 검사)
둘 다 이 모듈 하나를 거친다 — 파싱 규칙이 두 곳에 따로 있으면 한쪽만
고쳤을 때 어긋난다.
"""
from __future__ import annotations

from datetime import datetime

from core import config as C

DRAFT_PATH = C.ROOT / "my-report" / "제안서_작성.md"
HUMAN_TITLES = [m["제목"] for m in C.PROPOSAL_SECTIONS if m["kind"] == "human"]


def load(path=DRAFT_PATH) -> dict[str, dict[str, str]]:
    """path를 읽어 {주제 제목: {절 제목: 글}}로 돌려준다. 파일이 없으면
    빈 dict — 아직 아무도 저장한 적이 없다는 뜻이다.
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    data = {}
    for block in text.split("\n## ")[1:]:
        title, _, rest = block.partition("\n")
        sections = {}
        for sblock in rest.split("\n### ")[1:]:
            sec_title, _, sec_body = sblock.partition("\n")
            sec_body = sec_body.rsplit("\n---", 1)[0].strip()
            sections[sec_title.strip()] = sec_body
        data[title.strip()] = sections
    return data


def save(data: dict[str, dict[str, str]], path=DRAFT_PATH) -> None:
    """data({주제 제목: {절 제목: 글}}) 전체를 path 하나에 다시 쓴다.
    이번에 저장하는 주제만 바뀌고 나머지 주제는 data 안에 그대로 들어
    있으므로(호출하는 쪽이 load()로 먼저 읽어 이번 주제 항목만 갱신해
    넘긴다) 다른 주제의 글은 지워지지 않는다 — 제안카드.md를 "덮어쓰지
    않는다"는 규칙과 같은 결과를 전체 재작성 방식으로 낸다.
    """
    lines = ["# 제안서 작성 — 위험·철회 기준 · 요청", "",
             f"최종 갱신: {datetime.now():%Y-%m-%d}", "", "---"]
    for title, sections in data.items():
        if not any((sections.get(t) or "").strip() for t in HUMAN_TITLES):
            continue
        lines += ["", f"## {title}"]
        for sec_title in HUMAN_TITLES:
            lines += ["", f"### {sec_title}", "", sections.get(sec_title, "").strip()]
        lines += ["", "---"]
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def session_key(topic_key: str, sec_title: str) -> str:
    """pages/5_제안서.py가 주제별 st.session_state 위젯 키를 만들 때 쓴다
    (topic["키"] 기준 — 제목이 아니라 키가 이 주제의 진짜 식별자다).
    """
    return f"proposal_draft::{topic_key}::{sec_title}"


def human_for(topic: dict) -> dict[str, str]:
    """topic 하나의 저장된 초안을 report.proposal.build()의 human 인자
    모양({절 제목: 글})으로 바로 돌려준다 — 저장된 게 없으면 두 절 모두
    빈 문자열(아직 안 쓴 상태, build()가 그대로 "없음" 처리한다).
    """
    saved = load().get(topic.get("제목", ""), {})
    return {sec_title: saved.get(sec_title, "") for sec_title in HUMAN_TITLES}
