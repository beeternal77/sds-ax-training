"""Day 7 — 계측과 누적 평가.

6일간 쌓은 시스템을 측정합니다.

[중요]
  1. 함수·상수 이름을 바꾸지 마세요.
  2. run_eval과 compare_eval은 LLM을 호출하지 않습니다.
     '답이 맞았는가'의 판정은 호출자가 넘겨 준 함수가 합니다.
"""

from __future__ import annotations

import json
# === Insert Begin ===
import time
# === Insert End ===
from pathlib import Path
from typing import Any, Callable

# 판정 결과에 쓰는 상태값입니다. 이 셋만 씁니다.
PASS, FAIL, ERROR = "pass", "fail", "error"

# === Insert Begin ===
# trace 에 허용하는 이벤트 종류입니다. README 가 정한 네 가지만 받습니다.
#   - 오타("tool_strat" 등)가 조용히 기록되면 나중에 이벤트 개수를 셀 때 숫자가 어긋납니다.
#   - 그래서 목록 밖의 값은 기록하는 순간 ValueError 로 바로 알려 줍니다.
TRACE_EVENTS = ("llm_start", "llm_end", "tool_start", "tool_end")
# === Insert End ===


# ══════════════════════════════════════════════════════════════════
# 기초 파트 (7점)
# ══════════════════════════════════════════════════════════════════

class TraceCollector:
    """실행 중 일어난 일을 기록합니다.

    LangChain 콜백 핸들러로도 쓸 수 있게 만들되, 여기서는 최소 인터페이스만 요구합니다.
    trace는 결정적 구조체라서, LLM이 무슨 말을 했든 이벤트 개수와 필드는 확정 검사됩니다.
    """

    def __init__(self) -> None:
        # TODO: 기록을 담을 목록을 준비하세요.
        # === Delete Begin ===
        # D : raise NotImplementedError("TraceCollector.__init__ 을 구현하세요.")
        # === Delete End ===
        # === Insert Begin ===
        # 이벤트 dict 를 기록된 순서대로 쌓아 두는 목록입니다.
        #   - 이름 앞의 밑줄(_)은 "클래스 안에서만 쓰는 값"이라는 표시입니다.
        #   - 바깥에서는 events 속성(복사본)으로만 읽게 합니다.
        self._events: list[dict] = []
        # === Insert End ===

    def record(self, event: str, name: str, **fields: Any) -> None:
        """이벤트 하나를 기록합니다.

        event: "llm_start" | "llm_end" | "tool_start" | "tool_end" 중 하나
        name : 모델 이름 또는 도구 이름
        fields: latency_s, tokens 등 부가 정보
        """
        # TODO: 구현하세요. 최소한 event, name, 그리고 순번을 남기세요.
        # === Delete Begin ===
        # D : raise NotImplementedError("TraceCollector.record 를 구현하세요.")
        # === Delete End ===
        # === Insert Begin ===
        # 1) 허용된 이벤트인지 검사합니다.
        if event not in TRACE_EVENTS:
            raise ValueError(
                f"알 수 없는 이벤트입니다: {event!r} (허용: {', '.join(TRACE_EVENTS)})"
            )

        # 2) 기본 필드를 채웁니다.
        #   - seq  : 0부터 1씩 늘어나는 순번. "몇 번째로 일어난 일인지"를 확정적으로 알려 줍니다.
        #   - event: 이벤트 종류
        #   - name : 모델 이름 또는 도구 이름
        #   - ts   : 기록 시각(유닉스 초). 이벤트 사이 간격을 나중에 계산할 때 씁니다.
        entry: dict[str, Any] = {
            "seq": len(self._events),
            "event": event,
            "name": name,
            "ts": time.time(),
        }

        # 3) 부가 필드(latency_s, tokens 등)를 그대로 싣습니다.
        #    fields 에 seq/event/name 같은 이름이 들어와도 기본 필드를 덮어쓰지 않게 건너뜁니다.
        for key, value in fields.items():
            if key in ("seq", "event", "name"):
                continue
            entry[key] = value

        # 4) 목록 끝에 추가합니다.
        self._events.append(entry)
        # === Insert End ===

    @property
    def events(self) -> list[dict]:
        """기록된 이벤트 목록을 반환합니다."""
        # TODO: 구현하세요.
        # === Delete Begin ===
        # D : raise NotImplementedError("TraceCollector.events 를 구현하세요.")
        # === Delete End ===
        # === Insert Begin ===
        # 내부 목록을 그대로 주지 않고 복사본을 돌려줍니다.
        #   - 바깥에서 받은 목록에 append 하거나 dict 값을 고쳐도 기록 원본은 바뀌지 않습니다.
        #   - 목록만 복사하면 안의 dict 는 같은 객체라서, dict 도 하나씩 복사합니다.
        return [dict(e) for e in self._events]
        # === Insert End ===

    def dump(self, path: str | Path) -> None:
        """이벤트를 JSON Lines 파일로 씁니다. 한 줄에 한 이벤트."""
        # TODO: 구현하세요.
        # === Delete Begin ===
        # D : raise NotImplementedError("TraceCollector.dump 를 구현하세요.")
        # === Delete End ===
        # === Insert Begin ===
        # 문자열 경로가 들어와도 Path 로 바꿔서 같은 방식으로 다룹니다.
        path = Path(path)
        # 상위 폴더가 없으면 만들어 줍니다. (예: runs/day07/trace.jsonl)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as f:
            for e in self._events:
                # 이벤트 하나 = JSON 한 줄. 줄바꿈으로 구분합니다.
                #   - ensure_ascii=False : 한글을 \uXXXX 로 바꾸지 않고 원문 그대로 씁니다.
                #   - default=str        : datetime 처럼 JSON 으로 못 바꾸는 값은 문자열로 적습니다.
                f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        # === Insert End ===


