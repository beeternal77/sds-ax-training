"""도메인 도구 — IT 헬프데스크 (Day 3 ReAct 도구, Day 4 도구 계약 패턴).

설계 원칙
- 도구는 예외를 밖으로 던지지 않습니다. 실패도 모델이 읽을 수 있는 문장(dict의 "error")으로 돌려줍니다.
  예외가 도구 밖으로 새면 Agent 세션이 통째로 끝나기 때문입니다. (Day 4)
- 요청자 사번(user_id)은 **모델이 인자로 고르지 않습니다.** make_tools(user_id)가 요청자 사번을
  도구 안에 미리 묶어 둡니다. 그래서 모델이 프롬프트 인젝션에 넘어가도 다른 사람 정보는
  구조적으로 조회할 수 없습니다. (SERVICE.md 정책 1 "본인 정보만 조회")
- 데이터는 data/db/helpdesk.json 의 교육용 더미 데이터입니다.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "db" / "helpdesk.json"

# 되돌리기 어려운 작업 = 승인 필요 (Day 5 심화 needs_approval 패턴)
APPROVAL_REQUIRED = {"unlock_account"}


@lru_cache(maxsize=1)
def _db() -> dict:
    """더미 DB를 한 번만 읽어 둡니다."""
    return json.loads(DB_PATH.read_text(encoding="utf-8"))


# ── 순수 함수 (테스트·평가에서 LLM 없이 바로 호출) ──────────────────────────


def get_my_account(user_id: str) -> dict:
    """요청자 본인의 계정 상태(잠금 여부, 실패 횟수, 비밀번호 만료일)를 돌려줍니다."""
    acc = _db()["accounts"].get(user_id)
    if acc is None:
        return {"error": f"사번 {user_id} 의 계정을 찾지 못했습니다. 헬프데스크(#it-helpdesk)에 계정 등록 여부를 문의하세요."}
    # 이름은 응답에 필요 없으므로 내보내지 않습니다. (개인정보 최소화)
    return {k: v for k, v in acc.items() if k != "name"} | {"user_id": user_id}


def get_my_assets(user_id: str) -> dict:
    """요청자 본인에게 지급된 자산 목록을 돌려줍니다."""
    assets = _db()["assets"].get(user_id, [])
    if not assets:
        return {"assets": [], "error": "지급된 자산이 조회되지 않습니다. 자산 등록 문의는 헬프데스크(#it-helpdesk)로 하세요."}
    return {"assets": assets}


def check_license(user_id: str, asset_id: str) -> dict:
    """자산에 배정된 라이선스와 만료일을 돌려줍니다. 본인 자산이 아니면 거절합니다."""
    own_ids = {a["asset_id"] for a in _db()["assets"].get(user_id, [])}
    if asset_id not in own_ids:
        # 모델이 다른 사람 자산 ID를 넣는 경우까지 막습니다.
        return {"error": f"{asset_id} 는 요청자 본인 자산이 아닙니다. 본인 자산은 get_my_assets 로 먼저 확인하세요."}
    lic = _db()["licenses"].get(asset_id, [])
    if not lic:
        return {"asset_id": asset_id, "licenses": [], "error": "배정된 라이선스가 없습니다."}
    return {"asset_id": asset_id, "licenses": lic}


def unlock_account(user_id: str, approved: bool = False) -> dict:
    """계정 잠금 해제. 승인 전에는 실행하지 않고 '승인 요청 접수'만 돌려줍니다. (Day 5 HITL)

    실제 해제는 담당자가 승인(approved=True)했을 때만 일어납니다.
    Day 9에 LangGraph interrupt() 로 이 지점에서 그래프를 멈추도록 연결합니다.
    """
    acc = _db()["accounts"].get(user_id)
    if acc is None:
        return {"error": f"사번 {user_id} 의 계정을 찾지 못했습니다."}
    if not acc["locked"]:
        return {"status": "not_locked", "message": "계정이 잠겨 있지 않습니다. 해제할 필요가 없습니다."}
    if not approved:
        return {
            "status": "pending_approval",
            "message": "잠금 해제 요청이 접수되었습니다. 헬프데스크 담당자 승인 후 해제됩니다. (잠금은 30분 후 자동 해제되기도 합니다)",
        }
    # 교육용: 더미 DB를 실제로 바꾸지는 않고 결과만 돌려줍니다.
    return {"status": "unlocked", "message": "담당자 승인으로 계정 잠금이 해제되었습니다.",
            "unlocked_at": datetime.now().isoformat(timespec="seconds")}


# ── LangChain 도구로 감싸기 (Day 9에 agent.py 에서 bind_tools 로 사용) ─────────


def make_tools(user_id: str) -> list[Any]:
    """요청자 사번을 묶은 LangChain 도구 목록을 만듭니다.

    모델에게 보이는 인자에는 user_id 가 없습니다. → 다른 사람 정보 조회 경로가 원천 차단됩니다.
    retrieve_docs 는 retriever.py 에서 따로 만들어 agent.py 에서 합칩니다.
    """
    from langchain_core.tools import tool  # 함수 안에서 import: 모듈 로드만으로 무거운 의존성을 끌어오지 않음

    @tool
    def get_my_account_tool() -> dict:
        """요청자 본인의 계정 상태(잠금 여부, 비밀번호 연속 실패 횟수, 비밀번호 만료일)를 조회한다.
        계정 잠김·로그인 실패·비밀번호 만료 질문에 쓴다."""
        return get_my_account(user_id)

    @tool
    def get_my_assets_tool() -> dict:
        """요청자 본인에게 지급된 PC·노트북·모니터 등 자산 목록(asset_id, 모델명)을 조회한다.
        라이선스를 조회하려면 먼저 이 도구로 asset_id 를 얻는다."""
        return get_my_assets(user_id)

    @tool
    def check_license_tool(asset_id: str) -> dict:
        """자산(asset_id)에 배정된 SW 라이선스 이름과 만료일을 조회한다.
        asset_id 는 get_my_assets_tool 결과에서 가져온 값만 쓴다."""
        return check_license(user_id, asset_id)

    @tool
    def unlock_account_tool() -> dict:
        """요청자 본인 계정의 잠금 해제를 요청한다. 담당자 승인이 필요한 작업이며,
        이 도구는 승인 요청을 접수할 뿐 즉시 해제하지 않는다."""
        return unlock_account(user_id, approved=False)

    # 모델에게 보이는 이름은 SERVICE.md·test_queries.csv 의 도구 이름과 맞춥니다.
    get_my_account_tool.name = "get_my_account"
    get_my_assets_tool.name = "get_my_assets"
    check_license_tool.name = "check_license"
    unlock_account_tool.name = "unlock_account"
    return [get_my_account_tool, get_my_assets_tool, check_license_tool, unlock_account_tool]
