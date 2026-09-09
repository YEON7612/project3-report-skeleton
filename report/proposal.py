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

import html as _html
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


# ── HTML 내보내기 ────────────────────────────────────────────────────
# 제안서_템플릿.html(프로젝트 루트)의 구조·클래스를 그대로 옮겨 썼다. CSS는
# 그 파일의 <style> 내용을 그대로 복사했다 — 여기서 다시 읽지 않는다(단일
# 파일로 만들어야 하고, 배포 환경에 그 파일이 없어도 to_html()이 동작해야
# 하기 때문). 클래스 이름·색·의미는 템플릿과 완전히 같다.
_CSS = """
:root{
  --ok:#10b981; --warn:#f59e0b; --block:#f43f5e; --none:#64748b;
  --primary:#4f46e5; --ink:#0f172a; --muted:#64748b;
  --line:#e2e8f0; --bg:#f8fafc; --surface:#ffffff;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:Pretendard,-apple-system,'Malgun Gothic',sans-serif;
  background:var(--bg); color:var(--ink); font-size:14px; line-height:1.75;
}
.page{max-width:900px; margin:0 auto; padding:40px 36px 80px}
.num{font-variant-numeric:tabular-nums; font-feature-settings:"tnum"}

.cover{border-bottom:3px solid var(--primary); padding-bottom:26px; margin-bottom:32px}
.cover .kicker{font-size:12px; font-weight:700; color:var(--primary); letter-spacing:.08em}
.cover h1{font-size:30px; font-weight:800; margin:10px 0 6px; line-height:1.3}
.cover .sub{font-size:14px; color:var(--muted)}
.cover .meta{display:flex; gap:22px; flex-wrap:wrap; margin-top:18px; font-size:12px; color:var(--muted)}
.cover .meta b{color:var(--ink); font-weight:600}

.summary{background:var(--surface); border:1px solid var(--line);
  border-top:4px solid var(--primary); border-radius:14px; padding:26px 28px; margin-bottom:34px}
.summary h2{font-size:13px; font-weight:700; color:var(--primary); letter-spacing:.06em; margin:0 0 16px}
.srow{display:flex; gap:16px; padding:11px 0; border-top:1px solid var(--line)}
.srow:first-of-type{border-top:none; padding-top:0}
.srow .k{flex:0 0 74px; font-size:11px; font-weight:700; color:var(--muted); letter-spacing:.04em; padding-top:3px}
.srow .v{flex:1}
.srow .v .lead{font-size:15px; font-weight:600; line-height:1.6}
.plist{margin:0; padding:0; list-style:none}
.plist li{display:flex; gap:9px; align-items:baseline; padding:3px 0}
.plist .n{flex:0 0 18px; font-weight:700; color:var(--muted)}

h2.sec{font-size:20px; font-weight:800; margin:44px 0 4px; padding-top:8px}
h2.sec .no{color:var(--primary); margin-right:9px}
.sec-lead{color:var(--muted); font-size:13px; margin:0 0 20px}
h3{font-size:15px; font-weight:700; margin:26px 0 10px}

table{border-collapse:collapse; width:100%; font-size:13px; margin:12px 0 16px; page-break-inside:avoid}
th,td{border:1px solid var(--line); padding:7px 10px; text-align:left; vertical-align:top}
th{background:#f8fafc; font-weight:700; font-size:12px; color:#334155}
td.r,th.r{text-align:right}
tr.hl td{background:rgba(244,63,94,.05)}
tr.dim td{color:var(--muted)}

.badge{display:inline-flex; align-items:center; gap:5px; font-size:11px;
  font-weight:700; padding:3px 10px; border-radius:999px; white-space:nowrap}
.b-ok{background:rgba(16,185,129,.12); color:var(--ok)}
.b-warn{background:rgba(245,158,11,.14); color:#b45309}
.b-block{background:rgba(244,63,94,.12); color:var(--block)}
.b-none{background:rgba(100,116,139,.12); color:var(--none)}

.prop{background:var(--surface); border:1px solid var(--line); border-left:5px solid var(--line);
  border-radius:12px; padding:20px 24px; margin:16px 0; page-break-inside:avoid}
.prop.stop{border-left-color:var(--block); background:#fff8f9}
.prop.redo{border-left-color:var(--warn); background:#fffdf7}
.prop.go{border-left-color:var(--ok)}
.prop .cls{font-size:11px; font-weight:700; letter-spacing:.06em; color:var(--muted)}
.prop h4{font-size:17px; font-weight:700; margin:4px 0 14px}
.prop dl{display:grid; grid-template-columns:64px 1fr; gap:7px 14px; margin:0; font-size:13px}
.prop dt{font-weight:700; color:var(--muted); font-size:12px; padding-top:1px}
.prop dd{margin:0}

.lab{font-size:10.5px; font-weight:700; padding:1px 6px; border-radius:4px; margin-right:6px; letter-spacing:.03em}
.l-obs{background:rgba(16,185,129,.13); color:#047857}
.l-asm{background:rgba(245,158,11,.16); color:#b45309}
.l-est{background:rgba(100,116,139,.13); color:#475569}
.unknown{color:var(--warn); font-weight:700}

.callout{border-left:3px solid var(--warn); background:rgba(245,158,11,.07);
  padding:12px 16px; border-radius:0 8px 8px 0; font-size:13px; color:#78350f;
  margin:14px 0; page-break-inside:avoid}
.callout.info{border-left-color:var(--primary); background:rgba(79,70,229,.05); color:#3730a3}
.callout.stop{border-left-color:var(--block); background:rgba(244,63,94,.06); color:#9f1239}

figure{margin:18px 0; page-break-inside:avoid}
figcaption{font-size:11.5px; color:var(--muted); margin-top:7px}
.chart{background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:20px 22px}
.row{display:flex; align-items:center; gap:12px; margin:9px 0}
.row .lb{flex:0 0 150px; text-align:right; font-size:12.5px; color:#334155}
.row .track{flex:1; background:#f1f5f9; border-radius:4px; height:22px; position:relative}
.row .bar{height:22px; border-radius:4px; background:var(--primary); opacity:.85}
.row .bar.hl{background:var(--block); opacity:1}
.row .bar.mid{background:var(--warn); opacity:1}
.row .vv{flex:0 0 200px; font-size:12.5px; font-weight:700;
  font-variant-numeric:tabular-nums}
.row .vv small{font-weight:400; color:var(--muted); margin-left:8px}

.appendix{margin-top:52px; padding-top:26px; border-top:3px double var(--line)}
.appendix h2.sec{font-size:17px}
.small{font-size:12px; color:var(--muted)}

.todo{background:rgba(79,70,229,.06); color:#3730a3; border-radius:4px; padding:0 4px}

@page{size:A4; margin:18mm 16mm 20mm 16mm}
@media print{
  body{background:#fff; font-size:10.5pt}
  .page{max-width:none; padding:0}
  h2.sec{page-break-after:avoid}
  .summary,.prop,figure,table,.callout,.chart{page-break-inside:avoid}
  .appendix{page-break-before:always}
  .todo{background:none}
}
"""

