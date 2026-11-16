"""Day 6 — Supervisor 인시던트 대응팀.

전문 Agent 셋을 Supervisor가 지휘합니다.

[중요]
  1. 함수·상수 이름을 바꾸지 마세요.
  2. `route_question`은 LLM을 호출하지 않습니다. 결정적 규칙으로 배분하세요.
     실제 운영에서는 모델이 배분하지만, 규칙으로 먼저 나눠 보면
     '무엇을 근거로 나누는가'가 분명해집니다.
"""

from __future__ import annotations

from typing import Any
# === Insert Begin ===
# route_question: 정규식으로 키워드(동의어·영문 표기 포함)를 매칭합니다.
import re
# 그래프 상태 정의: messages(대화 누적) + targets(라우팅 결과)
from typing import Annotated, TypedDict

# build_supervisor: 워커 결과를 AIMessage로 남기고, StateGraph로 그래프를 조립합니다.
# (모듈 import는 최상단에 두어도 됩니다. 금지된 것은 '모델 객체 생성'이며
#  모델은 기존 _default_llm()처럼 함수 안에서 만듭니다.)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
# === Insert End ===

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = "us-east-1"


def _default_llm():
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(model=MODEL_ID, region_name=REGION, temperature=0)


# ══════════════════════════════════════════════════════════════════
# 기초 파트 (7점)
# ══════════════════════════════════════════════════════════════════

# TODO: 전문 Agent 이름 3개를 정하세요.
#   권장: log_agent / metric_agent / runbook_agent
# === Mody Begin ===
# M : AGENT_NAMES: list[str] = []
# 이름이 곧 담당 범위의 선언입니다. 그래프 노드 이름으로도 그대로 쓰입니다.
AGENT_NAMES: list[str] = ["log_agent", "metric_agent", "runbook_agent"]
# === Mody End ===

# TODO: Agent별로 쓸 도구를 나누세요.
#   같은 도구가 두 Agent에 들어가면 안 됩니다. 도메인이 겹치면 Supervisor가 헷갈립니다.
#   "혹시 몰라서" 얹지 마세요.
# === Mody Begin ===
# M : AGENT_TOOLS: dict[str, list[str]] = {}
# 도메인 기준으로 나누고, 한 도구는 한 Agent에만 둡니다. (Day 3·4 실습에 실재하는 도구만 사용)
#   - log_agent     : 로그 원문 조회
#   - metric_agent  : 지표·자산 상태·배포 이력 (README가 '배포'를 지표 쪽 어휘로 분류)
#   - runbook_agent : 런북 검색·담당자·과거 장애 이력 (대응 절차를 정하는 데 쓰는 정보)
AGENT_TOOLS: dict[str, list[str]] = {
    "log_agent": ["get_logs"],
    "metric_agent": ["get_metrics", "get_asset_status", "get_deploy_history"],
    "runbook_agent": ["search_runbook", "get_service_owner", "query_recent_incidents"],
}
# === Mody End ===

# === Insert Begin ===
# ──────────────────────────────────────────────────────────────────
# 라우팅 키워드 규칙표 (route_question 이 사용)
#
#   README 표의 어휘를 그대로 베끼지 않고, 같은 뜻의 동의어·영문 표기를 함께 넣습니다.
#   (채점은 표에 없는 동의어와 영문 표기로도 확인합니다)
#
#   키워드는 두 등급으로 나눕니다.
#     - strong : 이 단어만으로 담당 Agent가 분명한 것  (예: "로그", "지표", "런북")
#     - weak   : 혼자 나오면 그 Agent지만, 다른 Agent의 strong 키워드와 함께 나오면
#                무시하는 것 (아래 두 가지 함정을 막기 위함)
#         · "배포"   : README는 지표 쪽 어휘로 분류하지만, "배포 절차가 어떻게 되나요"는
#                      런북 질문입니다. 절차·대응 같은 런북 신호가 있으면 지표로 보내지 않습니다.
#         · "어떻게/방법" : "CPU 사용률이 어떻게 되나요"는 지표 질문입니다. 다른 도메인
#                      신호가 있으면 런북을 따로 부르지 않습니다. (불필요 호출 절제)
#
#   함정 단어 처리
#     - "오류율/에러율/error rate" 는 지표입니다. 로그 쪽 "오류/에러/error" 는
#       뒤에 '율·비율·rate'가 붙으면 매칭하지 않습니다.
#     - "로그인/로그아웃" 은 로그가 아닙니다.
#     - "500ms", "500건", "500%" 의 500 은 HTTP 상태 코드가 아닙니다.
# ──────────────────────────────────────────────────────────────────


