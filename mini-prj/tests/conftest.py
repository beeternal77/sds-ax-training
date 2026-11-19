"""pytest 공통 설정 — mini-prj 루트를 import 경로에 넣어 `src` 패키지를 불러올 수 있게 합니다."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
