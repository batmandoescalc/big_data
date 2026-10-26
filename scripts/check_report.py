#!/usr/bin/env python3
"""Run every local check and explain the result in plain English.

Each week's tests run in their own Python process, as with
``python3 -m unittest discover``, so helper modules from different weeks never
collide. The report says GREEN or RED, what each group of tests checks, and
which checks failed. Under GitHub Actions the same report is also written to
the job summary page, which the pull request's check links to.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

NOT_COVERED = (
    "These checks run on small sample inputs and never contact the university "
    "cluster. They show the code still gives the answers we verified by hand; "
    "they do not show the live cluster is healthy or measure its speed."
)


class RecordingResult(unittest.TestResult):
    """Remember each test's outcome along with its group description."""

    def __init__(self):
        super().__init__()
        self.records = []

    def _record(self, test, status, detail=""):
        method = getattr(test, "_testMethodName", "")
        cls = type(test)
        if cls.__name__ == "_FailedTest":
            group, about = "Loading", "The test file itself could be opened and read."
        else:
            group = cls.__name__
            about = (cls.__doc__ or group).strip().splitlines()[0]
        self.records.append({
            "group": group, "about": about, "test": method,
            "status": status, "detail": detail,
        })

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "pass")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "fail", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "fail", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "skip", reason)


def run_suite(suite_dir, out_path):
    """Child process: run one week's tests and write their outcomes as JSON."""
    tests = unittest.defaultTestLoader.discover(suite_dir)
    result = RecordingResult()
    result.buffer = True  # hide test chatter; failures still keep their output
    tests.run(result)
    Path(out_path).write_text(json.dumps(result.records))


def week_title(week_dir):
    """Return a week's README heading, e.g. 'Week 4: Finding Similar Items'."""
    readme = week_dir / "README.md"
    if readme.exists():
        for line in readme.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return week_dir.name


def readable(method):
    """Turn 'test_empty_set_is_rejected' into 'Empty set is rejected'."""
    words = re.sub(r"^test_", "", method).replace("_", " ")
    return words[:1].upper() + words[1:]


def mark(ok):
    return "✅" if ok else "❌"


def run_weeks():
    """Run each week-*/tests suite and return (title, records) per week."""
    weeks = []
    for suite in sorted(ROOT.glob("week-*/tests")):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.json"
            subprocess.run(
                [sys.executable, __file__, "--suite", str(suite), str(out)],
                cwd=ROOT, stdout=subprocess.DEVNULL, check=False,
            )
            if out.exists():
                records = json.loads(out.read_text())
            else:
                records = [{"group": "Loading", "about": "The tests could start at all.",
                            "test": "test_suite_ran", "status": "fail",
                            "detail": "The test process stopped before reporting."}]
        weeks.append((week_title(suite.parent), records))
    return weeks


def check_shell_syntax():
    """Return (script, ok, detail) for each tracked shell script."""
    listed = subprocess.run(["git", "ls-files", "*.sh"], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    results = []
    for script in listed.stdout.split():
        check = subprocess.run(["bash", "-n", script], cwd=ROOT,
                               capture_output=True, text=True)
        results.append((script, check.returncode == 0, check.stderr.strip()))
    return results


def build_report(weeks, shell):
    """Return the Markdown report and whether everything passed."""
    records = [r for _, week in weeks for r in week]
    ran = [r for r in records if r["status"] != "skip"]
    failed = [r for r in ran if r["status"] == "fail"]
    shell_failed = [s for s in shell if not s[1]]
    green = not failed and not shell_failed

    lines = []
    if green:
        lines += [f"# Test report: GREEN {mark(True)}", "",
                  f"All {len(ran)} tests and all {len(shell)} shell-script checks "
                  "passed. Nothing these checks look at is broken."]
    else:
        broken = []
        if failed:
            broken.append(f"{len(failed)} of {len(ran)} tests")
        if shell_failed:
            broken.append(f"{len(shell_failed)} of {len(shell)} shell-script checks")
        lines += [f"# Test report: RED {mark(False)}", "",
                  f"{' and '.join(broken)} failed. Do not merge until they are "
                  "fixed. The failing checks are marked below."]

    for title, week in weeks:
        week_ran = [r for r in week if r["status"] != "skip"]
        week_ok = sum(r["status"] == "pass" for r in week_ran)
        lines += ["", f"## {title}: {week_ok} of {len(week_ran)} passed "
                      f"{mark(week_ok == len(week_ran))}"]
        groups = {}
        for r in week:
            groups.setdefault(r["group"], []).append(r)
        for group in groups.values():
            group_ran = [r for r in group if r["status"] != "skip"]
            group_ok = sum(r["status"] == "pass" for r in group_ran)
            lines.append(f"- {mark(group_ok == len(group_ran))} {group[0]['about']} "
                         f"({group_ok} of {len(group_ran)})")
            for r in group:
                if r["status"] == "fail":
                    lines.append(f"  - {mark(False)} {readable(r['test'])}")
                elif r["status"] == "skip":
                    lines.append(f"  - Skipped: {readable(r['test'])} ({r['detail']})")

    shell_ok = len(shell) - len(shell_failed)
    lines += ["", f"## Shell scripts: {shell_ok} of {len(shell)} passed "
                  f"{mark(not shell_failed)}",
              "- Each script is read for typos only. None of them is run."]
    lines += [f"  - {mark(False)} {script}" for script, _, _ in shell_failed]

    lines += ["", "## What this does not cover", NOT_COVERED]
    return "\n".join(lines) + "\n", green


def failure_details(weeks, shell):
    """Return the technical error text for every failed check."""
    parts = [f"{r['group']}.{r['test']}\n{r['detail']}"
             for _, week in weeks for r in week if r["status"] == "fail"]
    parts += [f"{script}\n{detail}" for script, ok, detail in shell if not ok]
    return "\n\n".join(parts)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--suite":
        run_suite(sys.argv[2], sys.argv[3])
        return 0

    print(f"Python {sys.version.split()[0]}")
    weeks = run_weeks()
    shell = check_shell_syntax()
    report, green = build_report(weeks, shell)
    details = failure_details(weeks, shell)

    print(report)
    if details:
        print("Error details for whoever fixes it:\n")
        print(details)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report.replace("# Test report",
                                        f"# Test report (Python {sys.version.split()[0]})", 1))
            if details:
                handle.write("\n<details><summary>Error details</summary>\n\n"
                             f"```text\n{details}\n```\n</details>\n")
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
