#!/usr/bin/env python3
"""Compatibility entry point for the shared benchmark recorder."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from common.benchmark.run_timed import main, timed_run  # noqa: E402,F401


if __name__ == "__main__":
    main()
