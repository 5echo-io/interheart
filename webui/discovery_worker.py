#!/usr/bin/env python3
"""Background worker for network discovery.

This is launched by the WebUI API endpoint /api/discover-start.
It runs discovery in a separate process so the UI stays responsive.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app import _discover_worker  # noqa: E402


if __name__ == "__main__":
    _discover_worker()
