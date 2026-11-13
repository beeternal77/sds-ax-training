"""Day 5 — 승인 게이트와 가드레일.

[중요]
  1. 함수·상수 이름을 바꾸지 마세요.
  2. 이 파일의 함수는 LLM을 호출하지 않아도 동작해야 합니다.
     규칙 기반으로 먼저 막고, 필요하면 모델 판별을 덧붙이세요.
  3. 채점은 교안에 공개된 20문항이 아니라 **비공개 문항**으로 합니다.
     공개 문항만 통과하는 하드코딩은 채점에서 걸립니다.
"""

from __future__ import annotations

import json
import re
# === Insert Begin ===
import unicodedata
# === Insert End ===
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_public_sets() -> tuple[list[str], list[str]]:
    """연습용 공개 세트를 읽습니다. 채점에는 쓰이지 않습니다."""
    attack = json.loads((DATA_DIR / "attack_set.json").read_text(encoding="utf-8"))
    normal = json.loads((DATA_DIR / "normal_set.json").read_text(encoding="utf-8"))
    return attack, normal


# ══════════════════════════════════════════════════════════════════
# 기초 파트 (7점)
# ══════════════════════════════════════════════════════════════════

# === Insert Begin ===
# ──────────────────────────────────────────────────────────────────
# 입력 가드 규칙 설계
#
#   핵심 원칙: "단어 하나"가 아니라 "의도의 조합"으로 막는다.
#     - "무시"      단독 → 통과   (예: "무시해도 되는 알람이 뭔가요?")
#     - "이전 지시" + "무시/잊/됐고" → 차단 (지시를 덮어쓰려는 동작 + 현재 지시라는 대상)
#
#   규칙 묶음(카테고리)마다 [대상 표현] 과 [동작 표현] 을 따로 정의하고,
#   둘이 가까이(짧은 거리 안에) 함께 나올 때만 차단합니다.
#   정규식의 거리 제한(.{0,N})은 모두 상한이 있어서 아주 긴 입력에서도 느려지지 않습니다.
# ──────────────────────────────────────────────────────────────────

# 1) 지시 덮어쓰기 ─ "현재 지시"를 가리키는 대상
_PRIOR = r"(?:이전|지난|앞선|앞의|앞에서|위의|위에|기존|원래|여태|지금까지|모든)"
_INSTR = r"(?:지시|지침|명령|대화|규칙|룰|프롬프트|instruction|prompt)"
#    덮어쓰려는 동작 ("됐고"처럼 우회 표현 포함)
_OVERRIDE_VERB = r"(?:무시|잊|됐|되었|버려|버리|없던\s*걸로|없던\s*일|신경\s*(?:쓰지|끄)|따르지|덮어)"

# 2) 시스템 프롬프트·내부 지침 유출 ─ 대상
_SYS_TARGET = (
    r"(?:"
    r"(?:시스템|system|초기|원본|숨겨진|숨은|내부|hidden|initial|original)\s*(?:의\s*)?"
    r"(?:프롬프트|prompt|메시지|message|지침|지시|instructions?|규칙|rules)"
    r"|(?:너|네|당신|your)\s*(?:의\s*)?(?:프롬프트|prompt|지침|지시|instructions?|규칙|rules)"
    r")"
)
#    유출하려는 동작
_REVEAL_VERB = (
    r"(?:출력|알려|보여|공개|말해|노출|전문|그대로|복사|읽어|뽑아|적어|인코딩|번역"
    r"|reveal|show|print|repeat|output|tell|display|leak|dump|give)"
)

# 3) 자격증명·비밀값 유출 ─ 대상
_SECRET = (
    r"(?:비밀\s*번호|패스워드|password|passwd|토큰|token|api\s*키|api\s*key"
    r"|액세스\s*키|access\s*key|시크릿|secret|자격\s*증명|credentials?"
    r"|private\s*key|개인\s*키|인증\s*키|세션\s*키|접속\s*정보)"
)
#    대상 바로 뒤에 조사·부사만 끼고 붙은 '꺼내 보여 달라' 동작.
#    (사이에 "만료 시간", "발급 절차" 같은 다른 명사가 끼면 정상 문의로 보고 통과)
_SECRET_DUMP = (
    _SECRET
    + r"\s*(?:들|값)?\s*(?:을|를|은|는|도|만)?\s*"
    + r"(?:전부|모두|다|좀|전체|그대로|평문으로|원문으로)?\s*"
    + r"(?:출력|보여|알려|말해|덤프|노출|공개|뽑아|읽어|적어|print|show|reveal|dump|leak|display)"
)

