#!/usr/bin/env python3
import os, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app import _scan_worker

if __name__ == "__main__":
    _scan_worker()
