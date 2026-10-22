#!/usr/bin/env bash
# Run every local check that does not need cluster access, and explain the
# result in plain English: GREEN or RED, what each group of tests checks, and
# what failed.
#
# Usage: bash scripts/run-tests.sh
# Set PYTHON to test with a specific interpreter, e.g. PYTHON=python3.9.
#
# Each week's suite is discovered automatically from week-*/tests, so new
# weeks are included without editing this script. Shell scripts are only
# syntax-checked (bash -n); nothing is executed against the cluster.
# Exits non-zero if any check fails.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

exec "${PYTHON:-python3}" scripts/check_report.py