_CLASS_CSS = {"하지 말 것": "stop", "다시 할 것": "redo", "할 것": "go"}
_CLASS_BADGE = {
    "하지 말 것": ("b-block", "✕ 하지 말 것"),
    "다시 할 것": ("b-warn", "▲ 다시 할 것"),
    "할 것": ("b-ok", "● 할 것"),
}
_NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?(?:%p|%|명|건|시간|점|배)?")
_PROP_GROUP = re.compile(r"\[([^\]]+)\]\s*([^/]+)")
_FIELD_LINE = re.compile(r"^-\s*([^:]+):\s*(.*)$")


def _todo(placeholder: str) -> str:
    return f'<span class="todo">{_html.escape(placeholder, quote=False)}</span>'


def _text(value: str) -> str:
    """secs에서 가져온 실제 문장을 이스케이프하고, 그 안의 숫자에
    class="num"을 붙인다. 값이 비어 있으면 todo로 남긴다 — 빈 문자열을
    그대로 보여주지 않는다.
    """
    value = (value or "").strip()
    if not value:
        return _todo("[ 아직 안 채워짐 ]")
    escaped = _html.escape(value, quote=False)
    return _NUM.sub(lambda m: f'<span class="num">{m.group(0)}</span>', escaped)


def _parse_summary_line(body: str, key: str) -> str:
    """_s1_summary()가 만든 "발견: .../ 제안: .../ 불확실: .../ 근거: ..."
    네 줄 중 하나를 접두어로 찾는다 — proposal.py 자신이 만드는 고정 형식이라
    안전하게 되돌릴 수 있다(card_parser.py처럼 자유 텍스트를 추측하지 않는다).
    """
    prefix = f"{key}: "
    for line in body.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):]
    return ""


