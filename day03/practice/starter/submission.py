"""Day 3 — 장애 원인 조사 Agent.

도구 세 개로 장애 원인을 좁혀 갑니다.

[중요]
  1. 함수·상수 이름을 바꾸지 마세요.
  2. 모델은 함수 안에서 만듭니다. `llm` 인자가 오면 그것을 씁니다.
  3. 도구는 결정적이어야 합니다. 같은 인자에 항상 같은 결과를 돌려주세요.
"""

from __future__ import annotations

import json
from pathlib import Path
#=== Start of Modify Block
# [수정 이유] get_logs의 since 인자는 생략할 수 있어야 하므로 Optional 타입이 필요합니다.
# 원문: from typing import Any
from typing import Any, Optional
#=== End of Modify Block

#=== Start of Insert Block
# [추가 이유] 그래프를 직접 조립하려면 메시지 타입, StateGraph, ToolNode가 필요합니다.
#            (모델 생성이 아니라 import라서 모듈 최상단에 둬도 규약 위반이 아닙니다.)
from langchain_core.messages import AIMessage, SystemMessage
#=== End of Insert Block
from langchain_core.tools import tool
#=== Start of Insert Block
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
#=== End of Insert Block
from pydantic import BaseModel, Field

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = "us-east-1"

DATA = json.loads(
    (Path(__file__).resolve().parent.parent / "data" / "ops_fixtures.json").read_text(
        encoding="utf-8"
    )
)


def _default_llm():
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(model=MODEL_ID, region_name=REGION, temperature=0)


#=== Start of Insert Block
# [추가 이유] 세 도구가 모두 "빈 이름 / 없는 서비스"를 같은 방식으로 처리해야
#            모델이 일관된 문장을 읽습니다. 공개 테스트도 없는 서비스를 조회하면 '없'이 들어간
#            안내 문자열을 기대하므로, 공통 검사를 함수 하나로 뺐습니다.
def _check_service(service: str, table: dict) -> tuple[str, Optional[str]]:
    """서비스 이름을 정리하고, 조회할 수 없으면 안내 문장을 함께 돌려줍니다.

    Returns:
        (정리된 서비스 이름, 오류 안내 문장 또는 None)
    """
    name = (service or "").strip()
    if not name:
        return name, "서비스 이름이 비어 있습니다. 조회할 서비스 이름을 넣어 주세요. (예: payment-api)"
    if name not in table:
        known = ", ".join(sorted(table)) or "없음"
        return name, f"'{name}' 서비스의 데이터가 없습니다. 조회 가능한 서비스: {known}"
    return name, None
#=== End of Insert Block


# ══════════════════════════════════════════════════════════════════
# 기초 파트 (7점)
# ══════════════════════════════════════════════════════════════════

#=== Start of Modify Block
# [수정 이유] 모델은 Field description을 읽고 인자 값을 정합니다. TODO로 두면 모델이
#            무엇을 넣을지 몰라 서비스 이름을 지어낼 수 있으므로 형식과 예시를 적습니다.
# 원문: # TODO: 각 도구의 인자 스키마를 정의하세요.
# 원문: class DeployArgs(BaseModel):
# 원문:     service: str = Field(..., description="TODO: 어떤 값을 넣어야 하는지 적으세요.")
class DeployArgs(BaseModel):
    """get_deploy_history 인자 스키마입니다."""

    service: str = Field(
        ...,
        description="배포 이력을 볼 서비스 이름. 사용자 질문에 나온 이름을 그대로 넣습니다. (예: payment-api)",
    )
#=== End of Modify Block


#=== Start of Insert Block
# [추가 이유] README 요구사항 1 — get_logs도 args_schema를 Pydantic으로 지정해야 합니다.
#            since 설명에 "배포 이력에서 얻은 시각을 그대로 넣으라"고 적어
#            앞 도구 결과가 뒤 도구 인자로 흐르는 연쇄를 모델에게 알려 줍니다.
class LogsArgs(BaseModel):
    """get_logs 인자 스키마입니다."""

    service: str = Field(..., description="로그를 볼 서비스 이름. (예: payment-api)")
    since: Optional[str] = Field(
        None,
        description=(
            "로그를 볼 기준 시각. get_deploy_history 결과의 배포 시각(ISO 8601)을 "
            "글자 그대로 넣습니다. (예: 2026-08-11T02:58:00+09:00) "
            "모르면 비워 두며, 이때는 평상시 로그만 보입니다."
        ),
    )


# [추가 이유] README 요구사항 1 — get_metrics도 args_schema가 필요합니다.
class MetricsArgs(BaseModel):
    """get_metrics 인자 스키마입니다."""

    service: str = Field(..., description="지표를 볼 서비스 이름. (예: payment-api)")
