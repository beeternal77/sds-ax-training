"""Day 4 — 운영 지원 MCP 서버와 장애 복구.

[중요]
  1. 함수·상수 이름을 바꾸지 마세요.
  2. 도구는 예외를 밖으로 던지지 않습니다. 무엇이 잘못됐는지 설명하는 문자열을 돌려주세요.
     그 문자열은 모델이 읽고 다음 행동을 정하는 프롬프트입니다.
  3. 자격증명은 절대 반환값이나 로그에 남기지 마세요.
"""

from __future__ import annotations

import json
# === Insert Begin ===
# backoff 전략에서 재시도 간격을 늘리기 위해 time.sleep을 씁니다.
import time
# === Insert End ===
from pathlib import Path
from typing import Any, Callable

DATA = json.loads(
    (Path(__file__).resolve().parent.parent / "data" / "ops_assets.json").read_text(
        encoding="utf-8"
    )
)

# 교육용 더미 자격증명입니다. 이 값이 로그나 반환값에 남으면 채점에서 감점됩니다.
BACKEND_TOKEN = "sk-internal-dummy-1234"

MAX_RETRIES = 3

# === Insert Begin ===
# 재시도 대기 시간(초)입니다.
#   - retryable: 짧고 일정한 간격으로 다시 묻습니다.
#   - backoff  : 시도할 때마다 간격을 두 배로 늘립니다 (지수 백오프).
# 교육·채점 환경에서 테스트가 느려지지 않도록 값을 작게 잡았습니다.
# 실제 운영에서는 retryable 0.5~1초, backoff 1초부터 시작하는 식으로 키웁니다.
RETRY_DELAY_SEC = 0.05
BACKOFF_BASE_SEC = 0.1


def _redact(text: str) -> str:
    """문자열 안의 자격증명을 가립니다.

    예외 메시지에는 백엔드가 돌려준 원문(요청 헤더 등)이 섞여 들어올 수 있습니다.
    README 로그 두 번째 줄처럼 토큰이 그대로 찍히는 일을 막기 위해,
    밖으로 나가는 모든 문자열은 이 함수를 한 번 거치게 합니다.
    """
    return str(text).replace(BACKEND_TOKEN, "***REDACTED***")


def _format_asset(asset_id: str, asset: dict) -> str:
    """자산 정보를 모델이 읽기 쉬운 한 줄로 만듭니다. 토큰 같은 민감 필드는 넣지 않습니다."""
    return (
        f"자산 {asset_id}: 이름={asset.get('name', '알 수 없음')}, "
        f"상태={asset.get('status', '알 수 없음')}, 담당팀={asset.get('owner', '알 수 없음')}"
    )
# === Insert End ===


# ══════════════════════════════════════════════════════════════════
# 기초 파트 (7점)
# ══════════════════════════════════════════════════════════════════

def search_runbook(symptom: str) -> str:
    """증상 키워드로 대응 런북을 찾습니다."""
    # TODO: DATA["runbooks"]에서 찾아 문자열로 반환하세요.
    #   없는 키워드면 예외가 아니라 "어떤 키워드가 있는지" 알려 주는 문자열을 반환합니다.
    # === Insert Begin ===
    runbooks = DATA["runbooks"]
    available = ", ".join(runbooks)
    # 모델이 "5XX", " oom " 처럼 보낼 수 있으므로 공백과 대소문자를 정리해서 찾습니다.
    key = str(symptom or "").strip().lower()
    if key in runbooks:
        return f"[런북: {key}] {runbooks[key]}"
    # 예외 대신 "다음에 무엇을 넣으면 되는지"를 알려 줘야 모델이 호출을 고쳐 잡습니다.
    return (
        f"등록되지 않은 증상 키워드예요: '{symptom}'. "
        f"쓸 수 있는 값: {available}. 이 중 하나로 다시 호출하세요."
    )
    # === Insert End ===
    # === Delete Begin ===
    # D : raise NotImplementedError("search_runbook 을 구현하세요.")
    # === Delete End ===


