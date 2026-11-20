"""채팅 웹 화면 확인 — GET / 가 채팅 화면을 돌려주는지 봅니다.

실제 LLM(Bedrock)은 호출하지 않습니다. 화면 파일을 내려주는 경로만 확인합니다.
"""
from fastapi.testclient import TestClient

import app  # miniprj/app.py — 제출 진입점


def test_root_serves_chat_page():
    client = TestClient(app.app)
    res = client.get("/")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    # 화면이 질문을 POST /query 로 보내도록 배선되어 있는지 확인합니다.
    assert 'fetch("query"' in res.text
    assert 'id="input"' in res.text


def test_query_route_still_exists():
    # 화면을 추가해도 표준 규약 POST /query 는 그대로여야 합니다.
    routes = {(r.path, m) for r in app.app.routes for m in getattr(r, "methods", set())}
    assert ("/query", "POST") in routes
    assert ("/", "GET") in routes
