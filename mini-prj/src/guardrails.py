"""가드레일 — 입력 차단과 PII 마스킹 (Day 5 패턴).

Day 8 상태: 최소 규칙만 들어 있는 뼈대입니다.
Day 9 TODO: day05/practice/starter/submission.py 의 input_guard·mask_pii 규칙을 이식해 보강합니다.
  (정규화 → 의도 조합 규칙 → 질문형 예외 순서 유지)
"""

from __future__ import annotations

import re

# ── 입력 가드: (차단 여부, 사유) ──────────────────────────────────────────────
# 단어 하나가 아니라 "의도의 조합"으로 막습니다. "지난주 장애 이력" 같은 정상 질문이 같이 막히지 않게. (Day 5)
_PRIOR = r"(?:이전|지난|앞선|기존|원래|모든)"
_INSTR = r"(?:지시|지침|명령|규칙|프롬프트|instruction|prompt)"
_OVERRIDE = r"(?:무시|잊어|됐고|취소|ignore|forget)"
_SECRET = r"(?:시스템\s*프롬프트|system\s*prompt|관리자\s*비밀번호|admin\s*password|api\s*키|토큰|자격\s*증명)"

_RULES: list[tuple[str, re.Pattern]] = [
    ("prompt_injection", re.compile(rf"{_PRIOR}\s*{_INSTR}\S*\s*.{{0,6}}{_OVERRIDE}", re.I)),
    ("secret_request", re.compile(rf"{_SECRET}.{{0,10}}(?:알려|보여|출력|말해|tell|show)", re.I)),
    ("approval_bypass", re.compile(r"승인\s*(?:필요\s*없|없이|생략|건너)", re.I)),
]


def input_guard(text: str) -> tuple[bool, str]:
    """차단해야 하면 (True, 사유)를, 통과면 (False, "")를 돌려줍니다."""
    for reason, pat in _RULES:
        if pat.search(text):
            return True, reason
    return False, ""


# ── PII 마스킹: 로그·trace·응답에 남기 전에 적용 ───────────────────────────────
_PII_PATTERNS = [
    (re.compile(r"01[016789]-?\d{3,4}-?\d{4}"), "[전화번호]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[이메일]"),
    (re.compile(r"\d{6}-?[1-4]\d{6}"), "[주민번호]"),
]


def mask_pii(text: str) -> str:
    """전화번호·이메일·주민번호 형태를 가립니다."""
    for pat, repl in _PII_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ── 본인 외 조회 시도 감지 ────────────────────────────────────────────────────
# 도구는 구조적으로 본인 정보만 조회하지만(tools.make_tools), 질문 단계에서 먼저 거절해
# "왜 안 되는지"를 정중하게 안내합니다.
_OTHER_PERSON = re.compile(r"[가-힣]{2,4}\s*(?:과장|대리|부장|차장|사원|선임|책임|수석|님)\S*\s*(?:계정|자산|노트북|연차|비밀번호)")
_OTHER_EMPNO = re.compile(r"E\d{6}")


def is_other_person_request(text: str, user_id: str) -> bool:
    """질문이 요청자 본인이 아닌 다른 사람의 정보를 묻는지 판정합니다."""
    if _OTHER_PERSON.search(text):
        return True
    return any(emp != user_id for emp in _OTHER_EMPNO.findall(text))