def get_service_owner(service: str) -> str:
    """서비스의 담당팀과 온콜 담당자를 조회합니다."""
    # TODO: DATA["owners"] 에서 조회하세요.
    # === Insert Begin ===
    owners = DATA["owners"]
    key = str(service or "").strip()
    owner = owners.get(key)
    if owner:
        return (
            f"서비스 {key}: 담당팀={owner['team']}, 온콜={owner['oncall']}, "
            f"알림 채널={owner['slack']}"
        )
    return (
        f"등록되지 않은 서비스예요: '{service}'. "
        f"조회 가능한 서비스: {', '.join(owners)}. 서비스 이름을 확인해 다시 호출하세요."
    )
    # === Insert End ===
    # === Delete Begin ===
    # D : raise NotImplementedError("get_service_owner 를 구현하세요.")
    # === Delete End ===


def query_recent_incidents(service: str) -> str:
    """서비스의 최근 인시던트 이력을 조회합니다."""
    # TODO: DATA["incidents"] 에서 조회하세요.
    # === Insert Begin ===
    incidents = DATA["incidents"]
    key = str(service or "").strip()
    if key not in incidents:
        # 담당자 목록에는 있지만 인시던트가 없는 서비스(gateway 등)는 "이력 없음"으로 구분합니다.
        # "없는 서비스"와 "사고가 없었던 서비스"는 모델이 다르게 해석해야 하기 때문입니다.
        if key in DATA["owners"]:
            return f"서비스 {key}: 기록된 최근 인시던트가 없습니다."
        known = sorted(set(incidents) | set(DATA["owners"]))
        return (
            f"등록되지 않은 서비스예요: '{service}'. "
            f"조회 가능한 서비스: {', '.join(known)}. 서비스 이름을 확인해 다시 호출하세요."
        )
    lines = [
        f"- {inc['id']} ({inc['at']}) {inc['title']} / 원인: {inc['cause']}"
        for inc in incidents[key]
    ]
    return f"서비스 {key} 최근 인시던트 {len(lines)}건:\n" + "\n".join(lines)
    # === Insert End ===
    # === Delete Begin ===
    # D : raise NotImplementedError("query_recent_incidents 를 구현하세요.")
    # === Delete End ===


# TODO: MCP로 노출할 도구 명세를 채우세요.
#   각 항목: {"name": ..., "description": 30자 이상, "args": {인자명: 설명}}
#   description에는 '언제 쓰는지'와 '언제 쓰지 말아야 하는지'를 적으세요.
# === Mody Begin ===
# M : TOOL_SPECS: list[dict] = []
# MCP로 내보내면 이 설명문은 우리가 손댈 수 없는 다른 클라이언트·모델이 읽습니다.
# 그래서 '언제 쓰는지'와 '언제 쓰지 말아야 하는지', 인자에 넣을 수 있는 값을 구체적으로 적습니다.
TOOL_SPECS: list[dict] = [
    {
        "name": "search_runbook",
        "description": (
            "장애 증상 키워드로 1차 대응 런북(조치 순서)을 찾습니다. "
            "증상은 알지만 무엇부터 해야 할지 모를 때 씁니다. "
            "담당자 조회나 과거 인시던트 이력 확인에는 쓰지 마세요."
        ),
        "args": {"symptom": "증상 키워드. 사용 가능한 값: 5xx, oom, cert"},
    },
    {
        "name": "get_service_owner",
        "description": (
            "서비스 이름으로 담당팀, 온콜 담당자, 알림 슬랙 채널을 조회합니다. "
            "누구에게 에스컬레이션할지 정할 때 씁니다. "
            "장애 조치 방법이나 과거 장애 이력을 찾을 때는 쓰지 마세요."
        ),
        "args": {"service": "서비스 이름. 예: payment-api, auth-service, gateway"},
    },
    {
        "name": "query_recent_incidents",
        "description": (
            "서비스 이름으로 최근 인시던트 이력(ID, 날짜, 제목, 원인)을 조회합니다. "
            "같은 장애가 반복되는지, 과거 원인이 무엇이었는지 확인할 때 씁니다. "
            "현재 자산 상태나 담당자 조회에는 쓰지 마세요."
        ),
        "args": {"service": "서비스 이름. 예: payment-api, auth-service"},
    },
]
# === Mody End ===

