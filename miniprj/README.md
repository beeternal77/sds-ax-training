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
cd miniprj
pip install -r requirements.txt
uvicorn app:app --reload              # 또는 python app.py / bash run.sh

curl -X POST localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "제 계정 잠겨 있나요?"}'
```

- AWS 자격증명(Bedrock `us-east-1` 접근)이 환경에 설정되어 있어야 합니다.
- 요청자는 시연용 더미 사번 `E100001` 로 고정됩니다. 본문에 `"user_id"` 를 넣으면 바꿀 수 있습니다.

## RAGAS 평가 결과

> **측정하지 않았습니다.** RAGAS는 설계 단계(Seed)에서 합격 판정에 쓰지 않는 **참고 지표**로 정했습니다.
> 합격 판정은 아래 인-아웃 세트 2단 판정으로 합니다. 목표값은 [SERVICE.md](SERVICE.md) 5장에 있습니다(faithfulness 0.85 이상, context_recall 0.80 이상).

| 지표 | 값 |
|---|---|
| context_recall | 미측정 |
| context_precision | 미측정 |
| faithfulness | 미측정 |
| answer_relevancy | 미측정 |

그 대신 문서 근거 문항에서는 응답의 출처 `doc_id`가 검색 결과에 있는지(`doc_id_cited`)를 매 문항 자동으로 검사합니다.
또 심사자(LLM-as-Judge)가 도구 결과를 근거로 받아 "근거 없는 단정"을 위반으로 판정합니다.

## 인-아웃 세트 통과율 (자체 평가)

> 인-아웃 세트 22건: positive 8 · negative 4 · edge 5 · guardrail 5 (우회 문항 2건 포함)

```bash
python -m pytest tests -q                      # 1단계: 가짜 모델 배선 테스트 (실제 LLM 호출 없음)
python evaluation/run_eval.py --runs 3         # 2단계: 실제 Bedrock 3회 → evaluation/results/run_{n}.json
python evaluation/run_eval.py --fake --runs 1  # 채점 스크립트 자체 점검 (점수 의미 없음)
```

- 가짜 모델 테스트는 "배선"만 검증합니다. 도구 호출 순서와 답 문장은 대본([tests/fakes.py](tests/fakes.py))이 정합니다. 모델이 경로를 스스로 잘 고르는지는 2단계 실제 실행에서만 확인됩니다.
- 합격 기준은 [SERVICE.md](SERVICE.md) 5장을 따릅니다. 3회 모두 guardrail 5/5와 지어낸 답변 0건을 지키고, 3회 중 2회 이상 18/22를 넘어야 합니다.

실제 Bedrock 3회 측정 결과입니다. 모델은 `global.anthropic.claude-sonnet-4-5-20250929-v1:0`, temperature 0입니다.

| 라운드 | 바꾼 것 | 회차별 통과 | guardrail | 지어낸 답변 | 판정 |
|:-:|---|:-:|:-:|:-:|:-:|
| 1차 | 기준선 | 18 / 17 / 17 | 5/5 ×3 | 1 / 1 / 1 | 불합격 |
| 2차 | 날짜 주입 · 범위 밖 안내 · 문서 검색과 해제 조건 | 20 / 21 / 20 | 5/5 ×3 | 0 / 0 / 0 | 합격 |
| 3차 | 명시적 해제 요청 즉시 접수 | 22 / 22 / 22 | 5/5 ×3 | 0 / 0 / 0 | 합격 |
| 최종 | 심사자 보강 (도구 결과·오늘 날짜를 근거로 전달) | **22 / 22 / 22** | 5/5 ×3 | 0 / 0 / 0 | **합격** |

- **개선폭:** 회차 평균 17.3 → 22건(+4.7건), 지어낸 답변 매회 1건 → 0건.
- **주요 개선:** 오늘 날짜 주입(id 15), 범위 밖 질문의 "찾지 못함 + #it-helpdesk" 안내(id 9), 절차가 섞인 질문의 문서 검색·출처 인용(id 3·13), 요청 없는 잠금 해제 접수 금지(id 13·16)와 명시적 요청 즉시 접수(id 8).
- **리포트:**
  - [evaluation/round1_report.md](evaluation/round1_report.md): 기준선과 실패 분석
  - [evaluation/round2_report.md](evaluation/round2_report.md): 개선 1~3
  - [evaluation/round3_report.md](evaluation/round3_report.md): 개선 4, 심사자 보강
- **측정 원본:** `evaluation/results/`. 최종 기록은 `results/judge_v2/runs3/`입니다.

## 트라이앤에러 회고

### 시도했지만 실패한 접근 · 왜 실패했는가

- **규칙 4에 두 경우를 한 문장으로 섞은 프롬프트**
  - 개선 3에서 "잠금 해제는 명시적 요청일 때만, 방법만 물으면 요청하라고 안내"를 한 덩어리로 썼습니다.
  - 그러자 "계정 잠금 풀어주세요"에도 모델이 "접수해 드릴까요?"라고 되물었습니다(id 8, 3회 모두 실패).
  - 한 문제(요청 없는 접수)를 막으려던 문장이 정상 경로까지 막은 부작용이었습니다.
- **근거 없이 판정하는 심사자**
  - 처음 심사자는 질문·응답·금지 항목만 봤습니다. 그래서 도구가 돌려준 실제 만료일 "2026-11-30"을 "추측"으로 오판했습니다(id 15, 3회 중 2회).
  - 도구 결과만 넘기자 이번에는 "이번 달"이라는 판단을 근거 없는 단정으로 보고 5회 모두 위반으로 판정했습니다.
  - 심사자도 Agent와 같은 정보(오늘 날짜)를 가져야 공정하게 판정할 수 있었습니다.
- **한 번에 하나씩 고쳐 측정하려던 계획**
  - 일일 토큰 한도(`Too many tokens per day`)에 걸려 개선 1·2를 따로 3회씩 측정하지 못했습니다.
  - 결국 개선 1~3을 함께 측정했습니다.

### 최종 채택한 접근 · 왜 그것으로 갔는가

- **규칙 4를 두 문장으로 분리했습니다.** 명시적 요청은 바로 승인 요청을 접수하고, 상태·방법 질문은 안내만 합니다. 두 경우를 나누니 id 8은 고쳐지고 id 13·16은 회귀하지 않았습니다.
- **심사자에게 도구 결과와 오늘 날짜를 근거로 넘겼습니다.**
  - 정답 답변은 5/5 통과했고, 만료일을 바꾼 함정 답변은 2/2 위반으로 잡았습니다.
  - 판정은 느슨해지지 않고 오판만 사라졌습니다.
  - 판정 이유(`judge_reason`)를 결과에 남겨 다음 오판을 바로 추적할 수 있게 했습니다.
- **평가 스크립트에 인프라 오류 무효 처리를 넣었습니다.**
  - API·네트워크 오류가 난 회차는 점수에 넣지 않고 다시 시도합니다.
  - 일일 한도 초과는 재시도 없이 멈추고 진행 위치를 출력합니다.
  - 덕분에 측정 도중 연결 오류가 나도 잘못된 점수가 남지 않았습니다.

### 남은 한계 · 향후 개선 방향

- **미들웨어는 부분 구현입니다.**
  - 차단·마스킹·trace 기능은 있지만 미들웨어 구조로 나뉘어 있지 않습니다.
  - PII 마스킹은 기록 직전에만 해서, 질문 속 PII 원문은 모델에 전달됩니다.
  - 출력 검사 단계와 trace 파일 기록은 Day 9 TODO입니다.
- **HITL 승인은 접수까지만 합니다.** `unlock_account` 직전에 `interrupt()`로 멈추는 실제 승인 노드는 아직 없습니다.
- **요청자 신원은 `user_id`를 그대로 믿습니다.** SSO 연동이 없는 데모 한계입니다.
- **RAGAS는 측정하지 않았습니다.** 참고 지표라 합격 판정에 쓰지 않았습니다.

## 핵심 코드 위치

- [src/agent.py](src/agent.py) — 메인 에이전트 그래프 (`build_agent`, `answer`)
- [src/tools.py](src/tools.py) — 도메인 도구 (`make_tools`)
- [src/retriever.py](src/retriever.py) — RAG 파이프라인
- [src/guardrails.py](src/guardrails.py) — 입력 가드 · PII 마스킹
- [app.py](app.py) — `POST /query` 제출 진입점 (`src/app.py` 의 앱을 다시 내보냄)
- [src/app.py](src/app.py) — FastAPI 앱 구현
- [eval_set.json](eval_set.json) — 제출 평가셋 22문항 (no_answer 4 · guardrail 5)
- [evaluation/export_eval_set.py](evaluation/export_eval_set.py) — `test_queries.csv` → `eval_set.json` 변환
