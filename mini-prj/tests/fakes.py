"""가짜 모델·가짜 retriever — 실제 LLM·임베딩 호출 없이 배선을 검증합니다.

AGENTS.md 규약: 채점 테스트는 실제 LLM API 를 호출하지 않습니다.
- ScriptedToolModel : 정해진 순서대로 도구 호출(AIMessage.tool_calls)을 돌려주고 마지막에 답 문장을 돌려줍니다.
- ExplodingModel    : 호출되면 바로 실패합니다. "가드에서 막혀 LLM 을 부르지 않았다"를 증명할 때 씁니다.
- FakeRetriever     : Titan 임베딩·Chroma 없이 doc_id 가 붙은 문서를 돌려줍니다.

한계: 가짜 모델은 우리가 정해 준 대로 도구를 부릅니다. 그래서 이 테스트는 "배선"(도구 연결, trace,
응답 스키마)만 검증하고, 모델이 경로를 스스로 잘 고르는지는 실제 Bedrock 평가(run_eval.py)에서 봅니다.
"""

from __future__ import annotations

import csv
import itertools
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "evaluation" / "test_queries.csv"

# 가짜 모델이 check_license 에 넘길 자산 ID (E100001 의 더미 노트북 — 교육용 더미 데이터입니다)
DEMO_ASSET_ID = "NB-2024-0137"

# 문항이 기대하는 문서 출처 — 질문 키워드로 고릅니다.
_DOC_HINTS = [("vpn", "vpn_guide"), ("VPN", "vpn_guide"), ("설치", "software_policy"),
              ("라이선스", "software_policy"), ("SW", "software_policy")]


def load_rows() -> list[dict]:
    """test_queries.csv 를 읽어 dict 목록으로 돌려줍니다."""
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def expected_tools(row: dict) -> list[str]:
    """expected_tools 칸("a;b")을 순서 있는 목록으로 바꿉니다."""
    return [t.strip() for t in (row.get("expected_tools") or "").split(";") if t.strip()]


def is_bypass(row: dict) -> bool:
    """note 가 [bypass] 로 시작하는 우회 문항인지 판정합니다."""
    return (row.get("note") or "").startswith("[bypass]")


class ScriptedToolModel:
    """정해진 대본(script)대로 응답하는 가짜 채팅 모델입니다.

    script 의 각 원소는 (도구이름, 인자dict) 묶음의 목록(=한 번의 tool_calls) 이거나, 최종 답 문자열입니다.
    """

    _ids = itertools.count(1)

    def __init__(self, script: list):
        self.script = list(script)
        self.calls = 0

    def bind_tools(self, tools):  # build_agent 가 부르는 인터페이스만 흉내 냅니다.
        return self

    def invoke(self, messages):
        self.calls += 1
        step = self.script.pop(0) if self.script else "대본이 끝났습니다."
        if isinstance(step, str):
            return AIMessage(content=step)
        return AIMessage(content="", tool_calls=[
            {"name": name, "args": args, "id": f"call_{next(self._ids)}", "type": "tool_call"}
            for name, args in step
        ])


class ExplodingModel:
    """호출되면 실패하는 모델 — 가드 차단 시 LLM 이 불리지 않았음을 증명합니다."""

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        raise AssertionError("가드에서 막혀야 할 요청인데 LLM 이 호출되었습니다.")


class FakeRetriever:
    """질문 키워드로 doc_id 를 골라 문서 1건을 돌려주는 가짜 retriever 입니다."""

    def invoke(self, query: str) -> list[Document]:
        doc_id = next((d for k, d in _DOC_HINTS if k in query), "account_policy")
        return [Document(page_content=f"[{doc_id}] 교육용 더미 문서 조각입니다.",
                         metadata={"doc_id": doc_id})]


def script_for(row: dict) -> list:
    """CSV 한 행의 expected_tools 대로 도구를 하나씩 부르고, 마지막에 답 문장을 내는 대본을 만듭니다."""
    args_by_tool = {
        "retrieve_docs": {"query": row["input"]},
        "check_license": {"asset_id": DEMO_ASSET_ID},
    }
    tools = expected_tools(row)
    script: list = [[(t, args_by_tool.get(t, {}))] for t in tools]
    if row["category"] == "negative":
        script.append("가이드에서 찾지 못했습니다. 자세한 내용은 #it-helpdesk 채널로 문의해 주세요.")
        return script
    # 실제 모델이 지켜야 할 답 형식(출처 doc_id 인용, 승인 대기 안내)을 대본에도 반영해
    # run_eval.py --fake 가 채점기의 '통과' 경로까지 점검하게 합니다.
    parts = ["요청하신 내용을 안내해 드립니다."]
    if "unlock_account" in tools:
        parts.append("잠금 해제 승인 요청이 접수되었습니다. 담당자 승인 후 해제됩니다.")
    if "retrieve_docs" in tools:
        doc_id = FakeRetriever().invoke(row["input"])[0].metadata["doc_id"]
        parts.append(f"(출처: {doc_id})")
    script.append(" ".join(parts))
    return script