# TODO: 이름 -> 실제 함수 매핑. TOOL_SPECS의 name과 키가 정확히 일치해야 합니다.
# === Mody Begin ===
# M : TOOLS_IMPL: dict[str, Any] = {}
TOOLS_IMPL: dict[str, Any] = {
    "search_runbook": search_runbook,
    "get_service_owner": get_service_owner,
    "query_recent_incidents": query_recent_incidents,
}
# === Mody End ===


def _default_fetch(asset_id: str) -> dict:
    """기본 자산 조회 경로입니다. 실제로는 외부 시스템을 호출한다고 가정합니다."""
    asset = DATA["assets"].get(asset_id)
    if not asset:
        raise LookupError(f"asset not found: {asset_id}")
    return asset


def get_asset_status(asset_id: str, fetch: Callable[[str], dict] | None = None) -> str:
    """자산 상태를 조회합니다. 실패하면 재시도하고, 그래도 안 되면 대체 경로를 씁니다.

    반드시 지킬 것:
      - 어떤 경우에도 예외를 밖으로 던지지 않습니다.
      - 대체 경로로 넘어갔다면 반환 문자열에 'get_asset_status_backup' 이름을 남깁니다.
        모델이 다음에 무엇을 할지 알아야 하기 때문입니다.
      - BACKEND_TOKEN 값을 반환 문자열에 넣지 마세요.

    Args:
        asset_id: 조회할 자산 ID
        fetch: 외부 조회 함수. 채점기가 실패하는 함수를 넣습니다. None이면 기본 경로.
    """
    fetch = fetch or _default_fetch
    # TODO: 구현하세요.
    #   1) fetch를 호출한다
    #   2) 실패하면 재시도한다 (심화를 했다면 classify_failure로 전략을 나눈다)
    #   3) 끝내 실패하면 get_asset_status_backup 으로 넘어간다
    # === Insert Begin ===
    # MAX_RETRIES는 "백엔드 총 호출 횟수 상한"으로 씁니다. (README: 총 호출은 상한 이하)
    last_kind = "unknown"
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            asset = fetch(asset_id)
            # 재시도 끝에 살아난 값이면 그 사실도 함께 남겨 둡니다. 되살아난 값을 버리지 않습니다.
            suffix = f" (시도 {attempt}회째 성공)" if attempt > 1 else ""
            return _redact(_format_asset(asset_id, asset) + suffix)
        except Exception as exc:  # noqa: BLE001 — 도구는 예외를 밖으로 던지지 않습니다.
            last_kind = classify_failure(exc)
            # 예외 메시지에 토큰이 섞여 있을 수 있으므로 반드시 가린 뒤 보관합니다.
            last_error = _redact(f"{type(exc).__name__}: {exc}")

            # fatal: 다시 물어도 답이 같으므로 재시도하지 않고 즉시 대체 경로로 갑니다.
            if last_kind == "fatal":
                break
            # 마지막 시도였으면 기다릴 필요 없이 대체 경로로 갑니다.
            if attempt == MAX_RETRIES:
                break
            # backoff: 한도를 더 깎지 않도록 간격을 지수적으로 늘립니다.
            # retryable: 짧고 일정한 간격으로 다시 묻습니다.
            if last_kind == "backoff":
                time.sleep(BACKOFF_BASE_SEC * (2 ** (attempt - 1)))
            else:
                time.sleep(RETRY_DELAY_SEC)

    # 여기까지 왔으면 기본 경로는 실패한 것입니다.
    # 반환 문자열에 대체 도구 이름과 실패 종류를 남겨, 모델과 담당자가
    # "지금 값이 실시간이 아니라 대체 경로 값"임을 알 수 있게 합니다.
    backup = get_asset_status_backup(asset_id)
    return _redact(
        f"기본 조회 실패({last_kind}, 시도 {attempt}회, 마지막 오류 {last_error}) "
        f"→ get_asset_status_backup 대체 경로로 전환했습니다. {backup}"
    )
    # === Insert End ===
    # === Delete Begin ===
    # D : raise NotImplementedError("get_asset_status 를 구현하세요.")
    # === Delete End ===


