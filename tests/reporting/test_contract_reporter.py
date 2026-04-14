"""
tests/reporting/test_contract_reporter.py

Phase 1 tests for the ContractReporter module and report_writer.
Verifies HTML, JUnit, JSON output and file rotation.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_server.reporting.contract_reporter import ContractReporter, _SECTION_KEYS, _SECTION_META


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

def _make_test(test_id: str, score: float = 0.95) -> MagicMock:
    """Create a minimal GeneratedTest-compatible mock."""
    t = MagicMock()
    t.test_id = test_id
    t.why_generated = f"Covers the happy-path for {test_id} to validate core behaviour"
    t.requirement_mapping = f"REQ-001: {test_id} must satisfy acceptance criteria AC-1.1"
    t.how_it_exercises = (
        "GIVEN the system is initialized with valid input. "
        "WHEN the function is invoked. THEN the expected result is returned."
    )
    t.coverage_contribution = f"Branch coverage for {test_id} — happy path. Test type: unit. Risk: low."
    t.expected_outcome = "Returns expected value without raising exceptions and matches spec."
    t.gaps_missing = f"Does not test concurrent access for {test_id}. Additional edge cases pending."
    t.meaningfulness_check = f"Meaningful — directly validates REQ-001 via happy_path scenario. No hallucination."
    t.rendered_code = f"def test_{test_id.lower().replace('-', '_')}(): pass"
    t.validation_score = score
    t.validation_passed = score >= 0.85
    t.validation_violations = []
    return t


def _make_engine_output(n_tests: int = 3) -> MagicMock:
    """Create a minimal EngineOutput-compatible mock."""
    out = MagicMock()
    out.tests = [_make_test(f"TC-REQ-{i:03d}", 0.95) for i in range(1, n_tests + 1)]
    out.blocked_tests = []
    out.detected_language = "python"
    out.detected_framework = "pytest"
    out.coverage_summary = {"test_type": "unit"}
    out.suite_contract_score = 0.95
    out.blocked_count = 0
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — HTML report contains all 8 section names
# ──────────────────────────────────────────────────────────────────────────────

def test_html_report_has_all_8_sections():
    """TC-REP-001: HTML output must reference all 8 section names."""
    output = _make_engine_output(n_tests=2)
    reporter = ContractReporter(output)
    html = reporter.to_html()

    for meta in _SECTION_META:
        assert meta["name"] in html, f"Section '{meta['name']}' missing from HTML report"

    # KPI elements must be present
    assert "Suite Contract Score" in html
    assert "Tests Generated" in html
    assert "Blocked (Contract)" in html


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — JUnit XML has utf.contract_score property
# ──────────────────────────────────────────────────────────────────────────────

def test_junit_xml_has_contract_score_property():
    """TC-REP-002: JUnit XML must include utf.contract_score property on each testcase."""
    output = _make_engine_output(n_tests=2)
    reporter = ContractReporter(output)
    xml_str = reporter.to_junit_xml()

    root = ET.fromstring(xml_str)
    testcases = root.findall(".//testcase")
    assert len(testcases) == 2, f"Expected 2 testcases, got {len(testcases)}"

    for tc in testcases:
        props = {p.get("name"): p.get("value") for p in tc.findall(".//property")}
        assert "utf.contract_score" in props, (
            f"utf.contract_score property missing from testcase {tc.get('name')}"
        )
        score = float(props["utf.contract_score"])
        assert 0.0 <= score <= 1.0


# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — JUnit XML has all 8 section properties
# ──────────────────────────────────────────────────────────────────────────────

def test_junit_xml_has_all_8_section_properties():
    """TC-REP-003: Each testcase in JUnit XML must have all 8 utf.section.* properties."""
    output = _make_engine_output(n_tests=1)
    reporter = ContractReporter(output)
    xml_str = reporter.to_junit_xml()

    root = ET.fromstring(xml_str)
    tc = root.find(".//testcase")
    assert tc is not None
    props = {p.get("name"): p.get("value") for p in tc.findall(".//property")}

    for key in _SECTION_KEYS:
        prop_name = f"utf.section.{key}"
        assert prop_name in props, (
            f"Property '{prop_name}' missing from JUnit XML testcase"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Test 4 — JSON summary schema validation
# ──────────────────────────────────────────────────────────────────────────────

def test_json_summary_schema():
    """TC-REP-004: JSON output must contain required top-level keys and valid types."""
    output = _make_engine_output(n_tests=3)
    reporter = ContractReporter(output)
    json_str = reporter.to_json()
    doc = json.loads(json_str)

    required_keys = [
        "report_version", "generated_at", "suite_contract_score",
        "test_count", "blocked_count", "section_averages",
        "section_pass_rates", "weakest_section", "tests",
    ]
    for key in required_keys:
        assert key in doc, f"Key '{key}' missing from JSON summary"

    assert isinstance(doc["tests"], list)
    assert len(doc["tests"]) == 3
    assert 0.0 <= doc["suite_contract_score"] <= 1.0

    for t in doc["tests"]:
        for key in _SECTION_KEYS:
            assert key in t["section_scores"], f"Section key '{key}' missing from test JSON"

    for key in _SECTION_KEYS:
        assert key in doc["section_averages"], f"'{key}' missing from section_averages"


# ──────────────────────────────────────────────────────────────────────────────
# Test 5 — report_writer creates dir, writes files, stable copy exists
# ──────────────────────────────────────────────────────────────────────────────

def test_report_writer_creates_dir_and_stable_copy(tmp_path):
    """TC-REP-005: write_contract_report must create dirs, write timestamped + stable files."""
    from mcp_server.reporting.report_writer import write_contract_report
    from mcp_server.config.utf_config import UTFConfig, ReportingConfig

    output = _make_engine_output(n_tests=2)
    cfg = UTFConfig()
    cfg.reporting = ReportingConfig(
        auto_report=True,
        report_dir=str(tmp_path / ".utf" / "reports"),
        formats=["html", "junit", "json"],
        keep_last_n=5,
    )

    written = write_contract_report(output, cfg, cwd=tmp_path)

    assert "html" in written
    assert "junit" in written
    assert "json" in written

    for path_str in written.values():
        assert Path(path_str).exists(), f"Expected file {path_str} to exist"

    report_dir = Path(cfg.reporting.report_dir)
    assert (report_dir / "last_contract_report.html").exists()
    assert (report_dir / "last_contract_report.xml").exists()
    assert (report_dir / "last_contract_report.json").exists()


# ──────────────────────────────────────────────────────────────────────────────
# Test 6 — report rotation removes oldest files beyond keep_last_n
# ──────────────────────────────────────────────────────────────────────────────

def test_report_rotation(tmp_path):
    """TC-REP-006: Old reports beyond keep_last_n must be deleted."""
    from mcp_server.reporting.report_writer import write_contract_report, _rotate_old_reports
    from mcp_server.config.utf_config import UTFConfig, ReportingConfig

    report_dir = tmp_path / ".utf" / "reports"
    report_dir.mkdir(parents=True)

    # Create 5 fake old html reports
    for i in range(5):
        (report_dir / f"contract_2025010{i}_120000.html").write_text("<html/>")

    # Rotate with keep_last_n=2
    _rotate_old_reports(report_dir, "contract", keep_last_n=2)

    remaining = sorted(report_dir.glob("contract_*.html"))
    assert len(remaining) == 2, f"Expected 2 files after rotation, got {len(remaining)}"
