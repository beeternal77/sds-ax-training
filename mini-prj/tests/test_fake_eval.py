"""Seed AC5 — guardrail 을 뺀 17건을 가짜 모델로 돌려 배선을 확인합니다.

확인하는 것
- trace 에 기록된 도구 호출 순서가 expected_tools 와 같다
- negative(가이드에 없는 문의) 응답에 #it-helpdesk 안내가 있다
- 응답 스키마가 answer / contexts / trace 이고, retrieve_docs 를 부르면 contexts 에 doc_id 가 담긴다

한계: 도구 순서와 답 문장은 가짜 모델 대본(tests/fakes.py)이 정합니다.
모델이 경로를 스스로 잘 고르는지는 실제 Bedrock 평가(evaluation/run_eval.py)에서 검증합니다.
"""

import pytest

from src.agent import answer
from tests.fakes import FakeRetriever, ScriptedToolModel, expected_tools, load_rows, script_for

TOOL_NAMES = {"retrieve_docs", "get_my_account", "get_my_assets", "check_license", "unlock_account"}
ROWS = [r for r in load_rows() if r["category"] != "guardrail"]


def test_non_guardrail_count():
    assert len(ROWS) == 17


@pytest.mark.parametrize("row", ROWS, ids=lambda r: f"id{r['id']}-{r['category']}")
def test_fake_model_wiring(row):
    model = ScriptedToolModel(script_for(row))
    res = answer(row["input"], llm=model, retriever=FakeRetriever())

    # 응답 스키마
    assert set(res) == {"answer", "contexts", "trace"}
    assert res["answer"]

    # 도구 호출 순서 = expected_tools
    called = [t["step"] for t in res["trace"] if t["step"] in TOOL_NAMES]
    assert called == expected_tools(row)
    assert "agent" in [t["step"] for t in res["trace"]]   # 가드를 통과했으니 LLM 단계가 있어야 함

    # 문서 검색을 했다면 contexts 에 doc_id 가 담겨야 함
    if "retrieve_docs" in called:
        assert res["contexts"] and all("doc_id" in c for c in res["contexts"])

    # 가이드에 없는 문의 → 채널 안내
    if row["category"] == "negative":
        assert "#it-helpdesk" in res["answer"]
