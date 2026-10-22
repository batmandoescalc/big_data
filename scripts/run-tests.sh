#!/usr/bin/env bash
# Run every local check that does not need cluster access.
#
# Usage: bash scripts/run-tests.sh
# Set PYTHON to test with a specific interpreter, e.g. PYTHON=python3.9.
#
# Each week's suite is discovered automatically from week-*/tests, so new
# weeks are included without editing this script. Shell scripts are only
# syntax-checked (bash -n); nothing is executed against the cluster.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python="${PYTHON:-python3}"
echo "Using $("$python" --version 2>&1)"

status=0

for suite in week-*/tests; do
  [ -d "$suite" ] || continue
  echo
  echo "== ${suite%/tests} unit tests"
  if ! "$python" -m unittest discover -s "$suite"; then
    status=1
  fi
done

echo
echo "== shell syntax"
while IFS= read -r script; do
  if bash -n "$script"; then
    echo "ok  $script"
  else
    echo "FAIL $script"
    status=1
  fi
done < <(git ls-files '*.sh')

echo
if [ "$status" -eq 0 ]; then
  echo "All local checks passed."
else
  echo "One or more checks failed."
fi
exit "$status"