def _parse_card_blocks(body: str) -> list[dict]:
    """_card_lines()가 만든 "### 제목\\n- 근거: ..\\n..." 블록을 되돌린다."""
    blocks = re.split(r"(?=^### )", body, flags=re.MULTILINE)
    cards = []
    for b in blocks:
        b = b.strip()
        if not b.startswith("### "):
            continue
        lines = b.splitlines()
        row = {"제목": lines[0][4:].strip()}
        for line in lines[1:]:
            m = _FIELD_LINE.match(line)
            if m:
                row[m.group(1).strip()] = m.group(2).strip()
        cards.append(row)
    return cards


def _cover_html(summary_body: str) -> str:
    return f"""<div class="cover">
  <div class="kicker">성과 개선 제안</div>
  <h1>{_todo("[ 무엇을 하자고 하는지 한 줄 ]")}</h1>
  <div class="sub">{_todo("[ 어느 분석의 결과인지 · 제안 몇 건인지 ]")}</div>
  <div class="meta">
    <span>데이터셋 <b class="num">{_todo("[ 이름 ]")}</b></span>
    <span>기간 <b class="num">{_todo("[ 시작 ~ 끝 ]")}</b></span>
    <span>작성 <b class="num">{_todo("[ 날짜 ]")}</b></span>
    <span>검증 <b>{_todo("[ 통과 / 경고 / 차단 ]")}</b></span>
  </div>
</div>"""


def _summary_html(sec: dict) -> str:
    body = sec.get("body", "")
    found = _parse_summary_line(body, "발견")
    prop_line = _parse_summary_line(body, "제안")
    uncertain = _parse_summary_line(body, "불확실")
    basis = _parse_summary_line(body, "근거")

    groups = _PROP_GROUP.findall(prop_line)
    if groups:
        items = []
        for i, (cls, titles) in enumerate(groups, start=1):
            css, label = _CLASS_BADGE.get(cls.strip(), ("b-none", cls.strip()))
            titles_text = titles.strip().rstrip("/").strip()
            items.append(
                f'<li><span class="n">{"①②③④⑤"[i - 1] if i <= 5 else i}</span>'
                f'<span><span class="badge {css}">{label}</span> '
                f'{_text(titles_text)}</span></li>')
        plist = f'<ul class="plist">{"".join(items)}</ul>'
    else:
        plist = f'<ul class="plist"><li>{_todo("[ 하지 말 것 / 다시 할 것 / 할 것 후보가 없음 ]")}</li></ul>'

    return f"""<div class="summary">
  <h2>한 장 요약</h2>
  <div class="srow"><div class="k">발견</div>
    <div class="v"><div class="lead">{_text(found)}</div></div></div>
  <div class="srow"><div class="k">제안</div>
    <div class="v">{plist}</div></div>
  <div class="srow"><div class="k">불확실</div>
    <div class="v">{_text(uncertain)}</div></div>
  <div class="srow"><div class="k">근거</div>
    <div class="v small">{_text(basis)}</div></div>
</div>"""


