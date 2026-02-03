#!/usr/bin/env python3
# =============================================================================
# Copyright (c) 2026 5echo.io
# Project: interheart
# Purpose: WebUI discovery worker process (nmap scan and event streaming).
# Path: /webui/discovery_worker.py
# Created: 2026-02-01
# Last modified: 2026-02-02
# =============================================================================

#!/usr/bin/env python3
"""Background worker for network discovery.

This is launched by the WebUI API endpoint /api/discover-start.
It runs discovery in a separate process so the UI stays responsive.
"""

import os
import sys
from pathlib import Path

os.environ["INTERHEART_WORKER"] = "1"
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app import _discover_worker  # noqa: E402


if __name__ == "__main__":
    _discover_worker()
