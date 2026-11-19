"""RAG 파이프라인 — IT 가이드 문서 검색 (Day 2 패턴).

- 메타데이터(doc_id)는 청킹 **전에** 붙여야 청크에 상속됩니다. (Day 2 학습 포인트)
- 임베딩·벡터DB 생성은 모두 함수 안에서 합니다. 모듈을 import 만 해도 Bedrock 을 부르면 안 되기 때문입니다.
- Day 9 TODO: BM25 하이브리드 검색, 검색 게이트(assess_retrieval) 추가.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs"

EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
REGION = "us-east-1"
PERSIST_DIR = "./chroma_db"
COLLECTION = "sds_policies"


def build_chunks(docs_dir: Path = DOCS_DIR) -> list:
    """문서 폴더의 .md 파일을 읽어 doc_id 메타데이터가 붙은 청크 리스트로 만듭니다."""
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    docs = [
        Document(page_content=p.read_text(encoding="utf-8"), metadata={"doc_id": p.stem, "source": p.name})
        for p in sorted(docs_dir.glob("*.md"))
    ]
    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50,
                                              separators=["\n## ", "\n\n", "\n", " "])
    return splitter.split_documents(docs)


def build_vectorstore(chunks: list, embeddings: Any = None):
    """청크를 Chroma 에 적재합니다. embeddings 를 주입하면 실호출 없이 테스트할 수 있습니다."""
    from langchain_chroma import Chroma

    if embeddings is None:
        from langchain_aws import BedrockEmbeddings
        embeddings = BedrockEmbeddings(model_id=EMBED_MODEL_ID, region_name=REGION)
    return Chroma.from_documents(chunks, embeddings, persist_directory=PERSIST_DIR,
                                 collection_name=COLLECTION)


def build_retriever(vectorstore, k: int = 3):
    """벡터저장소에서 retriever 를 만듭니다."""
    return vectorstore.as_retriever(search_kwargs={"k": k})


def to_contexts(docs: list) -> list[dict]:
    """검색 결과를 API 응답의 contexts 형식({doc_id, text})으로 바꿉니다."""
    return [{"doc_id": d.metadata.get("doc_id", "unknown"), "text": d.page_content} for d in docs]


def make_retrieve_tool(retriever):
    """retriever 를 Agent 가 고를 수 있는 retrieve_docs 도구로 감쌉니다."""
    from langchain_core.tools import tool

    @tool
    def retrieve_docs(query: str) -> list[dict]:
        """사내 IT 가이드 문서(VPN, 계정·비밀번호 정책, SW 설치·라이선스 정책)를 검색한다.
        절차·규칙·정책 질문에 쓰고, 결과의 doc_id 를 답변 출처로 인용한다."""
        return to_contexts(retriever.invoke(query))

    return retrieve_docs