def get_asset_status_backup(asset_id: str) -> str:
    """대체 조회 경로입니다. 캐시된 값이나 축약 정보를 돌려준다고 가정합니다."""
    # TODO: 구현하세요. 실패해도 예외를 던지지 않습니다.
    # === Insert Begin ===
    try:
        key = str(asset_id or "").strip()
        if not key:
            return (
                "[get_asset_status_backup] 자산 ID가 비어 있습니다. "
                f"조회 가능한 ID: {', '.join(DATA['assets'])}"
            )
        asset = DATA["assets"].get(key)
        if not asset:
            return (
                f"[get_asset_status_backup] 캐시에도 자산 '{key}'가 없습니다. "
                f"조회 가능한 ID: {', '.join(DATA['assets'])}. ID를 확인하세요."
            )
        # 캐시 값임을 분명히 밝혀, 현재 상태로 착각해 "정상입니다"라고 보고하는 일을 막습니다.
        return _redact(
            f"[get_asset_status_backup] 캐시된 값이며 현재 상태와 다를 수 있습니다. "
            + _format_asset(key, asset)
        )
    except Exception as exc:  # noqa: BLE001 — 대체 경로도 예외를 밖으로 던지지 않습니다.
        return _redact(
            f"[get_asset_status_backup] 대체 조회도 실패했습니다 ({type(exc).__name__}). "
            "담당팀에 직접 확인이 필요합니다."
        )
    # === Insert End ===
    # === Delete Begin ===
    # D : raise NotImplementedError("get_asset_status_backup 을 구현하세요.")
    # === Delete End ===


# ══════════════════════════════════════════════════════════════════
# 심화 파트 (3점) — 못 해도 과제는 통과합니다
# ══════════════════════════════════════════════════════════════════

def classify_failure(error: BaseException | str) -> str:
    """실패를 세 종류로 분류합니다. LLM을 호출하지 않습니다.

    반환값은 정확히 다음 셋 중 하나여야 합니다.

      "retryable"  타임아웃, 일시적 연결 오류      -> 짧게 재시도
      "backoff"    요청 한도 초과 (rate limit)     -> 간격을 늘려 재시도
      "fatal"      스키마 오류, 인증 실패, 없는 자원 -> 재시도하지 말고 즉시 대체 경로

    판단 근거는 예외 타입이나 메시지 문자열 어느 쪽을 써도 됩니다.
    """
    # TODO: 구현하세요.
    # === Insert Begin ===
    # 기준은 하나: "다시 물었을 때 답이 달라질 수 있는가?"
    msg = str(error).lower()

    # 1) 요청 한도 초과는 메시지로 먼저 판단합니다.
    #    RuntimeError("429 Too Many Requests")처럼 타입만으로는 구분되지 않기 때문입니다.
    if any(k in msg for k in ("429", "too many requests", "rate limit", "ratelimit", "throttl")):
        return "backoff"

    # 2) 타임아웃·연결 오류는 다시 물으면 달라질 수 있으므로 짧게 재시도합니다.
    if isinstance(error, (TimeoutError, ConnectionError)):
        return "retryable"
    if any(k in msg for k in ("timeout", "timed out", "connection reset", "connection refused",
                              "temporarily unavailable", "503")):
        return "retryable"

    # 3) 나머지(스키마 오류, 인증 실패, 없는 자원, 알 수 없는 오류)는 fatal로 봅니다.
    #    모르는 오류를 재시도 쪽으로 보내면 README 로그처럼 39번을 다시 물을 수 있으므로,
    #    애매하면 재시도하지 않고 대체 경로로 보내는 쪽이 안전합니다.
    return "fatal"
    # === Insert End ===
    # === Delete Begin ===
    # D : raise NotImplementedError("classify_failure 를 구현하세요.")
    # === Delete End ===
