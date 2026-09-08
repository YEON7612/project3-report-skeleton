# -*- coding: utf-8 -*-
"""아직 채우지 않은 자리를 표시한다.

**이 파일은 골격에만 있다.** 전부 채우고 나면 지워도 된다.

왜 예외를 쓰는가 — 안 채운 함수가 그냥 None을 돌려주면 화면이 조용히 비거나
엉뚱한 곳에서 터진다. 어디를 아직 안 채웠는지 화면에 보이게 하려고 예외로 올리고,
페이지가 그것을 잡아 안내 카드를 그린다.

그래서 빈 골격도 켜진다. 채운 자리부터 화면이 살아난다.
"""
from __future__ import annotations


class NotYet(Exception):
    """아직 채우지 않았다. 페이지가 잡아 안내 카드를 그린다."""

    def __init__(self, day: str, task: str, hint: str = "", where: str = ""):
        self.day = day
        self.task = task
        self.hint = hint
        self.where = where
        super().__init__(f"{day} — {task}")


def todo(day: str, task: str, hint: str = "", where: str = "") -> None:
    """아직 안 채운 자리.

    day   : "Day2 실습 A" 처럼 교안의 어느 지점인지
    task  : 무엇을 만드는가
    hint  : 무엇을 먼저 정해야 하는가
    where : 어느 파일 어느 함수인가
    """
    raise NotYet(day, task, hint, where)


# ── 백로그 ────────────────────────────────────────────────────────
# 화면을 막지 않는 개선 아이디어. todo()로 예외를 던지지 않고 여기 comment로만
# 남긴다 — 아직 만들 시점이 아니거나, 신중한 검증이 먼저 필요한 것들.
#
#   입사1년내이탈률 월별 스파크라인 — 월별 KM 재적합 필요, 신중한 검증 후 구현.
#   monthly()가 이 지표를 안 내는 이유(core/metrics.py monthly() docstring)와
#   같다 — 매달 말을 가짜 스냅샷으로 놓고 KM을 다시 적합해야 하는데, 이건
#   새 계산 방법론이라 임의로 만들지 않기로 함(9주차 Day1).