#=== End of Insert Block


@tool(args_schema=DeployArgs)
def get_deploy_history(service: str) -> str:
    #=== Start of Modify Block
    # [수정 이유] 모델이 도구를 고를 때 읽는 것은 이 docstring뿐입니다. 30자 이상이어야 하고,
    #            "언제 쓰는지 / 언제 쓰지 않는지"를 적어야 오호출이 줄어듭니다.
    # 원문: """TODO: 이 도구가 무엇을 하고 언제 써야 하는지 30자 이상으로 적으세요.
    # 원문:
    # 원문: 모델이 보는 것은 이 설명문뿐입니다. '언제 쓰지 말아야 하는지'도 적으면 좋습니다.
    # 원문: """
    """서비스의 최근 배포 이력(버전, 배포 시각, 배포 팀)을 최신순으로 조회합니다.

    장애 원인 조사를 시작할 때 가장 먼저 씁니다. 여기서 얻은 배포 시각을
    get_logs의 since 인자로 넘기면 배포 직후 로그를 볼 수 있습니다.
    오류율·지연 같은 수치를 볼 때는 쓰지 말고 get_metrics를 쓰세요.
    """
    #=== End of Modify Block
    #=== Start of Modify Block
    # [수정 이유] NotImplementedError 상태로는 도구가 동작하지 않습니다. 고정 데이터에서
    #            조회해 모델과 사람이 모두 읽을 수 있는 문장으로 돌려줍니다.
    #            같은 인자에는 항상 같은 결과가 나오도록 데이터 순서를 그대로 씁니다.
    # 원문: # TODO: DATA["deploys"]에서 조회해 사람이 읽을 수 있는 문자열로 반환하세요.
    # 원문: raise NotImplementedError("get_deploy_history 를 구현하세요.")
    name, error = _check_service(service, DATA["deploys"])
    if error:
        return f"[배포 이력] {error}"

    deploys = DATA["deploys"][name]
    lines = [f"[배포 이력] {name} — 최근 배포 {len(deploys)}건 (최신순)"]
    for d in deploys:
        lines.append(f"- {d['version']} | 배포 시각 {d['at']} | 배포 팀 {d['by']}")
    lines.append(f"가장 최근 배포 시각: {deploys[0]['at']} (get_logs의 since에 그대로 넣으세요)")
    return "\n".join(lines)
    #=== End of Modify Block


#=== Start of Modify Block
# [수정 이유] README 요구사항 1·3 — 로그 도구가 필요하고, since(배포 시각)를 실제
#            조회 키로 써야 배포 직후 로그(NullPointerException)에 닿습니다.
# 원문: # TODO: get_logs 를 만드세요.
# 원문: #   - 인자: service, since (배포 시각). since가 있으면 그 시점 로그를 봅니다.
# 원문: #   - 이 도구는 get_deploy_history 결과가 있어야 제대로 쓸 수 있습니다.
@tool(args_schema=LogsArgs)
def get_logs(service: str, since: Optional[str] = None) -> str:
    """서비스 로그(ERROR/WARN/INFO)를 조회합니다. since에 시각을 주면 그 시점 로그를 봅니다.

    배포 직후 무슨 오류가 났는지 볼 때 씁니다. 먼저 get_deploy_history로 배포 시각을
    알아낸 뒤 그 값을 since에 그대로 넣으세요. since 없이 부르면 평상시 로그만 나옵니다.
    수치(오류율, 지연, CPU)를 볼 때는 쓰지 마세요.
    """
    services = {key.split("@", 1)[0] for key in DATA["logs"]}
    name, error = _check_service(service, dict.fromkeys(services))
    if error:
        return f"[로그] {error}"

    when = (since or "").strip()
    if when:
        key = f"{name}@{when}"
        if key in DATA["logs"]:
            return f"[로그] {name} @ {when}\n{DATA['logs'][key]}"
        # 시각이 맞지 않으면 평상시 로그로 대신하되, 그 사실을 분명히 알려 줍니다.
        fallback = DATA["logs"].get(f"{name}@default", "(평상시 로그도 없습니다)")
        return (
            f"[로그] {name} @ {when} 구간의 로그가 없습니다. "
            "get_deploy_history의 배포 시각을 글자 그대로 넣었는지 확인하세요.\n"
            f"참고로 평상시 로그는 다음과 같습니다.\n{fallback}"
        )

    log = DATA["logs"].get(f"{name}@default", "(평상시 로그가 없습니다)")
    return f"[로그] {name} (평상시, 기준 시각 없음)\n{log}"
#=== End of Modify Block