def run_eval(answer_fn: Callable[[str], Any], eval_set: list[dict],
             judge: Callable[[dict, Any], bool] | None = None) -> dict:
    """평가셋을 전부 돌려 유형별 통과율을 냅니다.

    Args:
        answer_fn: 질문 문자열을 받아 답을 돌려주는 함수. 예외가 날 수 있습니다.
        eval_set: [{"id", "question", "type", ...}] 목록
        judge: (문항, 답) -> 통과 여부. None이면 '답이 비어 있지 않으면 통과'로 봅니다.

    Returns:
        {
          "total": 전체 문항 수,
          "passed": 통과 수,
          "by_type": {유형: {"total": n, "passed": m}},
          "failures": [{"id", "type", "status", "detail"}],
        }

    반드시 지킬 것:
      - answer_fn이 예외를 던져도 전체 실행이 멈추면 안 됩니다.
        그 문항은 status를 ERROR로 기록하고 계속 진행합니다.
    """
    # TODO: 구현하세요.
    # === Delete Begin ===
    # D : raise NotImplementedError("run_eval 을 구현하세요.")
    # === Delete End ===
    # === Insert Begin ===
    # judge 가 없으면 '답이 비어 있지 않으면 통과'하는 기본 판정을 씁니다.
    judge_fn = judge or _default_judge

    total = 0
    passed = 0
    by_type: dict[str, dict[str, int]] = {}
    failures: list[dict] = []

    for item in eval_set or []:
        item_id = item.get("id")
        item_type = item.get("type") or "unknown"
        question = item.get("question", "")

        # 문항을 세는 일은 답을 만들기 "전에" 합니다.
        # 그래야 예외가 난 문항도 total 과 by_type 에서 빠지지 않습니다.
        total += 1
        bucket = by_type.setdefault(item_type, {"total": 0, "passed": 0})
        bucket["total"] += 1

        # 1) 답 만들기 — 여기서 난 예외는 "코드가 터진 것"이라 ERROR 로 남기고 다음 문항으로 갑니다.
        try:
            answer = answer_fn(question)
        except Exception as exc:  # noqa: BLE001 — 어떤 예외든 그 문항 하나만 격리합니다.
            failures.append({
                "id": item_id,
                "type": item_type,
                "status": ERROR,
                "detail": f"answer_fn 예외: {type(exc).__name__}: {exc}",
            })
            continue

        # 2) 판정 — 바깥에서 넣은 judge 가 터져도 평가 전체가 멈추면 안 되므로 똑같이 격리합니다.
        try:
            ok = bool(judge_fn(item, answer))
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "id": item_id,
                "type": item_type,
                "status": ERROR,
                "detail": f"judge 예외: {type(exc).__name__}: {exc}",
            })
            continue

        # 3) 집계 — 통과면 수를 올리고, 틀린 답은 FAIL 로 남깁니다. (터진 코드 ERROR 와 구분)
        if ok:
            passed += 1
            bucket["passed"] += 1
        else:
            failures.append({
                "id": item_id,
                "type": item_type,
                "status": FAIL,
                "detail": f"판정 불통과 (답: {_preview(answer)})",
            })

    return {
        "total": total,
        "passed": passed,
        "by_type": by_type,
        "failures": failures,
    }


