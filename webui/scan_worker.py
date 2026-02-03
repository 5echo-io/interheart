#!/usr/bin/env python3
# =============================================================================
# Copyright (c) 2026 5echo.io
# Project: interheart
# Purpose: WebUI scan worker process (runner orchestration and snapshots).
# Path: /webui/scan_worker.py
# Created: 2026-02-01
# Last modified: 2026-02-02
# =============================================================================

#!/usr/bin/env python3
import os
import sys
from pathlib import Path

os.environ["INTERHEART_WORKER"] = "1"
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app import _scan_worker

if __name__ == "__main__":
    _scan_worker()