#=== Start of Modify Block
# [수정 이유] README 요구사항 1 — 지표 도구가 필요합니다. 비율은 %로, 지연은 ms로 풀어
#            모델이 숫자의 의미를 오해하지 않게 합니다.
# 원문: # TODO: get_metrics 를 만드세요.
# 원문: #   - 인자: service
# 원문: #   - DATA["metrics"]에서 조회합니다.
@tool(args_schema=MetricsArgs)
def get_metrics(service: str) -> str:
    """서비스의 현재 지표(5분 오류율, p99 지연, CPU 사용률)를 조회합니다.

    장애의 규모와 영향을 수치로 확인할 때 씁니다. 원인(어떤 오류가 났는지)은
    알려 주지 않으므로 원인을 찾을 때는 get_deploy_history와 get_logs를 쓰세요.
    """
    name, error = _check_service(service, DATA["metrics"])
    if error:
        return f"[지표] {error}"

    m = DATA["metrics"][name]
    return (
        f"[지표] {name}\n"
        f"- 5분 오류율: {m['error_rate_5m'] * 100:.1f}%\n"
        f"- p99 지연: {m['p99_latency_ms']} ms\n"
        f"- CPU 사용률: {m['cpu'] * 100:.0f}%"
    )
#=== End of Modify Block


#=== Start of Modify Block
# [수정 이유] 빈 리스트면 모델에 묶인 도구가 없어 Agent가 아무것도 조회할 수 없습니다.
# 원문: # TODO: 위에서 만든 도구들을 여기에 모으세요.
# 원문: TOOLS: list = []
TOOLS: list = [get_deploy_history, get_logs, get_metrics]
#=== End of Modify Block


#=== Start of Insert Block
# [추가 이유] 모델에게 조사 순서(배포 → 로그 → 지표)와 연쇄 규칙을 알려 주는 시스템 프롬프트입니다.
#            도구가 필요 없는 질문에는 도구를 부르지 않도록 함께 적습니다.
SYSTEM_PROMPT = """당신은 장애 원인을 조사하는 운영 엔지니어입니다.
조사 순서:
1. get_deploy_history로 최근 배포가 있었는지, 그 시각이 언제인지 확인합니다.
2. 배포 시각을 get_logs의 since 인자로 글자 그대로 넘겨 배포 직후 로그를 봅니다.
3. get_metrics로 영향 규모를 확인합니다.
직전 도구 결과를 보고 다음에 무엇을 볼지 매번 다시 정하세요.
같은 도구를 같은 인자로 다시 부르지 마세요.
장애 조사가 필요 없는 질문(인사, 일반 개념 설명 등)에는 도구 없이 바로 답하세요.
결론은 한국어로, 근거가 된 도구 결과를 함께 적으세요."""


# [추가 이유] 한 번의 응답에 도구 호출이 여러 개 묶여 오면 ToolNode가 한꺼번에 실행해
#            MAX_TOOL_CALLS를 넘을 수 있습니다. 남은 예산만큼만 남기고 잘라 냅니다.
#            Bedrock 응답은 content 안에도 tool_use 블록이 있으므로 같이 맞춰 줍니다.
def _limit_tool_calls(msg: AIMessage, remaining: int) -> AIMessage:
    """AIMessage의 도구 호출을 remaining개까지만 남깁니다."""
    if len(msg.tool_calls) <= remaining:
        return msg
    kept = msg.tool_calls[:remaining]
    kept_ids = {tc["id"] for tc in kept}
    content = msg.content
    if isinstance(content, list):
        content = [
            b
            for b in content
            if not (
                isinstance(b, dict)
                and b.get("type") in ("tool_use", "tool_call")
                and b.get("id") not in kept_ids
            )
        ]
    return msg.model_copy(update={"tool_calls": kept, "content": content})


# [추가 이유] 멈추라는 판정이 났을 때 모델이 또 도구를 부르려 해도 그 호출은 버리고
#            글(결론)만 남겨야 합니다. 실행되지 않은 tool_calls가 남으면 대화 기록이 깨집니다.
def _text_only(msg: AIMessage) -> AIMessage:
    """도구 호출을 모두 떼어 내고 글만 남긴 AIMessage를 만듭니다."""
    content = msg.content
    if isinstance(content, list):
        content = "".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return AIMessage(content=content or "조사를 마칩니다.")
#=== End of Insert Block


