from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from mcp_server.execution.base import TestRunResult


def format_ci_report(results: list[TestRunResult], project_id: str) -> dict:
    """Format execution results for CI systems (GitHub Actions, GitLab CI, etc.)."""
    total = len(results)
    passed = sum(1 for r in results if r.success)
    failed = total - passed
    return {
        "project_id": project_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_files": total,
            "passed": passed,
            "failed": failed,
            "success_rate": round(passed / total * 100, 1) if total else 0.0,
        },
        "results": [
            {
                "test_file": r.test_file,
                "adapter": r.adapter,
                "passed": r.passed,
                "failed": r.failed,
                "errors": r.errors,
                "duration_seconds": r.duration_seconds,
                "success": r.success,
                "error_details": r.error_details[:5],  # cap at 5
            }
            for r in results
        ],
        "ci_annotations": [
            f"::error file={r.test_file}::{'; '.join(r.error_details[:3])}"
            for r in results
            if not r.success
        ],
    }


def format_junit_xml(results: list[TestRunResult], project_id: str) -> str:
    """Format results as JUnit XML (compatible with GitHub Actions, Jenkins, GitLab)."""
    total_tests = sum(r.passed + r.failed + r.errors + r.skipped for r in results)
    total_failures = sum(r.failed for r in results)
    total_errors = sum(r.errors for r in results)
    total_skipped = sum(r.skipped for r in results)
    total_time = sum(r.duration_seconds for r in results)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<testsuites name="{escape(project_id)}" tests="{total_tests}" '
            f'failures="{total_failures}" errors="{total_errors}" '
            f'skipped="{total_skipped}" time="{round(total_time, 3)}">'
        ),
    ]

    for r in results:
        suite_tests = r.passed + r.failed + r.errors + r.skipped
        suite_name = escape(Path(r.test_file).stem if r.test_file else "unknown")
        lines.append(
            f'  <testsuite name="{suite_name}" tests="{suite_tests}" '
            f'failures="{r.failed}" errors="{r.errors}" skipped="{r.skipped}" '
            f'time="{r.duration_seconds}" file="{escape(r.test_file)}">'
        )

        # Emit individual failure entries for each error_detail
        for detail in r.error_details[:10]:
            case_name = escape(detail[:120])
            lines.append(f'    <testcase name="{case_name}" classname="{suite_name}" time="0">')
            lines.append(f'      <failure message="{case_name}">{escape(detail)}</failure>')
            lines.append('    </testcase>')

        # Emit a synthetic passing testcase if there are passing tests
        if r.passed > 0:
            lines.append(
                f'    <testcase name="[{r.passed} passing tests]" '
                f'classname="{suite_name}" time="{r.duration_seconds}"/>'
            )

        lines.append('  </testsuite>')

    lines.append('</testsuites>')
    return "\n".join(lines)
