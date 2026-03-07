"""
Pytest 공통 설정.

테스트 실행 위치가 프로젝트 루트(`Lucr-Crawler`)가 아닐 때도
`app` 패키지를 import할 수 있도록 경로를 보정한다.
"""

import sys
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 로거가 상대경로("logs/")를 사용하므로, 어떤 위치에서 pytest를 실행해도
# 프로젝트 루트 기준으로 동일하게 동작하도록 작업 디렉터리를 고정한다.
os.chdir(PROJECT_ROOT)
