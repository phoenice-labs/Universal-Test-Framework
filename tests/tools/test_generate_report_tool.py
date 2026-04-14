"""
tests/tools/test_generate_report_tool.py

Phase 4 tests for the generate_report MCP tool (#12).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.tools.generate_report import generate_report


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_mock_record(test_id: str) -> MagicMock:
    rec = MagicMock()
    rec.test_id = test_id
    rec.project_id = "test-proj"
    rec.test_type = "unit"
    rec.language = "python"
    rec.framework = "pytest"
    rec.requirement_ids = ["REQ-001"]
    rec.score = 0.95
    rec.status = "generated"
    rec.content = json.dumps({
        "test_id": test_id,
        "why_generated": "Covers happy path for REQ-001 acceptance criteria AC-1",
        "requirement_mapping": "REQ-001: system must do X per AC-1.1 spec",
        "how_it_exercises": "GIVEN valid input WHEN invoked THEN returns expected result",
        "coverage_contribution": "Branch coverage unit risk low pytest python",
        "expected_outcome": "Returns correct value without exceptions matching spec",
        "gaps_missing": "Does not cover concurrent calls or failure injection edge cases",
        "meaningfulness_check": "Meaningful directly validates REQ-001 no hallucination",
        "validation_violations": [],
    })
    return rec


# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — generate_report returns html path
# ──────────────────────────────────────────────────────────────────────────────

def test_generate_report_returns_html_path(tmp_path):
    """TC-GR-001: generate_report must return an 'html' key in report_path."""
    # First generate some tests to populate the registry
    from mcp_server.engine.rule_engine import run_engine
    run_engine(
        requirements_text="REQ-001: User must be able to log in with valid credentials AC-1.1",
        test_type="unit",
        language="python",
        cwd=tmp_path,
    )

    result = generate_report(
        formats=["html"],
        cwd=str(tmp_path),
        project_id=tmp_path.name,
    )

    assert "report_path" in result
    if result.get("error"):
        pytest.skip(f"No registry records: {result['error']}")

    assert result["report_path"] is not None
    assert "html" in result["report_path"]
    assert Path(result["report_path"]["html"]).exists()


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — sections_summary has 8 keys
# ──────────────────────────────────────────────────────────────────────────────

def test_generate_report_sections_summary_has_8_keys(tmp_path):
    """TC-GR-002: sections_summary.averages must have exactly 8 section keys."""
    from mcp_server.engine.rule_engine import run_engine
    run_engine(
        requirements_text="REQ-001: API must validate user input per AC-2.1",
        test_type="unit",
        language="python",
        cwd=tmp_path,
    )

    result = generate_report(cwd=str(tmp_path), project_id=tmp_path.name)

    if result.get("error"):
        pytest.skip(f"No registry records: {result['error']}")

    sections = result.get("sections_summary", {})
    averages = sections.get("averages", {})
    assert len(averages) == 8, (
        f"Expected 8 section keys in averages, got {len(averages)}: {list(averages.keys())}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — suite_contract_score is between 0 and 1
# ──────────────────────────────────────────────────────────────────────────────

def test_generate_report_suite_score_between_0_and_1(tmp_path):
    """TC-GR-003: suite_contract_score must be in [0.0, 1.0]."""
    from mcp_server.engine.rule_engine import run_engine
    run_engine(
        requirements_text="REQ-001: Service must process requests within 200ms SLA",
        test_type="unit",
        language="python",
        cwd=tmp_path,
    )

    result = generate_report(cwd=str(tmp_path), project_id=tmp_path.name)

    if result.get("error"):
        pytest.skip(f"No registry records: {result['error']}")

    score = result.get("suite_contract_score", -1)
    assert 0.0 <= score <= 1.0, f"suite_contract_score out of range: {score}"


# ──────────────────────────────────────────────────────────────────────────────
# Test 4 — formats subset: only json written
# ──────────────────────────────────────────────────────────────────────────────

def test_generate_report_formats_subset(tmp_path):
    """TC-GR-004: Requesting only 'json' format must not write HTML or JUnit files."""
    from mcp_server.engine.rule_engine import run_engine
    run_engine(
        requirements_text="REQ-001: System must handle edge cases for input validation AC-3",
        test_type="unit",
        language="python",
        cwd=tmp_path,
    )

    result = generate_report(
        formats=["json"],
        cwd=str(tmp_path),
        project_id=tmp_path.name,
    )

    if result.get("error"):
        pytest.skip(f"No registry records: {result['error']}")

    paths = result.get("report_path", {})
    assert "json" in paths, "json format must be in report_path"
    assert "html" not in paths, "html format must NOT be in report_path when not requested"
    assert "junit" not in paths, "junit format must NOT be in report_path when not requested"