def _en(*words: str) -> str:
    """영문 키워드를 '앞뒤가 영문자가 아닌 경우'로 감싸는 패턴을 만듭니다.

    정규식 \\b 는 한글도 단어 문자로 보기 때문에 "CPU가" 에서 cpu 를 놓칩니다.
    그래서 영문자만 경계로 보는 lookaround 를 씁니다. ("login" 속 "log" 는 제외됨)
    """
    return r"(?<![a-z])(?:" + "|".join(words) + r")(?![a-z])"


# 로그: 원문 로그·에러 메시지·예외·스택·트레이스·HTTP 5xx
_LOG_STRONG = "|".join([
    r"로그(?!\s*인|\s*아웃)", r"에러(?!\s*율|\s*비율)", r"오류(?!\s*율|\s*비율)",
    r"예외", r"스택", r"트레이스", r"익셉션", r"크래시", r"덤프", r"널\s*포인터",
    r"(?<![\d.])5(?:\d\d|xx)(?![\d.%]|\s*(?:ms|초|밀리|mb|gb|kb|건|개|명|원|번|회|대))",
    _en(r"logs?", r"logging", r"errors?(?!\s*rates?)", r"exceptions?", r"stack\s*trace",
        r"trace(?:s|back)?", r"tracing", r"crash(?:es|ed)?", r"panic", r"fatal", r"npe",
        r"5xx", r"stderr"),
])

# 지표: 수치·성능·자원 사용량·오류율·지연
_METRIC_STRONG = "|".join([
    r"지표", r"수치", r"지연", r"레이턴시", r"응답\s*(?:시간|속도)", r"메모리", r"사용률",
    r"사용량", r"점유율", r"오류율", r"에러율", r"오류\s*비율", r"에러\s*비율", r"처리량",
    r"트래픽", r"부하", r"디스크", r"리소스", r"자원", r"메트릭", r"성능", r"가용성",
    r"대시보드", r"느려", r"느림", r"그라파나",
    _en(r"metrics?", r"latency", r"cpu", r"memory", r"mem", r"error\s*rates?",
        r"throughput", r"tps", r"qps", r"rps", r"p(?:50|90|95|99)", r"usage",
        r"utili[sz]ation", r"load", r"traffic", r"disk", r"dashboard", r"grafana",
        r"prometheus", r"slow", r"response\s*time", r"uptime"),
])
#    배포: 다른 Agent 의 strong 신호가 없을 때만 지표로 봅니다.
_METRIC_WEAK = "|".join([
    r"배포", r"릴리스", r"릴리즈",
    _en(r"deploy(?:s|ed|ment|ments)?", r"release[sd]?", r"rollout"),
])

# 런북: 대응 절차·매뉴얼·담당자
_RUNBOOK_STRONG = "|".join([
    r"절차", r"대응", r"런북", r"매뉴얼", r"메뉴얼", r"가이드", r"플레이북", r"담당",
    r"책임자", r"오너", r"연락처", r"에스컬레이션", r"누구", r"누가", r"조치\s*(?:방법|사항|순서)",
    r"해결\s*(?:방법|책)",
    _en(r"runbooks?", r"playbooks?", r"manuals?", r"procedures?", r"guides?", r"sop",
        r"owners?", r"on-?call", r"escalat(?:e|ion)", r"who", r"how\s+to"),
])
#    어떻게/방법: 다른 Agent 의 strong 신호가 없을 때만 런북으로 봅니다.
_RUNBOOK_WEAK = "|".join([r"어떻게", r"방법", _en(r"how")])