def build_agent(llm=None):
    """도구를 쓸 수 있는 Agent 그래프를 만들어 컴파일해 반환합니다.

    반드시 지킬 것:
      - agent 노드와 tools 노드 사이에 순환이 있어야 합니다.
      - 탈출 조건이 있어야 합니다. 없으면 무한 루프입니다.

    create_react_agent를 써도 되고 StateGraph로 직접 만들어도 됩니다.
    심화 파트를 구현했다면 should_stop 판정을 그래프에 연결하세요.
    """
    llm = llm or _default_llm()
    #=== Start of Modify Block
    # [수정 이유] README 요구사항 2와 심화 연결 — agent ↔ tools 순환을 만들고,
    #            agent 노드가 매번 should_stop을 먼저 확인해 예산 초과·중복 호출·근거 충분이면 멈추게 합니다.
    #            create_react_agent는 이 판정을 끼워 넣기 어려워 StateGraph로 직접 조립합니다.
    # 원문: # TODO: 구현하세요.
    # 원문: raise NotImplementedError("build_agent 를 구현하세요.")
    model = llm.bind_tools(TOOLS)

    def agent_node(state: MessagesState) -> dict:
        """모델에게 다음 행동을 묻습니다. 멈춰야 하면 도구 없이 결론만 받습니다."""
        messages = state["messages"]
        # 지금까지 실제로 실행된 도구 수 = ToolMessage 개수
        made = sum(1 for m in messages if m.type == "tool")
        stop, reason = should_stop(messages, made)

        if stop:
            # 탈출 조건: 더 조사하지 말고 지금까지의 근거로 결론을 내게 합니다.
            notice = (
                f"\n\n[조사 종료: {reason}] 더 이상 도구를 부르지 말고 "
                "지금까지의 도구 결과만으로 원인과 근거를 정리해 답하세요."
            )
            response = model.invoke([SystemMessage(SYSTEM_PROMPT + notice), *messages])
            return {"messages": [_text_only(response)]}

        response = model.invoke([SystemMessage(SYSTEM_PROMPT), *messages])
        if response.tool_calls:
            response = _limit_tool_calls(response, MAX_TOOL_CALLS - made)
        return {"messages": [response]}

    def route_after_agent(state: MessagesState) -> str:
        """도구 호출이 있으면 tools로, 없으면 종료합니다. (두 번째 탈출 조건)"""
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")  # 순환: 도구 결과를 보고 다시 판단
    return graph.compile()
    #=== End of Modify Block


# ══════════════════════════════════════════════════════════════════
# 심화 파트 (3점) — 못 해도 과제는 통과합니다
# ══════════════════════════════════════════════════════════════════

#=== Start of Modify Block
# [수정 이유] 0이면 첫 판정부터 "예산 초과"가 되어 도구를 하나도 못 부릅니다.
#            README는 3~8을 요구합니다. 세 도구 한 바퀴(3회)에 재확인 여유 2회를 더해 5로 정합니다.
# 원문: # TODO: 한 번의 조사에서 허용할 도구 호출 상한 (3 이상 8 이하)
# 원문: MAX_TOOL_CALLS = 0
MAX_TOOL_CALLS = 5
#=== End of Modify Block


def should_stop(messages: list, tool_calls_made: int) -> tuple[bool, str]:
    """더 조사할지 멈출지 결정합니다. LLM을 호출하지 않습니다.

    판정 규칙:
      - tool_calls_made >= MAX_TOOL_CALLS        -> (True, "예산 초과")
      - 같은 도구를 같은 인자로 2회 이상 호출함  -> (True, "중복 호출")
      - 세 도구를 모두 한 번 이상 호출함         -> (True, "근거 충분")
      - 그 외                                    -> (False, 아무 문자열)

    Args:
        messages: 지금까지의 메시지 목록. 도구 호출 기록이 들어 있습니다.
        tool_calls_made: 지금까지 실행한 도구 호출 횟수

    Returns:
        (중단할지 여부, 이유 문자열)
    """
    #=== Start of Modify Block
    # [수정 이유] 멈춤 판정을 LLM에 맡기면 확률이 되므로, README 규칙 순서대로
    #            코드로 못 박습니다. 비용 상한인 예산을 가장 먼저 봅니다.
    # 원문: # TODO: 구현하세요.
    # 원문: raise NotImplementedError("should_stop 을 구현하세요.")
    if tool_calls_made >= MAX_TOOL_CALLS:
        return True, "예산 초과"

    # AIMessage에 남은 tool_calls에서 (도구 이름, 인자) 쌍을 모읍니다.
    # 인자 dict는 키 순서가 달라도 같은 호출로 보도록 정렬된 JSON 문자열로 바꿉니다.
    seen: set[tuple[str, str]] = set()
    used: set[str] = set()
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            name = tc["name"] if isinstance(tc, dict) else tc.name
            args = tc.get("args", {}) if isinstance(tc, dict) else tc.args
            key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
            if key in seen:
                return True, "중복 호출"
            seen.add(key)
            used.add(name)

    if {"get_deploy_history", "get_logs", "get_metrics"} <= used:
        return True, "근거 충분"

    return False, "조사 계속"
    #=== End of Modify Block