def _s1_html() -> str:
    """"무엇을 발견했는가" — 퍼널 표·막대 차트는 secs에 없는 데이터(funnel()
    결과)라 여기서 만들지 않는다. 자리만 템플릿 그대로 남긴다.
    """
    return f"""<h2 class="sec"><span class="no">1</span>무엇을 발견했는가</h2>
<p class="sec-lead">{_todo("[ 어디서 빠지는가 / 무엇이 다른가 — funnel() 결과가 secs에 없어 여기서 못 채움 ]")}</p>"""


def _s2_html() -> str:
    """"왜 이런 일이 생겼는가" — 분해축 표(funnel_by() 결과)도 secs에 없다."""
    return f"""<h2 class="sec"><span class="no">2</span>왜 이런 일이 생겼는가</h2>
<p class="sec-lead">{_todo("[ 어느 구간을 몇 개 축으로 쪼갰는지 — funnel_by() 결과가 secs에 없어 여기서 못 채움 ]")}</p>"""


def _prop_card_html(cls: str, sec: dict) -> str:
    css = _CLASS_CSS[cls]
    badge_css, badge_label = _CLASS_BADGE[cls]
    cards = _parse_card_blocks(sec.get("body", ""))
    if not cards:
        return f"""<div class="prop {css}">
  <div class="cls">{badge_label}</div>
  <h4>{_todo("[ 해당 분류에 카드가 없음 ]")}</h4>
</div>"""
    out = []
    for c in cards:
        out.append(f"""<div class="prop {css}">
  <div class="cls">{badge_label}</div>
  <h4>{_text(c.get("제목", ""))}</h4>
  <dl>
    <dt>근거</dt><dd>{_text(c.get("근거", ""))}</dd>
    <dt>비용</dt><dd>{_text(c.get("비용", ""))}</dd>
    <dt>효과</dt><dd>{_text(c.get("효과", ""))}</dd>
    <dt>되돌림</dt><dd>{_text(c.get("되돌림", ""))}</dd>
    <dt>확신도</dt><dd>{_todo("[ 카드에 확신도 필드가 없어 여기서 못 채움 ]")}</dd>
  </dl>
</div>""")
    return "\n".join(out)


def _s3_html(sec_by_title: dict) -> str:
    parts = ['<h2 class="sec"><span class="no">3</span>무엇을 하자고 제안하는가</h2>',
             '<p class="sec-lead">멈추는 것부터 적는다. 비용이 0이고 근거가 관측이기 때문이다.</p>']
    for cls in CLASSES:
        parts.append(_prop_card_html(cls, sec_by_title[cls]))
    return "\n".join(parts)


def _s4_html(sec_by_title: dict) -> str:
    sec = sec_by_title["이 제안이 틀린다면"]
    return f"""<h2 class="sec"><span class="no">4</span>이 제안이 틀린다면</h2>
<p>{_text(sec.get("body", ""))}</p>
<div class="callout stop">
  <b>철회 조건 —</b> {_todo("[ 무엇이 ] [ 얼마 ] 가 될 때까지 [ 어느 지표 ] 가 [ 얼마 ] 에 이르지 못하면 이 제안을 철회한다.")}
</div>"""


def _s5_html(sec_by_title: dict) -> str:
    sec = sec_by_title["적용"]
    candidates = sec.get("candidates") or []
    if candidates:
        rows = "\n".join(
            f'<tr><td>{_text(c)}</td><td>{_todo("[ 어디에 적용하면 무엇이 달라지나 ]")}</td></tr>'
            for c in candidates)
    else:
        rows = (f'<tr><td>{_todo("[ 판단기준.md 에서 후보를 찾지 못함 ]")}</td>'
                f'<td>{_todo("[ 어디에 적용하면 무엇이 달라지나 ]")}</td></tr>')
    next_look = sec.get("body", "")
    return f"""<h2 class="sec"><span class="no">5</span>적용</h2>
<p class="sec-lead">이번 분석에서 쓴 방법 중 앞으로도 쓸 것 — 판단기준.md 최근 절에서 자동으로 가져온 후보.</p>
<table>
  <thead><tr><th>판단 기준</th><th>어디에 적용하면 무엇이 달라지나</th></tr></thead>
  <tbody>
{rows}
  </tbody>
</table>
<p class="small"><b>다음에 볼 것</b> — {_text(next_look)}</p>"""