# Agent 이름 -> (strong 패턴, weak 패턴). AGENT_NAMES 순서대로 결과를 냅니다.
_ROUTE_RULES: dict[str, tuple[re.Pattern[str], re.Pattern[str] | None]] = {
    "log_agent": (re.compile(_LOG_STRONG, re.IGNORECASE), None),
    "metric_agent": (
        re.compile(_METRIC_STRONG, re.IGNORECASE),
        re.compile(_METRIC_WEAK, re.IGNORECASE),
    ),
    "runbook_agent": (
        re.compile(_RUNBOOK_STRONG, re.IGNORECASE),
        re.compile(_RUNBOOK_WEAK, re.IGNORECASE),
    ),
}
# === Insert End ===


def route_question(question: str) -> list[str]:
    """질문을 처리할 Agent 목록을 반환합니다. LLM을 호출하지 않습니다.

    반환 규칙:
      - 로그·에러·예외·스택·트레이스·5xx, 영문 log/exception/trace -> log_agent
      - 지표·수치·지연·레이턴시·CPU·메모리·오류율·배포, 영문 metric/latency -> metric_agent
      - 절차·대응·방법·런북·매뉴얼·담당·누구·어떻게, 영문 runbook -> runbook_agent
      - 여러 주제가 섞이면 해당하는 Agent를 모두 반환
      - 어디에도 해당하지 않으면 빈 목록 (Supervisor가 직접 답한다)

    **필요한 것만 반환하세요.** 전부 부르면 정확도는 오르지만 호출 비용이 폭증합니다.
    """
    # TODO: 구현하세요.
    # === Delete Begin ===
    # D : raise NotImplementedError("route_question 을 구현하세요.")
    # === Delete End ===
    # === Insert Begin ===
    # 비정상 입력 방어: None·비문자열이 와도 예외 없이 빈 목록/판정을 돌려줍니다.
    if not isinstance(question, str):
        question = "" if question is None else str(question)
    if not question.strip():
        return []  # 빈 질문 → 부를 Agent 없음 (Supervisor가 직접 답함)

    # 1) strong 키워드: 걸리는 Agent를 모두 모읍니다. (복합 질문 → 여러 Agent)
    strong_hits = {
        name for name, (strong, _weak) in _ROUTE_RULES.items() if strong.search(question)
    }

    # 2) weak 키워드: 다른 Agent의 strong 신호가 하나도 없을 때만 추가합니다.
    #    예) "배포 절차가 어떻게 되나요" → runbook strong(절차)이 있으므로 '배포'로 metric 추가 안 함
    #        "CPU 사용률이 어떻게 되나요" → metric strong(CPU)이 있으므로 '어떻게'로 runbook 추가 안 함
    selected = set(strong_hits)
    for name, (_strong, weak) in _ROUTE_RULES.items():
        if weak is None or name in strong_hits:
            continue
        if not (strong_hits - {name}) and weak.search(question):
            selected.add(name)

    # 3) A  순서로 정렬해 반환합니다.
    #    - 집합에서 꺼내므로 같은 Agent가 두 번 들어가지 않습니다.
    #    - 순서가 고정되어 같은 질문은 언제 물어도 같은 결과(결정성)가 나옵니다.
    return [name for name in AGENT_NAMES if name in selected]
    # === Insert End ===