def _default_judge(item: dict, answer: Any) -> bool:
    """judge 가 없을 때의 기본 판정: 답이 비어 있지 않으면 통과입니다.

    - None, 빈 문자열, 공백뿐인 문자열, 빈 list/dict 는 '비어 있음'으로 봅니다.
    - Day2 RAG 체인처럼 {"answer": ...} dict 를 돌려주면 answer 값을 기준으로 봅니다.
    - item 인자는 judge 와 모양을 맞추려고 받기만 하고 쓰지 않습니다.
    """
    if isinstance(answer, dict) and "answer" in answer:
        answer = answer["answer"]
    if answer is None:
        return False
    if isinstance(answer, str):
        return bool(answer.strip())
    try:
        return len(answer) > 0
    except TypeError:
        # 길이를 잴 수 없는 값(숫자, True 등)은 값이 있다고 보고 통과시킵니다.
        return True


def _preview(answer: Any, limit: int = 80) -> str:
    """failures 의 detail 에 넣을 답 미리보기입니다. 너무 길면 잘라서 붙입니다."""
    text = repr(answer)
    return text if len(text) <= limit else text[:limit] + "..."
    # === Insert End ===


# ══════════════════════════════════════════════════════════════════
# 심화 파트 (3점) — 못 해도 과제는 통과합니다
# ══════════════════════════════════════════════════════════════════

def compare_eval(before: dict, after: dict) -> dict:
    """개선 전후를 비교합니다. LLM을 호출하지 않습니다.

    통과율 총합만 보면 '무엇이 좋아지고 무엇이 깨졌는지'를 알 수 없습니다.
    한 유형을 고치면 다른 유형이 깨지는 일이 실제로 자주 일어납니다.

    Args:
        before, after: run_eval이 반환한 dict

    Returns:
        {
          "fixed":     [before에서 실패했다가 after에서 통과한 문항 id],
          "regressed": [before에서 통과했다가 after에서 실패한 문항 id],
          "delta": after.passed - before.passed,
          "safe": regressed가 비었으면 True,
        }
    """
    # TODO: 구현하세요.
    # === Delete Begin ===
    # D : raise NotImplementedError("compare_eval 을 구현하세요.")
    # === Delete End ===
    # === Insert Begin ===
    # run_eval 결과에는 "실패한 문항"만 id 로 남고, 통과한 문항 목록은 없습니다.
    # 그래서 같은 평가셋으로 돌린 before/after 라는 전제에서 실패 id 집합의 차이로 비교합니다.
    #   - fixed     : before 실패 목록에 있고 after 실패 목록에는 없음 → 통과로 바뀜
    #   - regressed : before 실패 목록에는 없고 after 실패 목록에 있음 → 통과하다 깨짐
    # FAIL(틀린 답)과 ERROR(터진 코드)는 둘 다 "통과 못 함"이므로 같은 실패로 봅니다.
    before_failed = _failed_ids(before)
    after_failed = _failed_ids(after)

    # 결과 순서가 실행마다 같도록, 원래 실패 목록에 나온 순서를 그대로 유지합니다.
    fixed = [i for i in before_failed if i not in after_failed]
    regressed = [i for i in after_failed if i not in before_failed]

    delta = int((after or {}).get("passed", 0)) - int((before or {}).get("passed", 0))

    return {
        "fixed": fixed,
        "regressed": regressed,
        "delta": delta,
        # 통과 수가 늘었어도(delta > 0) 회귀가 하나라도 있으면 안전하지 않다고 봅니다.
        # 반대로 회귀가 없으면 True — 늘 False 를 내는 게이트는 아무도 읽지 않게 됩니다.
        "safe": not regressed,
    }


def _failed_ids(result: dict) -> list:
    """run_eval 결과에서 실패(FAIL/ERROR) 문항 id 를 중복 없이 나온 순서대로 꺼냅니다."""
    ids: list = []
    for f in (result or {}).get("failures", []) or []:
        item_id = f.get("id")
        if item_id is not None and item_id not in ids:
            ids.append(item_id)
    return ids
    # === Insert End ===
