# 미니 PJT: IT 헬프데스크 1차 응대 Agent

> 문서·사번·자산 데이터는 모두 **교육용 더미 데이터입니다.**
> 서비스 스펙은 [SERVICE.md](SERVICE.md), 평가셋은 [eval_set.json](eval_set.json) (제출 규격, 22문항)에 있습니다.
> 평가셋 원본은 [evaluation/test_queries.csv](evaluation/test_queries.csv) 이고, `python evaluation/export_eval_set.py` 로 `eval_set.json` 을 만듭니다.

## 무엇을 푸나

정해진 답이 있는 반복 IT 문의("VPN 안 붙어요", "계정 잠겼어요")를 헬프데스크 담당자 대신 1차로 처리하고, 승인이 필요한 건만 사람에게 넘깁니다.

## 활용한 패턴 (Day 1~7)

| # | 패턴 | Day | 어떻게 활용 | 상태 |
|:-:|---|:-:|---|:-:|
| 1 | LCEL chain · 구조화 출력 | 1 | API 응답을 `{answer, contexts, trace}` 스키마로 고정 | 뼈대 |
| 2 | ReAct (도구 자율 선택) | 3 | `bind_tools` 로 5개 도구 결합, `MAX_TOOL_CALLS` 로 순환 탈출 | 구현 |
| 3 | RAG | 2 | IT 가이드 3종을 `retrieve_docs` 로 검색, `doc_id` 출처 인용 | 구현 |
| 4 | 도구 다중 | 4 | 자산 조회 → 라이선스 조회 연쇄, 도구는 예외 대신 문장 반환 | 구현 |
| 6 | 가드레일 | 5 | 입력 단계 프롬프트 인젝션·자격증명 요구·승인 우회 차단 | 뼈대 |
| 7 | HITL (위험 작업 승인) | 5 | `unlock_account` 는 승인 요청 접수만, 해제는 승인 후 | 뼈대 |
| 8 | 미들웨어 (PII 마스킹) | 5 | trace·응답 기록 전 전화번호·이메일·주민번호 마스킹. 미들웨어 구조·출력 검사는 Day 9 TODO | 부분 구현 |
| 11 | Observability · Trace | 7 | 요청마다 단계별 trace 를 응답에 포함 | 구현 |
| 12 | 평가 (RAGAS · LLM-as-Judge) | 7 | 인-아웃 세트 22건 2단 판정(가짜 모델 pytest + Bedrock 3회), 라운드별 리포트 | 뼈대 |

## 아키텍처

```
POST /query {"question"}
   │
   ▼
[guard] 입력 가드 · 본인 외 조회 감지 ──차단──▶ 정중한 거절 (LLM 호출 없음)
   │ pass
   ▼
[agent] ReAct (Claude Sonnet 4.5 on Bedrock) ◀──┐
   │ tool_calls                                  │
   ▼                                             │
[tools] retrieve_docs · get_my_account ──────────┘
        get_my_assets → check_license (연쇄)
        unlock_account (승인 요청만 접수)
   │
   ▼
PII 마스킹 → {answer, contexts, trace}
```

### 핵심 설계 결정

1. **요청자 사번을 도구 인자에서 뺐습니다.** `make_tools(user_id)` 가 사번을 도구 안에 미리 묶습니다. 모델은 다른 사람 사번을 넣을 방법 자체가 없습니다. 프롬프트로 "남의 정보는 조회하지 마"라고 부탁하는 대신 구조로 막았습니다.
2. **가드 차단 시 모델을 부르지 않습니다.** 규칙 가드가 먼저 막으면 비용이 0이고 결과가 결정적입니다. 그래서 guardrail 케이스는 매번 같은 결과가 나옵니다.

## 실행 방법

```bash
cd mini-prj
pip install -r requirements.txt
uvicorn app:app --reload              # 또는 python app.py / bash run.sh

curl -X POST localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "제 계정 잠겨 있나요?"}'
```

- AWS 자격증명(Bedrock `us-east-1` 접근)이 환경에 설정되어 있어야 합니다.
- 요청자는 시연용 더미 사번 `E100001` 로 고정됩니다. 본문에 `"user_id"` 를 넣으면 바꿀 수 있습니다.

## RAGAS 평가 결과

> Day 9 측정 후 기입합니다.

- context_recall: 0.XX
- context_precision: 0.XX
- faithfulness: 0.XX
- answer_relevancy: 0.XX

## 인-아웃 세트 통과율 (자체 평가)

> 인-아웃 세트 22건: positive 8 · negative 4 · edge 5 · guardrail 5 (우회 문항 2건 포함)

```bash
python -m pytest tests -q                      # 1단계: 가짜 모델 배선 테스트 (실제 LLM 호출 없음)
python evaluation/run_eval.py --runs 3         # 2단계: 실제 Bedrock 3회 → evaluation/results/run_{n}.json
python evaluation/run_eval.py --fake --runs 1  # 채점 스크립트 자체 점검 (점수 의미 없음)
```

- 가짜 모델 테스트는 "배선"만 검증합니다. 도구 호출 순서와 답 문장은 대본([tests/fakes.py](tests/fakes.py))이 정합니다. 모델이 경로를 스스로 잘 고르는지는 2단계 실제 실행에서만 확인됩니다.
- 합격 기준은 [SERVICE.md](SERVICE.md) 5장을 따릅니다. 3회 모두 guardrail 5/5와 지어낸 답변 0건을 지키고, 3회 중 2회 이상 18/22를 넘어야 합니다.

- 1차 (Day 9 종료): XX / 22 통과 → [evaluation/round1_report.md](evaluation/round1_report.md)
- 2차 (Day 10 개선 후): XX / 22 통과 → [evaluation/round2_report.md](evaluation/round2_report.md)
- 개선폭: +XX 건 (주요 개선 사항: ...)

## 트라이앤에러 회고

> Day 10 에 작성합니다.

- 시도했지만 실패한 접근 · 왜 실패했는가
- 최종 채택한 접근 · 왜 그것으로 갔는가
- 남은 한계 · 향후 개선 방향

## 핵심 코드 위치

- [src/agent.py](src/agent.py) — 메인 에이전트 그래프 (`build_agent`, `answer`)
- [src/tools.py](src/tools.py) — 도메인 도구 (`make_tools`)
- [src/retriever.py](src/retriever.py) — RAG 파이프라인
- [src/guardrails.py](src/guardrails.py) — 입력 가드 · PII 마스킹
- [app.py](app.py) — `POST /query` 제출 진입점 (`src/app.py` 의 앱을 다시 내보냄)
- [src/app.py](src/app.py) — FastAPI 앱 구현
- [eval_set.json](eval_set.json) — 제출 평가셋 22문항 (no_answer 4 · guardrail 5)
- [evaluation/export_eval_set.py](evaluation/export_eval_set.py) — `test_queries.csv` → `eval_set.json` 변환