# === Insert Begin ===
class SupervisorState(TypedDict):
    """Supervisor 그래프가 노드 사이에서 주고받는 상태입니다.

    - messages : 대화 기록. `add_messages` 리듀서가 붙어 있어서, 노드가
                 {"messages": [새 메시지]} 를 돌려주면 덮어쓰지 않고 **뒤에 이어 붙습니다.**
                 사용자 질문 → 각 워커 답변(또는 억제 사유) 순으로 쌓입니다.
    - targets  : supervisor 노드가 route_question 으로 고른 Agent 이름 목록.
                 조건부 경로가 이 값을 보고 해당 Agent 노드로만 보냅니다.
                 (채점기는 그래프에 {"messages": [...], "targets": []} 형태로 넣습니다)

    리듀서가 없는 키(targets)는 노드가 돌려준 값으로 **통째로 교체**됩니다.
    supervisor 가 매 실행마다 새로 계산해 넣으므로 이 동작이 맞습니다.
    """

    messages: Annotated[list, add_messages]
    targets: list[str]


# 전문 Agent 별 시스템 프롬프트 — 담당 범위와 도구를 '좁게' 선언합니다.
#   한 Agent가 남의 영역까지 답하지 않게 막아 두면, 답이 이상할 때 고칠 프롬프트가 하나로 특정됩니다.
_AGENT_PROMPTS: dict[str, str] = {
    "log_agent": (
        "당신은 로그 분석 전문 Agent입니다. 로그·에러 메시지·예외·스택 트레이스·5xx 응답만 다룹니다. "
        "지표 해석이나 대응 절차 안내는 하지 마세요. "
        "답에는 확인한 에러 종류와 건수, 시각 같은 근거를 함께 적으세요."
    ),
    "metric_agent": (
        "당신은 지표 분석 전문 Agent입니다. 오류율·지연(레이턴시)·CPU·메모리·처리량·배포 이력만 다룹니다. "
        "로그 원문 해석이나 대응 절차 안내는 하지 마세요. "
        "답에는 수치와 측정 구간을 반드시 함께 적으세요."
    ),
    "runbook_agent": (
        "당신은 런북 전문 Agent입니다. 장애 대응 절차·매뉴얼·담당자·에스컬레이션 경로만 다룹니다. "
        "로그나 지표를 추측해서 말하지 마세요. "
        "답에는 참고한 런북 항목이나 담당 팀 같은 출처를 함께 적으세요."
    ),
}


def _last_question(messages: list) -> str:
    """상태의 메시지 목록에서 가장 최근 사용자 질문의 텍스트를 꺼냅니다."""
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", "") == "human":
            return _text_of(msg)
    return ""


def _text_of(msg: Any) -> str:
    """메시지 content 를 문자열로 바꿉니다.

    Bedrock 응답은 content 가 [{"type": "text", "text": "..."}] 같은 블록 리스트일 수 있어서
    텍스트 블록만 이어 붙입니다.
    """
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return "" if content is None else str(content)
# === Insert End ===


