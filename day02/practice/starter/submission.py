"""Day 2 — 런북 RAG와 평가셋.

문서를 인덱싱하고, 질문에 근거와 함께 답합니다.

[중요] 이 파일의 규칙
  1. 함수 이름과 인자를 바꾸지 마세요.
  2. 모델·임베딩은 반드시 함수 **안에서** 만듭니다.
  3. `llm` 인자가 들어오면 그것을 씁니다. 채점기가 가짜 모델을 넣습니다.
  4. `build_retriever`와 `build_rag_chain`은 **주어진 vectorstore/retriever를 그대로 씁니다.**
     함수 안에서 새로 인덱싱하지 마세요.
"""

from __future__ import annotations

import re
from typing import Any

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
REGION = "us-east-1"

PERSIST_DIR = "./chroma_db"
COLLECTION = "sds_policies"


def _default_llm():
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(model=MODEL_ID, region_name=REGION, temperature=0)


def _default_embeddings():
    from langchain_aws import BedrockEmbeddings

    return BedrockEmbeddings(model_id=EMBED_MODEL_ID, region_name=REGION)


def get_text(message: Any) -> str:
    """ChatBedrockConverse는 content를 블록 리스트로 주기도 하므로 텍스트만 모아 반환합니다."""
    content = message.content if hasattr(message, "content") else message
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content)


def format_docs(docs) -> str:
    """검색된 문서를 프롬프트에 넣을 문자열로 만듭니다."""
    return "\n\n".join(
        f"[출처: {d.metadata.get('source', '알 수 없음')}]\n{d.page_content}" for d in docs
    )


# ══════════════════════════════════════════════════════════════════
# 기초 파트 (7점)
# ══════════════════════════════════════════════════════════════════

def build_chunks(doc_paths: list[str]) -> list:
    """문서를 읽어 청크 Document 리스트를 만듭니다.

    반드시 지킬 것:
      - 모든 청크 metadata에 source / department / updated_at 세 키가 있어야 합니다.
      - 메타데이터는 **분할하기 전에** 붙여야 상속됩니다.
      - 고정 길이로 자르지 말고 RecursiveCharacterTextSplitter 또는
        MarkdownHeaderTextSplitter를 쓰세요.

    Args:
        doc_paths: 읽을 마크다운 파일 경로 목록

    Returns:
        langchain_core.documents.Document 의 리스트
    """
    from datetime import date
    from pathlib import Path

    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # ── 1) 파일을 읽어 "분할 전" 원본 Document를 만들고 메타데이터 3키를 붙입니다.
    #    split_documents()는 원본 Document의 metadata를 각 청크로 복사하므로,
    #    여기서 붙여 두면 모든 청크가 같은 source/department/updated_at을 갖게 됩니다.
    #    (분할한 뒤에 붙이면 빠뜨린 청크가 생겨도 오류가 나지 않아 알아채기 어렵습니다.)
    originals: list[Document] = []
    for raw_path in doc_paths:
        path = Path(raw_path)
        text = path.read_text(encoding="utf-8")
        known = DOC_META.get(path.name, {})

        # updated_at: 문서 관리 대장(DOC_META)에 있으면 그 값을, 없으면
        #             파일 최종 수정 시각을 YYYY-MM-DD로 바꿔 씁니다.
        updated_at = known.get("updated_at") or date.fromtimestamp(
            path.stat().st_mtime
        ).isoformat()

        originals.append(
            Document(
                page_content=text,
                metadata={
                    "source": path.name,  # 원본 파일명 (경로가 아니라 이름만)
                    "department": known.get("department", "미지정"),
                    "updated_at": updated_at,
                },
            )
        )

    # ── 2) 마크다운 구조를 존중하는 재귀 분할기로 자릅니다.
    #    - separators: "## 섹션" 경계 → 문단 → 줄 → 단어 순으로 먼저 끊어 봅니다.
    #      그래서 한 섹션(예: '## 3. 롤백 기준')이 가능하면 한 청크에 통째로 남습니다.
    #    - chunk_size=400: 실습 문서가 740~921자라 문서당 2~4개 청크가 나옵니다.
    #      800을 넘기면 문서 하나가 통째로 한 청크가 되어 검색 변별력이 떨어집니다.
    #    - chunk_overlap=50: 섹션 경계에 걸친 문장이 양쪽 청크에서 끊기지 않도록 약간 겹칩니다.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        separators=["\n## ", "\n\n", "\n", " ", ""],
    )
    return splitter.split_documents(originals)


