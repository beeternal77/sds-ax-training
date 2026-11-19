"""pytest 공통 설정 — miniprj 루트를 import 경로에 넣어 `src` 패키지를 불러올 수 있게 합니다."""
# === Mody Begin ===
# M : """pytest 공통 설정 — mini-prj 루트를 import 경로에 넣어 `src` 패키지를 불러올 수 있게 합니다."""
# 폴더 이름을 제출 규격(miniprj/)에 맞춰 바꿨습니다. 독스트링 안에는 주석을 넣을 수 없어 원문을 바로 아래에 남깁니다.
# === Mody End ===

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