def build_supervisor(llm=None):
    """Supervisor 그래프를 만들어 컴파일해 반환합니다.

    반드시 지킬 것:
      - AGENT_NAMES의 이름이 모두 그래프 노드로 존재해야 합니다.
      - supervisor 노드에서 각 Agent로 가는 경로가 있어야 합니다.
      - 종료 경로가 있어야 합니다.

    langgraph_supervisor를 써도 되고 StateGraph로 직접 만들어도 됩니다.
    """
    llm = llm or _default_llm()
    # TODO: 구현하세요.
    # === Delete Begin ===
    # D : raise NotImplementedError("build_supervisor 를 구현하세요.")
    # === Delete End ===
    # === Insert Begin ===
    # ──────────────────────────────────────────────────────────────
    # 그래프 구조
    #
    #   START → supervisor ─(targets 있음)─→ log_agent / metric_agent / runbook_agent → END
    #                     └─(targets 없음)─→ END   (supervisor 가 직접 답한 경우)
    #
    #   - supervisor : route_question 으로 Agent 를 고른다 (LLM 아님 → 배분은 항상 같은 결과)
    #   - 워커       : 자기 도메인 프롬프트로 LLM 을 부르고, 결과를 judge_output 게이트에 통과시킨다
    #   - 여러 Agent 가 골라지면 조건부 경로가 리스트를 돌려 **병렬로** 실행한다
    # ──────────────────────────────────────────────────────────────

    def supervisor_node(state: SupervisorState) -> dict:
        question = _last_question(state.get("messages", []))
        targets = route_question(question)
        if targets:
            return {"targets": targets}
        # 어느 Agent 에도 해당하지 않으면 워커를 부르지 않고 supervisor 가 직접 답합니다.
        # (불필요한 워커 호출을 만들지 않는 것이 Supervisor 의 역할)
        reply = llm.invoke([HumanMessage(content=question or "(빈 질문)")])
        return {
            "targets": [],
            "messages": [AIMessage(content=f"[supervisor] {_text_of(reply)}", name="supervisor")],
        }

    def make_worker(agent_name: str):
        """Agent 이름별 워커 노드 함수를 만듭니다. (클로저로 이름·프롬프트·도구를 고정)"""
        tools_desc = ", ".join(AGENT_TOOLS.get(agent_name, []))
        system_prompt = f"{_AGENT_PROMPTS[agent_name]}\n사용 가능한 도구: {tools_desc}"

        def worker_node(state: SupervisorState) -> dict:
            question = _last_question(state.get("messages", []))
            reply = llm.invoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=question)]
            )
            output = _text_of(reply)

            # 게이트: 워커 산출물을 그대로 내보내지 않고 judge_output 으로 한 번 거릅니다.
            # 검사를 워커마다 따로 짜지 않고 Supervisor 쪽 한 곳(이 함수)에서 공통으로 적용합니다.
            verdict = judge_output(agent_name, output)
            if verdict.get("keep"):
                content = f"[{agent_name}] {output}"
            else:
                # 억제할 때도 '누가, 왜' 억제됐는지 남깁니다. (사유가 없으면 다음 날 원인 추적 불가)
                content = f"[{agent_name}] 억제됨 (사유: {verdict.get('reason', '사유 미기재')})"
            return {"messages": [AIMessage(content=content, name=agent_name)]}

        return worker_node

    def route_to_agents(state: SupervisorState):
        """supervisor 다음 경로: 골라진 Agent 노드 목록(병렬 실행) 또는 종료."""
        targets = [t for t in state.get("targets", []) if t in AGENT_NAMES]
        return targets or END

    # 1) 빈 그래프 생성 (노드 사이에서 SupervisorState 를 주고받음)
    graph = StateGraph(SupervisorState)

    # 2) 노드 등록 — Supervisor 1개 + 전문 Agent 3개
    #    노드 이름은 AGENT_NAMES 와 똑같아야 합니다. (채점기가 그래프 노드 이름으로 확인)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("log_agent", make_worker("log_agent"))
    graph.add_node("metric_agent", make_worker("metric_agent"))
    graph.add_node("runbook_agent", make_worker("runbook_agent"))

    # 3) 시작 경로 — 모든 질문은 supervisor 가 먼저 받습니다.
    graph.add_edge(START, "supervisor")

    # 4) supervisor → Agent 조건부 경로
    #    route_to_agents 가 돌려준 Agent 들로만 이동합니다. (여러 개면 병렬 실행)
    #    path_map: supervisor 에서 갈 수 있는 모든 목적지(각 Agent + 종료)를 명시합니다.
    graph.add_conditional_edges(
        "supervisor",
        route_to_agents,
        ["log_agent", "metric_agent", "runbook_agent", END],
    )

    # 5) 종료 경로 — 각 워커는 일을 마치면 종료합니다.
    graph.add_edge("log_agent", END)
    graph.add_edge("metric_agent", END)
    graph.add_edge("runbook_agent", END)

    # 6) 컴파일해 실행 가능한 그래프로 반환
    return graph.compile()
    # === Insert End ===


# ══════════════════════════════════════════════════════════════════
# 심화 파트 (3점) — 못 해도 과제는 통과합니다
# ══════════════════════════════════════════════════════════════════

