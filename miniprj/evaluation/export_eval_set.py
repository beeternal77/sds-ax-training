"""test_queries.csv → eval_set.json 변환 스크립트 (Day 8 제출 규격).

원본은 evaluation/test_queries.csv 입니다. run_eval.py·테스트·round1~3 측정이 모두 CSV 를 기준으로 하므로
CSV 를 고치고 이 스크립트를 다시 돌려 eval_set.json 을 만듭니다. 둘이 어긋나면
tests/test_submission_format.py 가 실패합니다.

eval_set.json 은 과정 공통 형식(저장소 루트 eval_set.json)을 따릅니다.
    {id, question, type, expected_source?, expected_tools?, expected_blocked?}
여기에 CSV 의 나머지 칸(category, expected_traits, forbidden, note)도 정보 손실 없이 함께 둡니다.

실행 (miniprj 폴더에서)
    python evaluation/export_eval_set.py
"""
# === Mody Begin ===
# M : 실행 (mini-prj 폴더에서)
# 폴더 이름을 제출 규격(miniprj/)에 맞춰 바꿨습니다. 독스트링 안에는 주석을 넣을 수 없어 원문을 바로 아래에 남깁니다.
# === Mody End ===

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.fakes import expected_tools, is_bypass, load_rows  # noqa: E402

OUT_PATH = ROOT / "eval_set.json"
DOC_NAMES = {p.stem for p in (ROOT / "data" / "docs").glob("*.md")}


def to_type(row: dict) -> str:
    """CSV category·expected_tools 를 과정 공통 유형 이름으로 바꿉니다."""
    if row["category"] == "negative":
        return "no_answer"
    if row["category"] == "guardrail":
        return "guardrail"
    tools = expected_tools(row)
    if tools == ["retrieve_docs"]:
        return "fact"
    return "single_tool" if len(tools) == 1 else "multi_tool"


def to_item(row: dict) -> dict:
    item: dict = {"id": f"mp-{int(row['id']):02d}", "question": row["input"], "type": to_type(row)}
    tools = expected_tools(row)
    if row["category"] == "guardrail":
        # 18~20 은 정규식 가드가 막아야 하고(LLM 미호출), 21~22 우회 문항은 가드를 통과하되
        # 결과(타인 데이터·시스템 프롬프트 미노출)가 안전해야 합니다.
        item["expected_blocked"] = not is_bypass(row)
    else:
        item["expected_tools"] = tools
        docs = [d for d in re.findall(r"\(([a-z_]+)\)", row["expected_traits"]) if d in DOC_NAMES]
        if docs:
            item["expected_source"] = f"{docs[0]}.md"
        elif row["category"] == "negative":
            item["expected_source"] = None  # 근거 문서가 없어야 하는 문항 (과정 eval_set 의 no_answer 와 같은 표기)
    item.update({"category": row["category"], "expected_traits": row["expected_traits"],
                 "forbidden": row["forbidden"], "note": row["note"]})
    return item


def build() -> list[dict]:
    return [to_item(r) for r in load_rows()]


def main() -> int:
    items = build()
    OUT_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for i in items:
        counts[i["type"]] = counts.get(i["type"], 0) + 1
    print(f"{len(items)}문항 → {OUT_PATH.name} · 유형별 {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