# 4) 역할 탈취·모드 전환
_ROLE_HIJACK_EN = (
    r"(?:you\s+are\s+now|from\s+now\s+on|act\s+as|pretend\s+(?:to\s+be|you)"
    r"|roleplay\s+as|jailbreak|\bdan\b|developer\s+mode|do\s+anything\s+now)"
)
_ROLE_HIJACK_KO = (
    r"(?:"
    # "지금부터 너의 역할은 ~", "이제부터 당신은 ~ 역할"
    r"(?:지금부터|이제부터|앞으로|이제)\s*.{0,10}?(?:너|네|당신)\S*\s*.{0,6}?(?:역할|정체|이름|임무)"
    # "새로운 역할을 부여받아라", "역할을 맡아라" (AI 자신에게 역할을 씌우는 명령형)
    r"|역할\s*(?:을|를)\s*(?:부여\s*받|맡아라|맡아|수행해라|연기해)"
    r")"
)
#    "관리자 모드로 전환", "지금부터 점검 모드야"
_MODE_SWITCH = (
    r"(?:관리자|어드민|admin|개발자|developer|디버그|debug|점검|유지\s*보수|maintenance"
    r"|god|루트|root|탈옥|제한\s*해제|무제한|sudo)\s*모드\s*(?:로|으로)?\s*"
    r"(?:전환|진입|들어가|바꿔|변경|켜|활성|야|이야|다|입니다)"
)

# 5) 인코딩·변형으로 우회하려는 유출
_ENCODING = r"(?:base\s*64|hex|rot\s*13|인코딩|암호화해서|거꾸로|역순으로|한\s*글자씩)"
_ENCODING_TARGET = (
    r"(?:시스템|지침|프롬프트|prompt|instruction|비밀|시크릿|secret|토큰|token|password|패스워드|api\s*키)"
)

# 6) 구분자·가짜 시스템 블록 주입
_DELIMITER_INJECTION = (
    r"(?:#{2,}\s*(?:new\s+|system\s+|admin\s+)?(?:instructions?|system|prompt)"
    r"|\bnew\s+instructions?\b"
    r"|<\|?\s*(?:im_start|system)\s*\|?>|</?\s*system\s*>|\[/?\s*(?:inst|system)\s*\]"
    r"|begin\s+system|end\s+of\s+(?:system\s+)?prompt)"
)

# 7) 대량 파괴 명령 (전부/모든 + 운영 대상 + 삭제)
_BULK = r"(?:전부|전체|모든|모두|싹|일괄|all)"
_DESTROY_TARGET = r"(?:운영|프로덕션|prod|db|데이터\s*베이스|database|테이블|table|자산|서버|백업|계정|데이터)"
_DESTROY_VERB = r"(?:삭제|지워|지우|날려|드롭|drop|truncate|포맷|wipe|delete)"
_DESTRUCTIVE_CMD = r"(?:rm\s+-rf\s+/|drop\s+(?:database|table)|truncate\s+table|mkfs\b|:\(\)\s*\{)"

# 질문형(절차·시점·방법 문의) 표지. 모드 전환·대량 삭제는 '명령'일 때만 막고,
# "점검 모드 전환은 언제 하나요?"처럼 묻는 문장은 통과시켜 오탐을 줄입니다.
_QUESTION = r"(?:\?|나요|까요|인가요|습니까|언제|어떻게|방법|절차|정책|가능한가|되나요|있나요)"

