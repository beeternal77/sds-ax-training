"""Day 1 — 운영 알람 트리아지 체인.

알람 하나를 넣으면 구조화된 분류 결과와 담당팀 안내 초안을 동시에 만듭니다.

[중요] 이 파일의 규칙
  1. 함수 이름과 인자를 바꾸지 마세요. 채점기가 이 이름으로 찾습니다.
  2. 모델은 반드시 함수 **안에서** 만듭니다. 모듈 최상단에서 만들면
     채점기가 가짜 모델을 넣을 수 없어 채점이 실패합니다.
  3. `llm` 인자가 들어오면 그것을 쓰고, None이면 직접 만듭니다.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableParallel
from pydantic import BaseModel, Field

# 과정 전체에서 고정으로 쓰는 값입니다. 바꾸지 마세요.
MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = "us-east-1"

# 프롬프트에 넣을 알람 본문의 최대 길이입니다.
# 4000자짜리 알람이 들어와도 토큰 낭비 없이 앞부분만 보여 주기 위함입니다.
MAX_ALERT_CHARS = 2000


def _default_llm():
    """기본 모델을 만듭니다. 채점기는 이 함수를 부르지 않습니다.

    import를 함수 안에 둔 이유: 모듈을 불러오는 것만으로 AWS 자격증명을
    요구하지 않게 하기 위해서입니다.
    """
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(model=MODEL_ID, region_name=REGION, temperature=0)


def get_text(message: Any) -> str:
    """ChatBedrockConverse는 content를 블록 리스트로 주기도 하므로 텍스트만 모아 반환합니다."""
    content = message.content if hasattr(message, "content") else message
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content)


def _alert_to_text(alert: Any) -> str:
    """알람을 프롬프트에 넣을 문자열로 바꿉니다.

    - dict가 아니어도(문자열, None 등) 죽지 않게 처리합니다.
    - 중첩 dict·datetime 등 JSON 직렬화가 안 되는 값은 default=str로 문자열화합니다.
    - 한글·이모지가 \\uXXXX로 깨지지 않도록 ensure_ascii=False를 씁니다.
    - 너무 긴 본문은 잘라 내고 잘랐다는 표시를 남깁니다.
    """
    if isinstance(alert, dict):
        text = json.dumps(alert, ensure_ascii=False, default=str, indent=2)
    else:
        text = str(alert)
    if len(text) > MAX_ALERT_CHARS:
        text = text[:MAX_ALERT_CHARS] + "\n... (이하 생략, 원문이 너무 깁니다)"
    return text


# ══════════════════════════════════════════════════════════════════
# 기초 파트 (7점)
# ══════════════════════════════════════════════════════════════════


class TriageResult(BaseModel):
    """운영 알람 분류 결과입니다. 티켓 시스템에 그대로 적재합니다."""

    severity: Literal["P1", "P2", "P3", "P4"] = Field(
        ...,
        description=(
            "장애 등급. "
            "P1: 고객 대면 서비스 전면 장애 또는 결제·인증 등 핵심 기능 불가, 5xx 급증, 데이터 유실 위험 — 즉시 호출. "
            "P2: 핵심 서비스의 부분 장애·심각한 성능 저하(지연 급증, 일부 사용자 실패) — 30분 내 대응. "
            "P3: 사용자 영향이 작거나 우회 가능한 문제, 임계치 근접 경고 — 업무시간 내 대응. "
            "P4: 정보성 알람, 영향 없음 또는 판단 근거 부족 — 티켓만 기록."
        ),
    )
    service: str = Field(
        ...,
        description="알람이 발생한 서비스 이름. 알람에 없으면 'unknown'.",
    )
    system_type: Literal["AP", "DB", "NETWORK", "INFRA", "UNKNOWN"] = Field(
        ...,
        description=(
            "장애가 발생한 계층. AP: 애플리케이션 서버, DB: 데이터베이스, "
            "NETWORK: 네트워크/로드밸런서, INFRA: 서버·스토리지·클라우드 자원, "
            "판단이 어려우면 UNKNOWN."
        ),
    )
    category: Literal["availability", "latency", "error_rate", "capacity", "security", "other"] = Field(
        ...,
        description=(
            "증상 분류. availability: 서비스 다운/응답 없음, latency: 응답 지연, "
            "error_rate: 오류율(5xx 등) 증가, capacity: CPU·메모리·디스크 등 자원 부족, "
            "security: 보안 이벤트, other: 그 외."
        ),
    )
    owner_team: str = Field(
        ...,
        description="1차로 호출할 담당팀 이름 (예: 결제플랫폼팀, DB운영팀, 인프라운영팀). 모르면 '운영관제팀'.",
    )
    first_check: str = Field(
        ...,
        description="당직자가 가장 먼저 열어 볼 항목 한 가지 (예: 최근 배포 이력, DB 커넥션 풀, 대시보드 이름).",
    )
    summary: str = Field(
        ...,
        description="장애 현상 한 줄 요약 (한국어, 80자 이내).",
    )


TRIAGE_SCHEMA = TriageResult


def build_triage_chain(llm=None):
    """알람 dict를 받아 TRIAGE_SCHEMA 형태의 dict를 반환하는 체인을 만듭니다.

    반드시 지킬 것:
      - 프롬프트에 파서의 format_instructions를 실제로 주입해야 합니다.
        스키마만 정의하고 프롬프트에 넣지 않으면 모델은 형식을 모릅니다.
    """
    llm = llm or _default_llm()

    parser = JsonOutputParser(pydantic_object=TRIAGE_SCHEMA)
    prompt = PromptTemplate(
        template=(
            "당신은 24시간 운영 관제센터의 장애 트리아지 담당자입니다.\n"
            "아래 모니터링 알람을 읽고 장애 등급, 담당팀, 첫 확인 항목을 판단하세요.\n"
            "알람의 일부 필드가 비었거나 형식이 이상해도 있는 정보만으로 최선의 판단을 내리세요.\n\n"
            "[알람]\n{alert}\n\n"
            "[출력 형식]\n{format_instructions}\n"
            "JSON 객체 하나만 출력하고 다른 설명은 붙이지 마세요.\n"
        ),
        input_variables=["alert"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    return {"alert": RunnableLambda(_alert_to_text)} | prompt | llm | parser


NOTICE_SYSTEM_PROMPT = (
    "당신은 SDS 운영관제센터의 야간 당직 엔지니어입니다. "
    "모니터링 알람을 받아 담당팀 메신저 채널에 바로 붙여넣을 장애 안내 초안을 작성합니다.\n"
    "작성 규칙:\n"
    "1. 첫 줄은 '[장애 안내] <서비스명> <증상 요약>' 형식으로 씁니다.\n"
    "2. 이어서 '발생 시각 / 대상 서비스 / 리전 / 현상' 을 항목별로 한 줄씩 적습니다.\n"
    "3. 담당팀에 요청할 첫 조치를 1~2개 제시합니다.\n"
    "4. 정중한 '~습니다' 체 존댓말을 쓰되, 인사말 없이 5~8줄로 간결하게 씁니다.\n"
    "5. 알람에 없는 정보는 추측하지 말고 '확인 필요'라고 적습니다."
)


def build_notice_chain(llm=None):
    """알람 dict를 받아 담당팀 안내 초안 문자열을 반환하는 체인을 만듭니다.

    반드시 지킬 것:
      - system 메시지로 역할을 지정합니다 (30자 이상).
      - 기본 예시 문구를 그대로 두지 말고 본인 조직의 맥락으로 바꾸세요.
    """
    llm = llm or _default_llm()

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", NOTICE_SYSTEM_PROMPT),
            ("human", "다음 알람으로 담당팀 안내 초안을 작성해 주세요.\n\n{alert}"),
        ]
    )
    # StrOutputParser는 블록 리스트 content도 텍스트로 합쳐 줍니다.
    return {"alert": RunnableLambda(_alert_to_text)} | prompt | llm | StrOutputParser()


def _fallback_triage(alert: Any, error: Exception) -> dict:
    """파서가 실패했을 때 쓰는 복구용 기본값입니다.

    모르는 상황에서는 놓치는 것보다 과잉 대응이 안전하므로 가장 높은 P1로 둡니다.
    parse_failed 표시로 '모델이 아니라 복구 경로가 만든 값'임을 구분할 수 있게 합니다.
    """
    service = alert.get("service", "unknown") if isinstance(alert, dict) else "unknown"
    return {
        "severity": "P1",
        "service": str(service or "unknown"),
        "system_type": "UNKNOWN",
        "category": "other",
        "owner_team": "운영관제팀",
        "first_check": "모델 분류 실패 — 당직자가 알람 원문을 직접 확인",
        "summary": "자동 분류 실패로 수동 확인이 필요합니다.",
        "parse_failed": True,
        "parse_error": f"{type(error).__name__}: {str(error)[:200]}",
    }


def build_full_chain(llm=None):
    """두 체인을 병렬로 묶어 {"triage": dict, "notice": str} 를 반환합니다.

    심화 파트를 구현했다면, triage 결과는 apply_severity_rules를 거친 값이어야 합니다.
    """
    llm = llm or _default_llm()

    triage_chain = build_triage_chain(llm)
    notice_chain = build_notice_chain(llm)

    def triage_with_rules(alert: Any) -> dict:
        """분류 → (실패 시 복구) → 결정적 규칙 적용 순서로 처리합니다."""
        try:
            triage = triage_chain.invoke(alert)
            if not isinstance(triage, dict):
                raise ValueError(f"dict가 아닌 분류 결과: {type(triage).__name__}")
            triage = {**triage, "parse_failed": False}
        except Exception as exc:  # noqa: BLE001 — 어떤 실패든 파이프라인을 세우지 않습니다.
            triage = _fallback_triage(alert, exc)
        return apply_severity_rules(triage, alert if isinstance(alert, dict) else {})

    def safe_notice(alert: Any) -> str:
        """안내 초안이 실패해도 triage는 살아 있도록 기본 문구로 대체합니다."""
        try:
            return notice_chain.invoke(alert)
        except Exception as exc:  # noqa: BLE001
            return f"[장애 안내] 자동 초안 생성 실패 ({type(exc).__name__}). 알람 원문을 확인해 주세요."

    return RunnableParallel(
        triage=RunnableLambda(triage_with_rules),
        notice=RunnableLambda(safe_notice),
    )


# ══════════════════════════════════════════════════════════════════
# 심화 파트 (3점) — 못 해도 과제는 통과합니다
# ══════════════════════════════════════════════════════════════════

# 장애 시 최우선으로 봐야 하는 서비스 목록입니다 (교육용 더미 데이터입니다).
# 이 목록이 곧 "새벽에도 사람을 깨우는" 우선순위 정책입니다.
CRITICAL_SERVICES: set[str] = {
    "payment-api",
    "auth-api",
    "order-api",
    "core-db",
}

# 메시지에 포함되면 최소 P1로 올리는 키워드입니다 (대소문자 무시).
P1_KEYWORDS = ("5xx", "outage")

# severity 등급의 높낮이 비교용입니다. 숫자가 작을수록 급합니다.
SEVERITY_ORDER = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


def apply_severity_rules(triage: dict, alert: dict) -> dict:
    """모델이 매긴 severity 위에 결정적 규칙을 얹습니다.

    이 함수는 LLM을 호출하지 않습니다. 같은 입력에 항상 같은 출력을 내야 합니다.

    규칙:
      - alert["service"]가 CRITICAL_SERVICES에 있으면 최소 P2
      - alert["message"]에 "5xx" 또는 "outage"가 있으면 최소 P1
      - 둘 다면 더 높은 쪽(숫자가 작은 쪽)을 적용
      - 아무것도 해당 없으면 모델 판단을 그대로 둠
      - 규칙이 적용됐으면 그 사실을 결과에 남길 것 (rule_applied 키)

    Returns:
        규칙이 반영된 새 dict. 원본은 바꾸지 않습니다.
    """
    result = dict(triage or {})
    alert = alert if isinstance(alert, dict) else {}

    original = result.get("severity")
    # 모델이 등급을 빠뜨리거나 엉뚱한 값을 주면 비교가 불가능하므로 가장 낮은 P4로 보고 규칙만 적용합니다.
    current = original if original in SEVERITY_ORDER else "P4"

    service = str(alert.get("service") or "").strip().lower()
    message = str(alert.get("message") or "").lower()

    # (최소 등급, 규칙 이름) 후보를 모읍니다.
    candidates: list[tuple[str, str]] = []
    if service in CRITICAL_SERVICES:
        candidates.append(("P2", "critical_service"))
    if any(k in message for k in P1_KEYWORDS):
        candidates.append(("P1", "p1_keyword"))

    rules_hit: list[str] = []
    final = current
    for floor, name in candidates:
        # 규칙이 요구하는 최소 등급보다 현재가 낮을 때(숫자가 클 때)만 올립니다.
        if SEVERITY_ORDER[floor] < SEVERITY_ORDER[final]:
            final = floor
            rules_hit.append(name)

    result["severity"] = final
    result["model_severity"] = original
    result["rule_applied"] = bool(rules_hit) or final != original
    result["rules_hit"] = rules_hit
    return result