# 문서 관리 대장 — 파일명별 담당 조직과 최종 개정일 (교육용 더미 데이터입니다).
# 실습 문서 본문에는 담당 조직·개정일이 적혀 있지 않으므로 여기서 관리합니다.
DOC_META: dict[str, dict[str, str]] = {
    "leave_policy.md": {"department": "people", "updated_at": "2026-03-02"},
    "oncall_policy.md": {"department": "sre", "updated_at": "2026-06-30"},
    # 개정일이 관리되지 않는 문서는 파일 수정 시각으로 대체합니다.
    "incident_runbook.md": {"department": "sre"},
}


def build_retriever(vectorstore):
    """주어진 벡터저장소에서 retriever를 만듭니다.

    여기서 새로 인덱싱하지 마세요. 인자로 받은 vectorstore를 그대로 씁니다.
    k 값은 직접 정하고, 왜 그 값인지 주석으로 남기세요.
    """
    # k=4 를 고른 이유:
    #   - 청크가 문서당 2~4개, 전체 10개 안팎입니다. 정답이 한 섹션에 있더라도
    #     overlap 때문에 이웃 청크에 나뉘어 있을 수 있어 1~2개로는 놓칠 위험이 큽니다.
    #   - 반대로 6개 이상이면 전체의 절반 이상을 넣는 셈이라 무관한 런북
    #     (예: 롤백 질문에 온콜 규정)이 컨텍스트를 채워 모델이 끌려갑니다.
    #   - 4개면 "정답 문서의 대부분 + 다른 문서 1~2개" 정도라 재현율과 잡음의 균형이 맞습니다.
    return vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 4})


