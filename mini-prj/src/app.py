"""API 진입점 — POST /query (미니 PJT 표준 규약).

요청:  {"question": "사용자 질의"}            (선택: "user_id", 없으면 시연용 더미 사번)
응답:  {"answer": ..., "contexts": [{doc_id, text}], "trace": [{step, input, output}]}

실행:  uvicorn src.app:app --reload   (mini-prj 폴더에서)
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel

from .agent import DEMO_USER_ID, answer

app = FastAPI(title="IT 헬프데스크 1차 응대 Agent")


class QueryRequest(BaseModel):
    question: str
    user_id: str = DEMO_USER_ID


class QueryResponse(BaseModel):
    answer: str
    contexts: list[dict]
    trace: list[dict]


@lru_cache(maxsize=1)
def _retriever():
    """첫 요청 때 한 번만 문서를 적재합니다. (서버 import 시점에 Bedrock 을 부르지 않기 위해)"""
    from .retriever import build_chunks, build_retriever, build_vectorstore
    return build_retriever(build_vectorstore(build_chunks()))


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> dict:
    return answer(req.question, user_id=req.user_id, retriever=_retriever())
