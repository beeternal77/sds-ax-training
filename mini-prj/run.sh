#!/usr/bin/env bash
# IT 헬프데스크 Agent 실행 스크립트 (mini-prj 폴더에서 실행)
set -euo pipefail
cd "$(dirname "$0")"
pip install -r requirements.txt
uvicorn src.app:app --host 0.0.0.0 --port 8000