def build_rag_chain(retriever, llm=None):
    """질문 문자열을 받아 {"answer": str, "sources": list[str]} 를 반환하는 체인을 만듭니다.

    반드시 지킬 것:
      - 검색된 문서 본문을 프롬프트에 실제로 넣어야 합니다.
      - sources는 실제 검색 결과의 metadata에서 뽑습니다. 지어내면 안 됩니다.

    심화 파트를 구현했다면 assess_retrieval 판정을 거쳐야 합니다.
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    llm = llm or _default_llm()

    # 근거 문서 밖의 내용으로 답하지 않도록 시스템 프롬프트에서 규칙을 못 박습니다.
    # 문서 본문은 {context} 변수로 들어갑니다. 변수 "값"에 들어간 중괄호는
    # 템플릿 문법으로 해석되지 않으므로 특수문자 질문도 안전합니다.
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 사내 규정·런북 안내 도우미입니다.\n"
                "아래 [근거 문서]에 적힌 내용만 사용해 한국어로 간결하게 답하세요.\n"
                "근거 문서에 답이 없으면 추측하지 말고 정확히 "
                f"\"{NO_ANSWER['answer']}\" 라고만 답하세요.\n\n"
                "[근거 문서]\n{context}",
            ),
            ("human", "{question}"),
        ]
    )

    def _run(inputs: Any) -> dict:
        # 질문은 문자열이 기본이지만 {"question": ...} 형태로 들어와도 받아 줍니다.
        if isinstance(inputs, dict):
            question = str(inputs.get("question", ""))
        else:
            question = "" if inputs is None else str(inputs)

        # 1) 검색 — 주어진 retriever를 그대로 씁니다. (여기서 새로 인덱싱하지 않습니다)
        docs = list(retriever.invoke(question) or [])

        # 2) 게이트 — 검색 결과가 쓸 만하지 않으면 모델을 부르지 않고 바로 거절합니다.
        verdict = assess_retrieval(docs, question)
        if not verdict["usable"]:
            return {"answer": NO_ANSWER["answer"], "sources": []}

        # 3) 생성 — 검색된 본문을 실제로 프롬프트에 주입해 모델을 호출합니다.
        messages = prompt.invoke({"context": format_docs(docs), "question": question})
        answer = get_text(llm.invoke(messages)).strip()

        # 4) 출처 — 지어내지 않고 실제 검색 결과의 metadata에서만 뽑습니다.
        #    순서는 검색 순위를 유지하고 중복은 제거합니다.
        #    모델이 스스로 "찾을 수 없다"고 답했다면 근거가 없는 것이므로 비웁니다.
        if "찾을 수 없" in answer:
            return {"answer": answer, "sources": []}
        sources = list(
            dict.fromkeys(d.metadata["source"] for d in docs if d.metadata.get("source"))
        )
        return {"answer": answer, "sources": sources}

    return RunnableLambda(_run)


# ══════════════════════════════════════════════════════════════════
# 심화 파트 (3점) — 못 해도 과제는 통과합니다
# ══════════════════════════════════════════════════════════════════

def assess_retrieval(docs, question: str) -> dict:
    """검색 결과가 이 질문에 답하기에 쓸만한지 판정합니다.

    이 함수는 LLM을 호출하지 않습니다. 같은 입력에 항상 같은 출력을 내야 합니다.

    판정 방법은 자유입니다. 예를 들면
      - 질문에서 핵심어를 뽑아 문서 본문에 몇 개나 등장하는지 센다
      - 검색된 문서 개수와 길이를 본다
      - 특정 임계값을 넘는지 확인한다

    Returns:
        {"usable": bool, "reason": str, "matched": int} 형태의 dict.
        usable이 False면 build_rag_chain은 모델을 부르지 않고 거절해야 합니다.
    """
    # 빈 검색 결과 — 근거가 없으니 볼 것도 없이 거절합니다.
    if not docs:
        return {"usable": False, "reason": "검색 결과가 없음", "matched": 0}

    keywords = _extract_keywords(question)
    if not keywords:
        return {"usable": False, "reason": "질문에서 핵심어를 뽑지 못함", "matched": 0}

    # 공백을 지운 본문에서도 찾아 "인수 인계" / "인수인계" 같은 띄어쓰기 차이를 흡수합니다.
    body = " ".join(getattr(d, "page_content", "") or "" for d in docs)
    body_nospace = re.sub(r"\s+", "", body)
    matched_words = [k for k in keywords if k in body or k in body_nospace]
    matched = len(matched_words)

    # 판정 기준: 핵심어의 1/3 이상이 본문에 등장해야 쓸 만하다고 봅니다.
    #   - 너무 엄격하면(예: 절반 이상) "남은 휴가를 내년에…" 같은 바꿔 말한 질문이
    #     본문 단어와 덜 겹쳐 정상 질문까지 거절합니다.
    #   - 이 게이트를 통과한 뒤에도 프롬프트가 "근거 없으면 찾을 수 없다고 답하라"고
    #     한 번 더 막으므로, 게이트는 '명백히 무관한 검색'을 끊는 1차 방어선 역할입니다.
    usable = matched >= 1 and matched * 3 >= len(keywords)
    reason = f"질의어 {len(keywords)}개 중 {matched}개가 본문에 등장"
    if matched_words:
        reason += f" ({', '.join(matched_words)})"
    return {"usable": usable, "reason": reason, "matched": matched}


# 조사·어미 — 핵심어 끝에서 떼어 냅니다. 긴 것부터 시도해야 "으로"가 "로"보다 먼저 걸립니다.
_SUFFIXES = sorted(
    [
        "되나요", "하나요", "인가요", "있나요", "없나요", "할까요", "되요", "돼요", "나요",
        # 동사 활용 — "배포했는데"→"배포", "호출받아"→"호출" 처럼 어간을 살립니다.
        "했는데", "하는데", "했어요", "해요", "하면", "되면", "해도", "되도", "돼도",
        "받아", "받고", "하고", "했고", "한", "할", "된", "될",
        "에서는", "에서", "으로", "까지", "부터", "에게", "한테", "이나", "이랑", "하고",
        "은", "는", "이", "가", "을", "를", "에", "의", "도", "로", "와", "과", "만",
    ],
    key=len,
    reverse=True,
)
# 어느 문서에나 나올 법해 판정에 도움이 안 되는 말은 핵심어에서 뺍니다.
_STOPWORDS = {
    "어떻게", "어떤", "무엇", "뭐", "언제", "어디", "누가", "왜", "얼마나", "몇",
    "되나요", "하나요", "있나요", "없나요", "인가요", "알려주세요", "궁금합니다",
    "수", "것", "때", "좀", "그", "이", "저",
}


def _extract_keywords(question: str) -> list[str]:
    """질문에서 핵심어를 뽑습니다. 규칙 기반이라 같은 입력엔 항상 같은 결과가 나옵니다."""
    words = re.findall(r"[0-9A-Za-z가-힣]+", question or "")
    out: list[str] = []
    for w in words:
        if w in _STOPWORDS:
            continue
        stem = w
        for suf in _SUFFIXES:
            # 떼고 남은 말이 두 글자 이상일 때만 뗍니다. ("시간이"→"시간", "남은"은 유지)
            if stem.endswith(suf) and len(stem) - len(suf) >= 2:
                stem = stem[: -len(suf)]
                break
        # 한 글자 단어는 우연히 겹치기 쉬워 제외합니다.
        if len(stem) >= 2 and stem not in _STOPWORDS and stem not in out:
            out.append(stem)
    return out


NO_ANSWER = {
    "answer": "제공된 문서에서 답을 찾을 수 없습니다.",
    "sources": [],
}
