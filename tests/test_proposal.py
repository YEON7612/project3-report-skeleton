# -*- coding: utf-8 -*-
"""제안서 파이프라인 자가 검사.

  python tests/test_proposal.py

tests/test_app.py는 "렌더가 되는가"만 본다. 여기는 그보다 한 단계
더 들어가서, proposal_topics()가 돌려주는 후보 전부(기각된 것·근거
없는 것 포함)를 report.proposal.build()에 통과시켜 실제로 인쇄본에
나갈 문장·표 내용 자체가 다섯 조건을 지키는지 확인한다.

이 스크립트는 읽기만 한다 — 실패를 발견해도 report/proposal.py 등을
고치지 않는다(사용자에게 먼저 보고하는 몫이다).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config as C, load, metrics as M            # noqa: E402
from report import card_parser as CP, proposal as PR, proposal_draft as PD  # noqa: E402

CARD_PATH = C.ROOT / "my-report" / "제안카드.md"

# 문장·표에 남아 있으면 안 되는 코드 흔적 — 함수/컬럼/변수 이름
# (raw_count 등)과 밑줄로 이어붙인 값("1년차_잔류" 등) 둘 다 이 한
# 패턴으로 잡는다("영문·숫자·한글이 밑줄로 이어진 토큰"은 이 도메인
# 자연 문장에는 나오지 않는다 — CLAUDE.md "코드를 고칠 때 지킬 것").
_CODE_LEAK_RE = re.compile(r"[0-9A-Za-z가-힣]+_[0-9A-Za-z가-힣]+")

# "요청" 절 마지막 문장이 끝나야 하는 동사 계열(4번 검사).
_DECISION_STEMS = ("승인", "결정", "판단")

_요청_제목 = "무엇을 승인해 달라는 것인가?"


def _topic_label(topic: dict) -> str:
    tail = " (기각)" if topic.get("기각사유") else ""
    return f"{topic['제목']}{tail}"


def _last_sentence(text: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    return parts[-1] if parts else ""


def _section_blocks(html: str, n: int) -> list[str]:
    """to_html()이 만든 문서를 절 하나씩의 HTML 조각으로 자른다. 절은
    <div class="sec-block">...로 순서대로 이어지므로, n(result["절"]의
    길이)개로 나누면 blocks[i]가 result["절"][i]와 그대로 대응한다 —
    표 안 컬럼명·키 이름은 report/proposal.py의 _table_html()이 이미
    한글로 바꿔 놓았으므로, "표시되는 그대로"를 검사하려면 build()가
    돌려준 원본 "표" 객체가 아니라 반드시 이 렌더 결과를 봐야 한다.
    """
    blocks = html.split('<div class="sec-block">')[1:]
    return blocks[:n] if len(blocks) >= n else blocks + [""] * (n - len(blocks))


def check_blank(result: dict) -> list[str]:
    """1) 빈칸 0 — 자동 절의 "문장"이 비어 있으면 실패. 사람 절이 비어
    있는 건 정상이다(PROPOSAL_WORDS 안내 문구로 대체돼 인쇄된다) — 대신
    그 대체가 실제로 인쇄본에서 일어나는지, <p class="sec-body">가
    완전히 빈 채로 나가진 않는지까지 확인한다.
    """
    fails = []
    html = PR.to_html(result)
    blocks = _section_blocks(html, len(result["절"]))
    for sec, block in zip(result["절"], blocks):
        문장 = (sec.get("문장") or "").strip()
        if sec["kind"] == "auto" and not 문장:
            fails.append(f"[{sec['제목']}] 자동 절인데 문장이 비어 있다")
            continue
        m = re.search(r'<p class="sec-body">(.*?)</p>', block, re.S)
        if m is not None and not m.group(1).strip():
            fails.append(f"[{sec['제목']}] 인쇄본 문단이 완전히 비어 있다"
                        f"(PROPOSAL_WORDS 안내 문구조차 안 나감)")
    return fails


def check_terms(result: dict) -> list[str]:
    """2) 정체불명 용어 0 — check_phrasing()(인과 단정 표현)과 코드 흔적
    (raw_count류, 밑줄 이어진 값)을 6절 전부에서 찾는다. "문장"은 build()가
    돌려준 원본 문자열을, 표는 실제로 인쇄되는 HTML(to_html() 결과)을
    본다 — report/proposal.py의 _table_html()이 표의 컬럼명·키 이름을
    이미 한글로 바꾸므로, build()의 원본 "표" 객체를 그대로 스캔하면
    바뀌기 전 이름이 걸려 오탐이 난다.
    """
    fails = []
    html = PR.to_html(result)
    blocks = _section_blocks(html, len(result["절"]))
    for sec, block in zip(result["절"], blocks):
        flags = sec.get("phrasing_flags") or []
        if flags:
            fails.append(f"[{sec['제목']}] 인과 단정 표현: {', '.join(flags)}")

        leaks_문장 = sorted(set(_CODE_LEAK_RE.findall(sec.get("문장") or "")))
        if leaks_문장:
            fails.append(f"[{sec['제목']}] 문장에 코드 흔적으로 보이는 표현: "
                        f"{', '.join(leaks_문장)}")

        leaks_표 = sorted(set(_CODE_LEAK_RE.findall(block)) - set(leaks_문장))
        if leaks_표:
            fails.append(f"[{sec['제목']}] 인쇄본(표 포함)에 코드 흔적으로 "
                        f"보이는 표현: {', '.join(leaks_표)}")
    return fails


def check_chart_sentence(result: dict) -> list[str]:
    """3) 대응 문장 없는 그래프 0 — "차트" 값이 있는데 "문장"이 비어
    있으면 실패.
    """
    fails = []
    for sec in result["절"]:
        if sec.get("차트") is not None and not (sec.get("문장") or "").strip():
            fails.append(f"[{sec['제목']}] 차트({sec['차트']})는 있는데 설명 문장이 없다")
    return fails


def check_section_count(result: dict) -> list[str]:
    """5) 절 개수 — 요약 박스 제외 본문 절이 정확히 6개(고정)인지."""
    n = len(result["절"])
    return [] if n == 6 else [f"본문 절이 {n}개다(6개여야 한다)"]


def check_decision_verb(result: dict) -> tuple[list[str], str]:
    """4) 요청 절 마지막 "문장"(글자 수가 아니라 마침표·물음표·느낌표로
    나눈 문장 단위) 안에 승인/결정/판단 어간이 있는지 — 어간 뒤에 "해
    주시기 바랍니다"류 정중한 요청 어미가 얼마나 길게 붙든 상관없다(끝에서
    N글자만 보면 그 어미 길이에 따라 어간이 창 밖으로 밀려날 수 있어
    글자 수 기준을 쓰지 않는다). 사람이 아직 안 썼으면(빈 문자열) 검사를
    건너뛰고 SKIP으로 표시한다 — 미작성 상태를 실패로 세지 않는다.
    """
    ask = next((s for s in result["절"] if s["제목"] == _요청_제목), None)
    if ask is None:
        return [f"'{_요청_제목}' 절 자체를 찾을 수 없다"], "FAIL"
    문장 = (ask.get("문장") or "").strip()
    if not 문장:
        return [], "SKIP"
    last = _last_sentence(문장).rstrip(".!? ")
    if any(stem in last for stem in _DECISION_STEMS):
        return [], "PASS"
    return [f"마지막 문장 '{last}'에 승인/결정/판단 계열 동사가 없다"], "FAIL"


def run() -> bool:
    t = load.load_all()
    topics = M.proposal_topics(t)
    cards = CP.parse_file(CARD_PATH) if CARD_PATH.exists() else None

    checked = []
    any_fail = False
    for topic in topics:
        evidence = M.topic_evidence(t, topic)
        human = PD.human_for(topic)
        result = PR.build(topic, evidence, cards, human)

        c1 = check_blank(result)
        c2 = check_terms(result)
        c3 = check_chart_sentence(result)
        c5 = check_section_count(result)
        c4_fails, c4_status = check_decision_verb(result)

        row_fail = bool(c1 or c2 or c3 or c5 or c4_status == "FAIL")
        any_fail = any_fail or row_fail
        checked.append({
            "label": _topic_label(topic),
            "빈칸0": "PASS" if not c1 else "FAIL",
            "용어0": "PASS" if not c2 else "FAIL",
            "그래프대응": "PASS" if not c3 else "FAIL",
            "절개수6": "PASS" if not c5 else "FAIL",
            "결정동사": c4_status,
            "details": {"빈칸0": c1, "용어0": c2, "그래프대응": c3,
                       "절개수6": c5, "결정동사": c4_fails},
        })

    cols = ["빈칸0", "용어0", "그래프대응", "절개수6", "결정동사"]
    w = max(len(r["label"]) for r in checked) if checked else 20
    header = f"{'후보':<{w}}  " + "  ".join(f"{c:^8}" for c in cols)
    print(header)
    print("-" * len(header))
    for r in checked:
        line = f"{r['label']:<{w}}  " + "  ".join(f"{r[c]:^8}" for c in cols)
        print(line)

    fail_rows = [r for r in checked if any(r[c] == "FAIL" for c in cols)]
    if fail_rows:
        print(f"\n실패 상세 ({len(fail_rows)}개 후보):")
        for r in fail_rows:
            print(f"\n[{r['label']}]")
            for c in cols:
                for d in r["details"][c]:
                    print(f"  - ({c}) {d}")

    n_skip = sum(1 for r in checked if r["결정동사"] == "SKIP")
    print(f"\n총 {len(checked)}개 후보 검사 — 실패 {len(fail_rows)}개, "
         f"결정동사 검사 보류(요청 절 미작성) {n_skip}개")
    if any_fail:
        print("실패가 있습니다 — 코드는 고치지 않았습니다. 보고를 확인해 주세요.")
    else:
        print("전체 통과.")
    return not any_fail


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
