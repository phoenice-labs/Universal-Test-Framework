"""
mcp_server/tools/import_results.py — MCP Tool: import_test_results

Imports an existing JUnit XML (e.g. pytest --junit-xml output) into the UTF
registry so that generate_report, feedback_status, and query_registry can use
the real execution results without needing to re-run the tests through UTF.

Workflow:
  1. Run tests your usual way:
       python -m pytest backend/tests/ --junit-xml=utf-tests/reports/results.xml
  2. Import results into UTF registry:
       → call import_test_results with junit_xml_path and project_dir
  3. Generate the UTF contract report:
       → call generate_report with project_dir
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# JUnit XML parser                                                             #
# --------------------------------------------------------------------------- #

def _parse_junit_xml(xml_path: Path) -> list[dict[str, Any]]:
    """
    Parse a JUnit XML file (pytest, Maven, Gradle, Go) into a list of test dicts.

    Returns list of:
        test_id, name, classname, status (passed|failed|error|skipped),
        duration_seconds, failure_message, test_type (inferred)
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    # Handle both <testsuites><testsuite>... and bare <testsuite>...
    suites = root.findall(".//testsuite") if root.tag != "testsuite" else [root]

    results: list[dict[str, Any]] = []
    for suite in suites:
        suite_name = suite.get("name", "")
        for case in suite.findall("testcase"):
            name      = case.get("name", "unknown")
            classname = case.get("classname", suite_name)
            duration  = float(case.get("time", "0") or "0")

            # Determine status
            failure = case.find("failure")
            error   = case.find("error")
            skipped = case.find("skipped")

            if failure is not None:
                status  = "failed"
                message = (failure.get("message") or failure.text or "")[:500]
            elif error is not None:
                status  = "failed"
                message = (error.get("message") or error.text or "")[:500]
            elif skipped is not None:
                status  = "skipped"
                message = skipped.get("message", "")
            else:
                status  = "passed"
                message = ""

            # Build a stable, unique test_id from classname + method name
            test_id = _make_test_id(classname, name)

            results.append({
                "test_id":          test_id,
                "raw_name":         name,
                "classname":        classname,
                "status":           status,
                "duration_seconds": duration,
                "failure_message":  message,
            })

    return results


def _make_test_id(classname: str, method: str) -> str:
    """
    Build a stable TC-EXEC-* test ID that is unique per classname+method.

    Strategy: keep the last 2 segments of classname (e.g. test_module.ClassName)
    plus the full method name, then hash-suffix if still > 80 chars.
    This avoids truncation collisions caused by long module paths sharing prefixes.
    """
    import hashlib as _hashlib
    # Keep last 2 segments: e.g. "backend.tests.mod.TestFoo" → "mod.TestFoo"
    parts = classname.split(".") if classname else []
    cls_short = ".".join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else "")

    safe_cls    = re.sub(r"[^a-zA-Z0-9]+", "_", cls_short).strip("_")
    safe_method = re.sub(r"[^a-zA-Z0-9]+", "_", method).strip("_")
    combined    = f"{safe_cls}_{safe_method}" if safe_cls else safe_method

    if len(combined) > 80:
        # Hash suffix to keep uniqueness while staying readable
        h        = _hashlib.md5(combined.encode()).hexdigest()[:7]
        combined = combined[:72] + "_" + h

    return f"TC-EXEC-{combined}"


# --------------------------------------------------------------------------- #
# Public tool function                                                         #
# --------------------------------------------------------------------------- #

def import_test_results(
    junit_xml_path: str,
    project_dir: Optional[str] = None,
    test_type: str = "e2e",
    language: str = "python",
    framework: str = "pytest",
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Import JUnit XML execution results into the UTF registry.

    After importing, call generate_report (or 'utf report') to get the full
    contract compliance report including execution pass/fail rates.

    Args:
        junit_xml_path: Path to the JUnit XML file produced by pytest / Maven / etc.
                        Absolute or relative to project_dir.
        project_dir:    Absolute path to the caller's project root.
                        Registry stored at <project_dir>/.utf/utf.db.
        test_type:      Test type label (unit|integration|api|e2e|...). Default: e2e
        language:       Language label (python|typescript|...). Default: python
        framework:      Framework label (pytest|jest|...). Default: pytest
        project_id:     Override project name in registry. Defaults to project_dir name.

    Returns:
        imported:   Number of test records upserted
        passed:     Count of passed tests
        failed:     Count of failed tests
        skipped:    Count of skipped tests
        project_id: The project name used in the registry
        registry:   Path to the SQLite registry
        next_step:  Instruction for generating the report
    """
    from mcp_server.registry.registry_engine import get_registry
    from mcp_server.registry.backends.base import TestRecord

    # ── Resolve paths ────────────────────────────────────────────────────────
    cwd = Path(project_dir).resolve() if project_dir else Path.cwd().resolve()
    proj = project_id or cwd.name

    xml_path = Path(junit_xml_path)
    if not xml_path.is_absolute():
        xml_path = cwd / xml_path
    xml_path = xml_path.resolve()

    if not xml_path.exists():
        return {
            "error": f"JUnit XML not found: {xml_path}",
            "imported": 0,
        }

    # ── Parse XML ────────────────────────────────────────────────────────────
    try:
        cases = _parse_junit_xml(xml_path)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}", "imported": 0}

    if not cases:
        return {"error": "No test cases found in XML", "imported": 0}

    # ── Upsert into registry ─────────────────────────────────────────────────
    backend  = get_registry(cwd)
    now      = datetime.now(timezone.utc).isoformat()
    counts   = {"passed": 0, "failed": 0, "skipped": 0}
    imported = 0

    for case in cases:
        status_label = case["status"]         # passed | failed | skipped
        reg_status   = (
            "executed" if status_label == "passed"
            else "failed" if status_label == "failed"
            else "skipped"
        )
        counts[status_label] = counts.get(status_label, 0) + 1

        # Store as JSON so the report builder can extract readable fields
        import json as _json
        content_data = {
            "is_imported":        True,
            "imported_from":      xml_path.name,
            "raw_name":           case["raw_name"],
            "classname":          case["classname"],
            "exec_status_import": status_label,
            "duration_seconds":   case["duration_seconds"],
            "failure_message":    case["failure_message"],
        }

        record = TestRecord(
            test_id=case["test_id"],
            project_id=proj,
            test_type=test_type,
            language=language,
            framework=framework,
            requirement_ids=[],
            score=1.0 if status_label == "passed" else 0.0,
            content=_json.dumps(content_data),
            status=reg_status,
            created_at=now,
            updated_at=now,
        )
        backend.upsert(record)
        imported += 1

    db_path = cwd / ".utf" / "utf.db"

    return {
        "imported":   imported,
        "passed":     counts.get("passed",  0),
        "failed":     counts.get("failed",  0),
        "skipped":    counts.get("skipped", 0),
        "project_id": proj,
        "registry":   str(db_path),
        "xml_parsed": str(xml_path),
        "next_step":  (
            f"Results registered. Now call generate_report(project_dir='{cwd}') "
            "or say 'generate UTF report' to get the full contract compliance report."
        ),
    }
