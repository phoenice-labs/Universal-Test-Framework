"""
tests/feedback2/test_trend_reporter_contract.py

Phase 6 tests for the contract score trend helpers in trend_reporter.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.feedback.trend_reporter import (
    record_contract_snapshot,
    get_contract_trend,
    detect_contract_drift,
)
from mcp_server.registry.backends.sqlite_backend import SQLiteBackend


# ──────────────────────────────────────────────────────────────────────────────
# Helper: create a minimal EngineOutput-like object
# ──────────────────────────────────────────────────────────────────────────────

def _make_engine_output(score: float = 0.95, n: int = 3) -> MagicMock:
    t = MagicMock()
    t.test_id = "TC-REQ-001"
    t.why_generated = "Covers happy path for REQ-001 via unit test scenario"
    t.requirement_mapping = "REQ-001: AC-1.1 system must process user requests"
    t.how_it_exercises = "GIVEN valid state WHEN invoked THEN result matches expectation"
    t.coverage_contribution = "Branch coverage for unit test. Risk: low."
    t.expected_outcome = "Returns expected value without exceptions"
    t.gaps_missing = "Does not cover concurrent access or failure injection"
    t.meaningfulness_check = "Meaningful no hallucination directly validates REQ-001"
    t.validation_score = score
    t.validation_passed = score >= 0.85
    t.validation_violations = []

    out = MagicMock()
    out.tests = [t] * n
    out.blocked_tests = []
    out.detected_language = "python"
    out.detected_framework = "pytest"
    out.coverage_summary = {"test_type": "unit"}
    out.suite_contract_score = score
    out.blocked_count = 0
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — record_contract_snapshot inserts a row
# ──────────────────────────────────────────────────────────────────────────────

def test_record_contract_snapshot_inserts_row(tmp_path):
    """TC-TR-001: record_contract_snapshot must insert a row into contract_trend."""
    output = _make_engine_output(score=0.95)
    record_contract_snapshot(output, exec_pass_rate=1.0, project_id="test-proj", cwd=tmp_path)

    backend = SQLiteBackend(tmp_path / ".utf" / "utf.db")
    rows = backend.get_contract_trend("test-proj", last_n=5)
    assert len(rows) >= 1
    assert rows[0]["avg_contract_score"] > 0.0  # row was inserted with a valid score


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — get_contract_trend returns last_n entries
# ──────────────────────────────────────────────────────────────────────────────

def test_get_contract_trend_returns_last_n(tmp_path):
    """TC-TR-002: get_contract_trend must return at most last_n snapshots."""
    backend = SQLiteBackend(tmp_path / ".utf" / "utf.db")
    now = datetime.now(timezone.utc).isoformat()
    for i in range(7):
        backend.insert_contract_trend("proj-t", {
            "run_timestamp": now,
            "avg_contract_score": 0.90 + i * 0.01,
            "blocked_count": 0,
            "test_count": 5,
        })

    trend = get_contract_trend(project_id="proj-t", last_n=3, cwd=tmp_path)
    assert trend["runs"] <= 3, f"Expected at most 3 snapshots, got {trend['runs']}"
    assert len(trend["avg_score_trend"]) <= 3


# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — detect_drift raises when score drops
# ──────────────────────────────────────────────────────────────────────────────

def test_detect_drift_raises_when_score_drops(tmp_path):
    """TC-TR-003: detect_contract_drift must detect a >5% score drop."""
    backend = SQLiteBackend(tmp_path / ".utf" / "utf.db")
    now = datetime.now(timezone.utc).isoformat()
    backend.insert_contract_trend("proj-d", {"run_timestamp": now, "avg_contract_score": 0.95, "blocked_count": 0, "test_count": 5})
    backend.insert_contract_trend("proj-d", {"run_timestamp": now, "avg_contract_score": 0.82, "blocked_count": 0, "test_count": 5})

    result = detect_contract_drift(project_id="proj-d", threshold=0.05, cwd=tmp_path)
    assert result["drift_detected"] is True, f"Expected drift detected, got: {result}"
    assert result["delta"] < -0.05


# ──────────────────────────────────────────────────────────────────────────────
# Test 4 — weakest section identified correctly
# ──────────────────────────────────────────────────────────────────────────────

def test_weakest_section_identified_correctly(tmp_path):
    """TC-TR-004: get_contract_trend must identify the section with the lowest average score."""
    backend = SQLiteBackend(tmp_path / ".utf" / "utf.db")
    now = datetime.now(timezone.utc).isoformat()
    backend.insert_contract_trend("proj-w", {
        "run_timestamp": now,
        "avg_contract_score": 0.93,
        "blocked_count": 0,
        "test_count": 4,
        "section_scores_json": {
            "test_id": 0.10,
            "why_generated": 0.10,
            "requirement_mapping": 0.14,
            "how_it_exercises": 0.20,
            "coverage_contribution": 0.15,
            "expected_outcome": 0.15,
            "gaps_missing": 0.10,
            "meaningfulness_check": 0.02,  # lowest
        },
    })

    trend = get_contract_trend(project_id="proj-w", last_n=5, cwd=tmp_path)
    assert trend["weakest_section"] == "meaningfulness_check", (
        f"Expected weakest_section=meaningfulness_check, got {trend['weakest_section']}"
    )
