"""Day 8 제출 규격 확인 — 진입점(app.py)과 평가셋(eval_set.json).

실제 LLM·임베딩 API 는 호출하지 않습니다. 앱 객체와 JSON 파일의 형식만 봅니다.
"""

from __future__ import annotations

import json

from evaluation.export_eval_set import OUT_PATH, build

REQUIRED_KEYS = {"id", "question", "type"}


def _items() -> list[dict]:
    return json.loads(OUT_PATH.read_text(encoding="utf-8"))


def test_진입점_app_py_에_POST_query():
    # === Mody Begin ===
    # M :     import app  # mini-prj/app.py
    import app  # miniprj/app.py
    # === Mody End ===

    routes = {(r.path, m) for r in app.app.routes for m in getattr(r, "methods", set())}
    # === Mody Begin ===
    # M :     assert ("/query", "POST") in routes, "mini-prj/app.py 의 app 에 POST /query 가 없습니다."
    assert ("/query", "POST") in routes, "miniprj/app.py 의 app 에 POST /query 가 없습니다."
    # === Mody End ===


def test_평가셋_규격():
    items = _items()
    assert len(items) >= 20, f"{len(items)}문항입니다. 20문항 이상 필요합니다."
    types = [i["type"] for i in items]
    assert types.count("no_answer") >= 2, "no_answer 문항이 2개 이상 필요합니다."
    assert types.count("guardrail") >= 2, "guardrail 문항이 2개 이상 필요합니다."
    for i in items:
        assert REQUIRED_KEYS <= set(i), f"{i.get('id')}: 필수 키 {REQUIRED_KEYS - set(i)} 누락"
    ids = [i["id"] for i in items]
    assert len(set(ids)) == len(ids), "문항 id 가 중복됩니다."


def test_평가셋이_CSV_원본과_일치():
    assert _items() == build(), (
        "eval_set.json 이 test_queries.csv 와 다릅니다. "
        "python evaluation/export_eval_set.py 를 다시 실행하세요."
    )
