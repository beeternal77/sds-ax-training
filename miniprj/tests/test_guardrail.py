"""Seed AC2 — 고정 guardrail 문항은 규칙 가드에서 막히고 LLM 을 부르지 않습니다.

우회([bypass]) 문항은 결과 안전성으로 판정하므로 여기서 다루지 않습니다. (실제 Bedrock 평가 전용)
"""

import pytest

from src.agent import REFUSALS, answer
from tests.fakes import ExplodingModel, is_bypass, load_rows

FIXED_GUARDRAIL_ROWS = [r for r in load_rows() if r["category"] == "guardrail" and not is_bypass(r)]


def test_fixed_guardrail_count():
    """고정 guardrail 문항은 3건입니다(id 18·19·20)."""
    assert [r["id"] for r in FIXED_GUARDRAIL_ROWS] == ["18", "19", "20"]


@pytest.mark.parametrize("row", FIXED_GUARDRAIL_ROWS, ids=lambda r: f"id{r['id']}")
def test_guardrail_blocks_without_llm(row):
    # ExplodingModel: 호출되면 실패 → 테스트가 통과하면 LLM 이 불리지 않은 것입니다.
    res = answer(row["input"], llm=ExplodingModel())

    assert res["answer"] in REFUSALS.values()            # REFUSALS 문구로 거절
    assert res["contexts"] == []                          # 문서 검색도 하지 않음
    steps = [t["step"] for t in res["trace"]]
    assert "agent" not in steps                           # trace 에 LLM 단계 없음
    assert steps[0] == "guard" and res["trace"][0]["output"] != "pass"


def test_guardrail_trace_masks_phone_number():
    """id 20 처럼 전화번호가 담긴 입력은 trace 에 원문이 남지 않습니다. (SERVICE.md 정책 5)"""
    row = next(r for r in FIXED_GUARDRAIL_ROWS if r["id"] == "20")
    res = answer(row["input"], llm=ExplodingModel())
    assert "010-1234-5678" not in str(res)
    assert "[전화번호]" in res["trace"][0]["input"]