def _appendix_html(sec_by_title: dict) -> str:
    sec = sec_by_title["부록(근거 상세)"]
    body = sec.get("body", "")
    body_html = _text(body) if body.strip() else _todo("[ 카드가 없음 ]")
    body_html = body_html.replace("\n", "<br>")
    return f"""<div class="appendix">
<h2 class="sec">부록 A · 근거 상세</h2>
<p class="small">{body_html}</p>

<h2 class="sec">부록 B · 방법</h2>
<table><tbody>
  <tr><th>분석 단위</th><td>{_todo("[ 무엇을 하나로 셌는지 · 왜 — secs에 없음 ]")}</td></tr>
  <tr><th>기간</th><td class="num">{_todo("[ 시작 ~ 끝 ]")}</td></tr>
  <tr><th>판정 기준</th><td>{_todo("[ 임계값 · 최소 표본 · 유효 구간 ]")}</td></tr>
  <tr><th>가정값</th><td>{_todo("[ 무엇을 가정했는지 전부 ]")}</td></tr>
</tbody></table>

<h2 class="sec">부록 C · 한계</h2>
<ol class="small" style="line-height:2">
  <li>{_todo("[ 데이터에 없어서 못 본 것 ]")}</li>
  <li>{_todo("[ 찾아봤는데 신호가 없던 것 ]")}</li>
  <li>{_todo("[ 뺐다는 사실을 남기는 것 ]")}</li>
</ol>

<h2 class="sec">부록 D · 검토 이력</h2>
<table>
  <thead><tr><th>지적</th><th>처리</th></tr></thead>
  <tbody>
    <tr><td>{_todo("[ 무엇을 지적받았나 ]")}</td>
        <td>{_todo("[ 확인함 / 배제 못 함으로 추가 / 안 받아들임 — 이유 ]")}</td></tr>
  </tbody>
</table>

<h2 class="sec">부록 E · 대시보드</h2>
<p class="small">{_todo("[ URL — secs에 없음 ]")}</p>
</div>"""


def to_html(secs: list[dict]) -> str:
    """제안 리포트를 단일 HTML 파일로 만든다. 구조·클래스는 프로젝트 루트의
    제안서_템플릿.html을 그대로 따른다(CSS도 그 파일에서 그대로 복사) — 여기
    함수는 그 파일을 런타임에 읽지 않는다. 외부 CSS·이미지·CDN을 쓰지
    않으므로 나온 문자열 하나로 완결된 파일이다.

    secs는 build()의 반환값을 그대로 받는다. secs에 실제로 있는 값(한 장
    요약 네 줄, 분류별 카드의 근거·비용·효과·되돌림, "적용"의 후보·다음에
    볼 것, 부록 본문)만 채운다. 템플릿이 요구하지만 secs에 없는 자리
    (표지 메타데이터, 퍼널·분해축 표, 카드 확신도, 부록 B~E 상세, 철회
    조건)는 값을 지어내지 않고 class="todo"로 남긴다 — 채우지 않는다.

    본문 안의 숫자에는 class="num"을 붙인다(font-variant-numeric으로만
    보이게 하는 순수 표시용 마크업이라, 값 자체를 바꾸지 않는다).
    """
    sec_by_title = {s["title"]: s for s in secs}
    summary_sec = sec_by_title.get("한 장 요약", {"body": ""})

    body_parts = [
        '<div class="page">',
        _cover_html(summary_sec.get("body", "")),
        _summary_html(summary_sec),
        _s1_html(),
        _s2_html(),
        _s3_html(sec_by_title),
        _s4_html(sec_by_title),
        _s5_html(sec_by_title),
        _appendix_html(sec_by_title),
        '</div>',
    ]

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>제안서</title>
<style>{_CSS}</style>
</head>
<body>
{"".join(body_parts)}
</body>
</html>
"""
