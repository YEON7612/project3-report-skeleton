# -*- coding: utf-8 -*-
"""my-report/제안카드.md 파서. /제안 이 만든 카드 파일을 proposal.build()가
쓰는 cards 딕셔너리로 바꾼다.

표에 있는 값(제목·분류·근거·비용·효과·되돌림)은 표에서 그대로 옮긴다 — 새로
쓰지 않는다. 근거 문장 안의 "격차 X%p"·"비중: ...(N명)의 Y%"는 정규식으로
뽑아 gap_pp·weight_pct·weight_denom에 채운다. **정규식이 못 찾으면 절대
추측하지 않고 None으로 남긴다** — proposal.py의 "한 장 요약"이 그 카드를
크기 비교에서 빼고 todo로 표시하는 근거가 된다.
"""
from __future__ import annotations

import re

# "## 제안 3 — 직급 축(부장·차장)..." 형태의 카드 제목 줄.
_CARD_HEADER = re.compile(r"^##\s*제안\s*\d+\s*—\s*(.+?)\s*$", re.MULTILINE)
# "| **분류** | 하지 말 것 |" 형태의 표 행. 라벨이 굵게 된 셀만 잡는다 —
# "반증"·"받은 반박" 표의 라벨 없는 행("| 무엇을 봤는가 | |")은 안 잡힌다.
_ROW = re.compile(r"^\|\s*\*\*(.+?)\*\*\s*\|\s*(.*?)\s*\|\s*$", re.MULTILINE)
# "격차 6.64%p" 같은 표현에서 숫자만.
_GAP = re.compile(r"격차\s*(\d+(?:\.\d+)?)\s*%p")
# "(244명)의 32.0%" 같은 표현에서 분모 인원과 비중 숫자를 함께.
_WEIGHT = re.compile(r"\((\d+)\s*명\)\s*의\s*(\d+(?:\.\d+)?)\s*%")


def _parse_table(block: str) -> dict[str, str]:
    """"| **라벨** | 내용 |" 행만 {라벨: 내용}으로 뽑는다."""
    return {m.group(1): m.group(2) for m in _ROW.finditer(block)}


def _extract_gap_weight(근거: str) -> tuple[float | None, float | None, str | None]:
    """근거 문장에서 "격차 X%p"와 "비중: (N명)의 Y%"를 뽑는다.

    둘 다 못 찾으면(패턴이 문장과 안 맞으면) None — 근거 문장을 다른 방식으로
    억지로 해석해 숫자를 만들어내지 않는다.
    """
    gap_m = _GAP.search(근거)
    gap_pp = float(gap_m.group(1)) if gap_m else None

    weight_pct = None
    weight_denom = None
    idx = 근거.find("비중")
    scope = 근거[idx:] if idx != -1 else 근거
    w_m = _WEIGHT.search(scope)
    if w_m:
        weight_denom = f"{w_m.group(1)}명"
        weight_pct = float(w_m.group(2))
    return gap_pp, weight_pct, weight_denom


def parse(text: str) -> dict:
    """제안카드.md 전체 텍스트 -> proposal.build()가 쓰는 cards 딕셔너리."""
    headers = list(_CARD_HEADER.finditer(text))
    cards = []
    for i, h in enumerate(headers):
        title = h.group(1).strip()
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]

        # 카드 안의 첫 표(분류·근거·비용·효과·되돌림)만 본다. "### 반증"부터는
        # 다른 표(확인 결과·받은 반박)라 안 섞이게 자른다.
        cut = block.find("###")
        main_block = block if cut == -1 else block[:cut]
        row = _parse_table(main_block)

        근거 = row.get("근거", "")
        gap_pp, weight_pct, weight_denom = _extract_gap_weight(근거)

        cards.append({
            "제목": title,
            "분류": row.get("분류", ""),
            "근거": 근거,
            "비용": row.get("비용", ""),
            "효과": row.get("효과", ""),
            "되돌림": row.get("되돌림", ""),
            "gap_pp": gap_pp,
            "weight_pct": weight_pct,
            "weight_denom": weight_denom,
        })
    return {"cards": cards}


def parse_file(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return parse(f.read())
