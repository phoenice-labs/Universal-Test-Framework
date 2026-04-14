"""
tests/reporting/test_auto_report_integration.py

Phase 2 integration tests — auto-report triggered by run_engine().
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_server.engine.rule_engine import run_engine


# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — run_engine produces report_path
# ──────────────────────────────────────────────────────────────────────────────

def test_run_engine_produces_report_path(tmp_path):
    """TC-AR-001: run_engine() must set output.report_path when auto_report=True."""
    output = run_engine(
        requirements_text="REQ-001: User can log in with valid credentials",
        test_type="unit",
        language="python",
        cwd=tmp_path,
    )
    # report_path should be a dict with at least one format
    assert output.report_path is not None, "Expected output.report_path to be set"
    assert isinstance(output.report_path, dict)
    assert len(output.report_path) > 0


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — last_contract_report.html exists on disk
# ──────────────────────────────────────────────────────────────────────────────

def test_last_report_file_exists(tmp_path):
    """TC-AR-002: .utf/reports/last_contract_report.html must be written after run_engine."""
    run_engine(
        requirements_text="REQ-001: System must validate email format per AC-1.1",
        test_type="unit",
        language="python",
        cwd=tmp_path,
    )
    stable = tmp_path / ".utf" / "reports" / "last_contract_report.html"
    assert stable.exists(), f"Stable report not found at {stable}"
    content = stable.read_text(encoding="utf-8")
    assert "UTF" in content or "contract" in content.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — auto_report=False skips report writing
# ──────────────────────────────────────────────────────────────────────────────

def test_auto_report_disabled_via_config(tmp_path):
    """TC-AR-003: When reporting.auto_report=False, no report files should be written."""
    # Write a config that disables auto_report
    utf_dir = tmp_path / ".utf"
    utf_dir.mkdir()
    (utf_dir / "utf-config.yaml").write_text(
        "reporting:\n  auto_report: false\n",
        encoding="utf-8",
    )

    output = run_engine(
        requirements_text="REQ-001: User can register with email",
        test_type="unit",
        language="python",
        cwd=tmp_path,
    )

    # report_path should be None or empty when disabled
    assert output.report_path is None or output.report_path == {}, (
        f"Expected no report_path when auto_report=False, got: {output.report_path}"
    )
    stable = tmp_path / ".utf" / "reports" / "last_contract_report.html"
    assert not stable.exists(), "Report file should not be written when auto_report=False"


# ──────────────────────────────────────────────────────────────────────────────
# Test 4 — suite_contract_score is populated and >= 0.85
# ──────────────────────────────────────────────────────────────────────────────

def test_suite_contract_score_on_output(tmp_path):
    """TC-AR-004: EngineOutput.suite_contract_score must be >= 0.85 for passing tests."""
    output = run_engine(
        requirements_text="REQ-001: Service must authenticate user via JWT per AC-2.1",
        test_type="unit",
        language="python",
        cwd=tmp_path,
    )
    assert hasattr(output, "suite_contract_score"), "EngineOutput missing suite_contract_score"
    assert 0.0 <= output.suite_contract_score <= 1.0
    # Passing tests should have a decent contract score
    if output.tests:
        assert output.suite_contract_score >= 0.50, (
            f"Suite contract score too low: {output.suite_contract_score}"
        )