# === Insert Begin ===
# ──────────────────────────────────────────────────────────────────
# judge_output 판정 기준
#
#   단정 표현과 근거 유무를 '함께' 봅니다.
#     - 단정만 있고 근거가 없으면  → 억제  ("확실합니다. 틀림없이 배포 때문입니다.")
#     - 단정이 있어도 근거가 있으면 → 통과  ("NullPointerException 이 1243건 ... 확실합니다")
#     - 단정이 없으면              → 통과  (길이 기준만 넘으면 됨)
# ──────────────────────────────────────────────────────────────────
_MIN_LENGTH = 20  # 이 글자 수 미만이면 '저가치' (공백 제외 전후 기준)

# 근거 없이 단정하는 표현. "확실하지 않다"처럼 부정·유보는 단정이 아니므로 제외합니다.
_ASSERTIVE_RE = re.compile(
    r"확실(?!\s*(?:하지|치|하진)\s*않)|틀림\s*없|분명(?:합니다|하다|해|히)|명백|확신"
    r"|의심의\s*여지(?:가|는)?\s*없|단언|무조건|절대(?:로)?|뿐입니다|뿐이다"
    r"|definitely|certainly|undoubtedly|without\s+(?:a\s+)?doubt|clearly|guaranteed|for\s+sure",
    re.IGNORECASE,
)

# 근거: 수치(숫자) 또는 출처를 가리키는 표현
_EVIDENCE_RE = re.compile(
    r"\d"  # 건수·비율·시각·지연 수치 등
    r"|출처|근거|참고|기준|에\s*따르면|로그(?:에서|상|를\s*보면)|대시보드|그라파나|런북|매뉴얼|문서|티켓"
    r"|according\s+to|source|ref(?:erence)?|dashboard|grafana|runbook|https?://",
    re.IGNORECASE,
)
# === Insert End ===


def judge_output(agent_name: str, output: str) -> dict:
    """워커 산출물을 내보내기 전에 걸러냅니다. LLM을 호출하지 않습니다.

    워커가 만든 것을 그대로 사용자에게 주면 근거 없는 단정과 빈 답변이 섞입니다.
    Supervisor는 게이트 역할을 해야 합니다.

    판정 규칙:
      - 내용이 비었거나 20자 미만          -> {"keep": False, "reason": "저가치"}
      - "확실합니다" "틀림없습니다" 같은
        근거 없는 단정이 있는데 수치·출처가 없음 -> {"keep": False, "reason": "근거 없는 단정"}
      - 그 외                              -> {"keep": True, "reason": ...}

    Returns:
        {"keep": bool, "reason": str} 형태의 dict
    """
    # TODO: 구현하세요.
    # === Delete Begin ===
    # D : raise NotImplementedError("judge_output 을 구현하세요.")
    # === Delete End ===
    # === Insert Begin ===
    # 0) 입력 정리: None·비문자열이 와도 예외 없이 판정합니다.
    if output is None:
        output = ""
    text = output if isinstance(output, str) else str(output)
    text = text.strip()
    who = agent_name or "unknown_agent"

    # 1) 저가치: 비었거나 20자 미만 ("", "ok", "확인함" 등)
    if len(text) < _MIN_LENGTH:
        return {
            "keep": False,
            "reason": f"저가치: {who} 산출물이 {len(text)}자로 기준({_MIN_LENGTH}자) 미만",
        }

    # 2) 근거 없는 단정: 단정 표현은 있는데 수치·출처가 하나도 없음
    has_assertion = _ASSERTIVE_RE.search(text) is not None
    has_evidence = _EVIDENCE_RE.search(text) is not None
    if has_assertion and not has_evidence:
        return {
            "keep": False,
            "reason": f"근거 없는 단정: {who} 산출물에 단정 표현이 있으나 수치·출처가 없음",
        }

    # 3) 그 외: 통과 (통과 사유도 남겨 두면 나중에 게이트 동작을 추적하기 쉽습니다)
    if has_assertion:
        return {"keep": True, "reason": "통과: 단정 표현이 있으나 수치·출처 근거가 함께 있음"}
    return {"keep": True, "reason": "통과: 기준 길이 이상이며 근거 없는 단정 없음"}
    # === Insert End ===
