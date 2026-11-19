"""제출 요건 진입점 — POST /query (miniprj/app.py).

Day 8 제출 규격은 폴더 바로 아래 app.py 를 진입점으로 봅니다.
실제 구현은 src/app.py 에 있고, 이 파일은 그 FastAPI 앱을 그대로 다시 내보내기만 합니다.
(src/app.py 처럼 import 시점에는 Bedrock 을 부르지 않습니다. 문서 적재는 첫 요청 때 합니다.)

실행 (miniprj 폴더에서)
    uvicorn app:app --reload
    python app.py
"""
# === Mody Begin ===
# M : """제출 요건 진입점 — POST /query (mini-prj/app.py).
# M : 실행 (mini-prj 폴더에서)
# 폴더 이름을 제출 규격(miniprj/)에 맞춰 바꿨습니다. 독스트링 안에는 주석을 넣을 수 없어 원문을 바로 아래에 남깁니다.
# === Mody End ===

from __future__ import annotations

from src.app import app  # noqa: F401 — uvicorn 이 찾는 이름이 'app' 입니다

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