# (사유, 정규식, 질문형이면 통과시킬지)
_GUARD_RULES: list[tuple[str, re.Pattern[str], bool]] = [
    (
        "지시 덮어쓰기 시도 (이전 지시 + 무시/망각)",
        re.compile(
            rf"{_PRIOR}\s*(?:의\s*)?(?:모든\s*)?{_INSTR}.{{0,25}}?{_OVERRIDE_VERB}"
            rf"|(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+|any\s+|the\s+|your\s+|of\s+)*"
            rf"(?:previous|prior|above|earlier|preceding|system|original|existing)?\s*"
            rf"(?:instructions?|prompts?|rules|directions|guidelines)"
        ),
        False,
    ),
    (
        "시스템 프롬프트·내부 지침 유출 시도",
        re.compile(
            rf"{_SYS_TARGET}.{{0,30}}?{_REVEAL_VERB}|{_REVEAL_VERB}.{{0,30}}?{_SYS_TARGET}"
        ),
        False,
    ),
    (
        "자격증명·비밀값 유출 시도",
        re.compile(
            rf"{_SECRET_DUMP}"
            rf"|(?:따라\s*(?:해|하|말)|그대로\s*말해|repeat\s+after|반복해).{{0,40}}?{_SECRET}"
            rf"|(?:show|print|reveal|dump|leak|give)\s+(?:me\s+)?(?:the\s+|your\s+|all\s+)*{_SECRET}"
        ),
        False,
    ),
    (
        "역할 탈취 시도",
        re.compile(rf"{_ROLE_HIJACK_EN}|{_ROLE_HIJACK_KO}"),
        False,
    ),
    (
        "권한 모드 전환 시도",
        re.compile(_MODE_SWITCH),
        True,
    ),
    (
        "인코딩 우회를 통한 유출 시도",
        re.compile(
            rf"{_ENCODING}.{{0,40}}?{_ENCODING_TARGET}|{_ENCODING_TARGET}.{{0,40}}?{_ENCODING}"
        ),
        False,
    ),
    (
        "구분자·가짜 시스템 블록 주입",
        re.compile(_DELIMITER_INJECTION),
        False,
    ),
    (
        "대량 파괴 명령 요청",
        re.compile(
            rf"{_BULK}.{{0,15}}?{_DESTROY_TARGET}.{{0,15}}?{_DESTROY_VERB}"
            rf"|{_DESTROY_TARGET}.{{0,15}}?{_BULK}.{{0,10}}?{_DESTROY_VERB}"
            rf"|{_DESTRUCTIVE_CMD}"
        ),
        True,
    ),
]
_QUESTION_RE = re.compile(_QUESTION)
_ZERO_WIDTH_RE = re.compile(r"[​-‏⁠﻿]")
_SPACES_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """판정 전에 입력을 정규화합니다.

    - NFKC: 전각 문자(ＩＧＮＯＲＥ)·호환 문자를 일반 문자로 바꿉니다.
    - 제로폭 문자 제거: "무​시"처럼 글자 사이에 숨긴 문자로 규칙을 피하는 것을 막습니다.
    - 소문자화·공백 정리: 대소문자/줄바꿈 변형을 하나로 모읍니다.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    return _SPACES_RE.sub(" ", text).strip().lower()
# === Insert End ===


def input_guard(text: str) -> tuple[bool, str]:
    """입력을 검사해 차단 여부를 정합니다.

    Returns:
        (차단할지 여부, 사유 문자열)

    주의: 규칙을 늘릴수록 정상 요청도 막힙니다.
    normal_set에는 "이전", "무시", "새로운 역할", "관리자" 같은 함정 단어가
    일부러 들어 있습니다. 단어 하나로 막으면 오탐이 터집니다.
    """
    # TODO: 구현하세요.
    #   힌트: 단일 단어가 아니라 '지시를 덮어쓰려는 의도'의 조합을 보세요.
    # === Delete Begin ===
    # D : raise NotImplementedError("input_guard 를 구현하세요.")
    # === Delete End ===
    # === Insert Begin ===
    # 비정상 입력 방어: None·비문자열이 와도 예외 없이 판정을 돌려줍니다.
    if not isinstance(text, str):
        text = "" if text is None else str(text)

    norm = _normalize(text)
    # 빈 입력·공백만 있는 입력은 막지 않습니다. (막을 의도 자체가 없음)
    if not norm:
        return False, "통과: 빈 입력"

    is_question = bool(_QUESTION_RE.search(norm))
    for reason, pattern, allow_question in _GUARD_RULES:
        if pattern.search(norm):
            # 모드 전환·대량 삭제는 '명령'일 때만 차단, '문의'면 통과
            if allow_question and is_question:
                continue
            return True, f"차단: {reason}"

    return False, "통과: 차단 규칙에 해당하지 않음"
    # === Insert End ===


# === Insert Begin ===
# ──────────────────────────────────────────────────────────────────
# PII·자격증명 마스킹 규칙
#
#   - 치환 토큰([JWT], [EMAIL] …)에는 숫자·@·점이 없어서 다시 돌려도 아무 패턴에도
#     걸리지 않습니다 → 두 번 돌려도 결과가 같음(멱등).
#   - 가릴 게 없으면 re.sub가 원문을 그대로 돌려줍니다 → 무해 입력 보존.
#   - 순서: 긴/구체적인 패턴(JWT, AWS 키) → 이메일 → 전화번호 → 사번.
#     JWT 안의 문자열이 다른 패턴에 먼저 잘려 나가지 않게 하기 위함입니다.
# ──────────────────────────────────────────────────────────────────
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # JWT: eyJ로 시작하는 header.payload(.signature)
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*)?"), "[JWT]"),
    # AWS 액세스 키: AKIA(장기) / ASIA(임시) + 대문자·숫자 16자
    (re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"), "[AWS_KEY]"),
    # 이메일
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    # 전화번호: 010-1234-5678 / 01012345678 / 02-123-4567 / +82 10-1234-5678
    (
        re.compile(r"(?<!\d)(?:\+82[-.\s]?|0)\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"),
        "[PHONE]",
    ),
    # 사번: E + 숫자 6자리 (앞뒤로 영숫자가 붙어 있으면 다른 식별자로 보고 제외)
    (re.compile(r"(?<![A-Za-z0-9])E\d{6}(?![0-9])"), "[EMP_ID]"),
]
# === Insert End ===


def mask_pii(text: str) -> str:
    """개인정보와 자격증명을 마스킹합니다.

    최소 다섯 가지를 가려야 합니다.
      사번(예: E123456) · 전화번호 · 이메일 · AWS 액세스 키(AKIA...) · JWT(eyJ...)
    """
    # TODO: 구현하세요.
    # === Delete Begin ===
    # D : raise NotImplementedError("mask_pii 를 구현하세요.")
    # === Delete End ===
    # === Insert Begin ===
    if not isinstance(text, str) or not text:
        return text
    for pattern, token in _PII_PATTERNS:
        text = pattern.sub(token, text)
    return text
    # === Insert End ===


# TODO: 미들웨어를 어떤 순서로 둘지 정하세요.
#   원칙: 차단 -> 정제 -> 검증 -> 기록
#   마스킹이 로깅보다 뒤에 있으면 로그에 원본이 남습니다. 순서 자체가 설계입니다.
#   아래 이름을 그대로 쓰되 순서만 바꾸면 됩니다.
# === Mody Begin ===
# M : MIDDLEWARE_ORDER: list[str] = [
# M :     # "LoggingMiddleware",
# M :     # "MaskingMiddleware",
# M :     # "OutputCheckMiddleware",
# M :     # "InputGuardMiddleware",
# M : ]
MIDDLEWARE_ORDER: list[str] = [
    "InputGuardMiddleware",   # 차단: 공격 입력은 가장 먼저 끊는다
    "MaskingMiddleware",      # 정제: 이후 단계(모델·로그)에 원본 PII가 흘러가지 않게
    "OutputCheckMiddleware",  # 검증: 무엇이 걸렸는지 판정 결과를 만든다
    "LoggingMiddleware",      # 기록: 마스킹·검증이 끝난 결과만 남긴다
]
# === Mody End ===


# ══════════════════════════════════════════════════════════════════
# 심화 파트 (3점) — 못 해도 과제는 통과합니다
# ══════════════════════════════════════════════════════════════════

# TODO: 도구별 위험도를 정하세요. 값은 "read" | "write" | "destructive" 중 하나입니다.
#   조회는 read, 상태를 바꾸면 write, 되돌릴 수 없으면 destructive.
# === Mody Begin ===
# M : RISK_LEVELS: dict[str, str] = {}
RISK_LEVELS: dict[str, str] = {
    # read: 조회만 함 → 자동 실행 (넉넉히 채워 둬야 승인 알림 피로가 안 생김)
    "get_asset_status": "read",
    "get_asset_status_backup": "read",
    "get_metrics": "read",
    "get_logs": "read",
    "get_deploy_history": "read",
    "search_policies": "read",
    "list_assets": "read",
    # write: 상태를 바꾸지만 되돌릴 수 있음 → 승인 필요
    "restart_service": "write",
    "scale_service": "write",
    "update_config": "write",
    "rollback_deploy": "write",
    # destructive: 되돌릴 수 없음 → 승인 + 이중 확인
    "delete_asset": "destructive",
    "rotate_credentials": "destructive",
    "drop_database": "destructive",
    "revoke_access": "destructive",
}
# === Mody End ===


def needs_approval(tool_name: str, args: dict) -> tuple[bool, str]:
    """이 도구 호출에 사람 승인이 필요한지 판정합니다. LLM을 호출하지 않습니다.

    규칙:
      - read         -> 승인 불필요. (전부 막으면 자동화의 의미가 없습니다)
      - write        -> 승인 필요
      - destructive  -> 승인 필요 + 이중 확인 표시
      - 목록에 없는 도구 -> 승인 필요 (모르는 것은 막는다)

    Returns:
        (승인이 필요한가, 사유 또는 확인 수준)
        destructive인 경우 사유 문자열에 "이중" 또는 "double" 을 포함하세요.
    """
    # TODO: 구현하세요.
    # === Delete Begin ===
    # D : raise NotImplementedError("needs_approval 을 구현하세요.")
    # === Delete End ===
    # === Insert Begin ===
    level = RISK_LEVELS.get(tool_name)

    if level == "read":
        return False, f"read: '{tool_name}'은 조회 도구라 승인 없이 자동 실행합니다."
    if level == "write":
        return True, f"write: '{tool_name}'은 상태를 바꾸므로 사람 승인이 필요합니다."
    if level == "destructive":
        return True, (
            f"destructive: '{tool_name}'은 되돌릴 수 없습니다. "
            "승인 + 이중 확인(double confirmation)이 필요합니다."
        )
    # 목록에 없거나 등급이 잘못 적힌 도구 → 안전한 쪽(승인 필요)으로 실패
    return True, f"unknown: '{tool_name}'은 위험도가 등록되지 않은 도구라 승인이 필요합니다."
    # === Insert End ===
