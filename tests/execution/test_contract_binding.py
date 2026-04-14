"""
tests/execution/test_contract_binding.py

Phase 3 tests for the execution_results and contract_trend tables
added to SQLiteBackend.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mcp_server.registry.backends.sqlite_backend import SQLiteBackend


# ──────────────────────────────────────────────────────────────────────────────
# Fixture
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path) -> SQLiteBackend:
    return SQLiteBackend(tmp_path / "test.db")


# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — execution_results table is created
# ──────────────────────────────────────────────────────────────────────────────

def test_execution_results_table_created(db, tmp_path):
    """TC-EB-001: SQLiteBackend must create execution_results table on init."""
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "execution_results" in tables


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — binding produces exec_status per test
# ──────────────────────────────────────────────────────────────────────────────

def test_binding_produces_exec_status_per_test(db):
    """TC-EB-002: insert_execution_result must persist exec_status for a test."""
    now = datetime.now(timezone.utc).isoformat()
    db.insert_execution_result("proj-x", {
        "test_id": "TC-REQ-001",
        "run_timestamp": now,
        "exec_status": "passed",
        "exec_duration": 0.042,
        "contract_score": 0.97,
        "section_scores": {"test_id": 0.10, "why_generated": 0.10},
        "gaps": "does not test concurrent access",
        "error_message": None,
    })

    rows = db.get_execution_results("proj-x", test_id="TC-REQ-001")
    assert len(rows) == 1
    assert rows[0]["exec_status"] == "passed"
    assert abs(rows[0]["exec_duration"] - 0.042) < 0.001
    assert abs(rows[0]["contract_score"] - 0.97) < 0.001


# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — failed test recorded with error_message
# ──────────────────────────────────────────────────────────────────────────────

def test_failed_test_recorded_with_error_message(db):
    """TC-EB-003: A failed test's error_message must be persisted."""
    now = datetime.now(timezone.utc).isoformat()
    db.insert_execution_result("proj-x", {
        "test_id": "TC-REQ-002",
        "run_timestamp": now,
        "exec_status": "failed",
        "exec_duration": 0.01,
        "contract_score": 0.90,
        "error_message": "AssertionError: expected 200, got 404",
    })

    rows = db.get_execution_results("proj-x", test_id="TC-REQ-002")
    assert len(rows) == 1
    assert rows[0]["exec_status"] == "failed"
    assert "AssertionError" in (rows[0]["error_message"] or "")


# ──────────────────────────────────────────────────────────────────────────────
# Test 4 — contract_score preserved after execution insert
# ──────────────────────────────────────────────────────────────────────────────

def test_contract_score_preserved_after_execution(db):
    """TC-EB-004: contract_score stored in execution_results must be retrievable."""
    now = datetime.now(timezone.utc).isoformat()
    db.insert_execution_result("proj-y", {
        "test_id": "TC-REQ-003",
        "run_timestamp": now,
        "exec_status": "passed",
        "contract_score": 0.964,
    })

    rows = db.get_execution_results("proj-y")
    assert len(rows) >= 1
    found = [r for r in rows if r["test_id"] == "TC-REQ-003"]
    assert found, "TC-REQ-003 not found in execution_results"
    assert abs(found[0]["contract_score"] - 0.964) < 0.001


# ──────────────────────────────────────────────────────────────────────────────
# Test 5 — contract_trend table insert + retrieve
# ──────────────────────────────────────────────────────────────────────────────

def test_contract_trend_insert_and_retrieve(db):
    """TC-EB-005: insert_contract_trend + get_contract_trend must round-trip correctly."""
    now = datetime.now(timezone.utc).isoformat()
    db.insert_contract_trend("proj-z", {
        "run_timestamp": now,
        "avg_contract_score": 0.95,
        "blocked_count": 0,
        "test_count": 5,
        "section_scores_json": {"test_id": 0.10, "why_generated": 0.09},
        "exec_pass_rate": 1.0,
        "test_type": "unit",
        "language": "python",
    })

    rows = db.get_contract_trend("proj-z", last_n=5)
    assert len(rows) >= 1
    row = rows[0]
    assert abs(row["avg_contract_score"] - 0.95) < 0.001
    assert row["test_count"] == 5
