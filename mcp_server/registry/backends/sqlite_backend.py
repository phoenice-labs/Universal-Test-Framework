"""
registry/backends/sqlite_backend.py — SQLite implementation of RegistryBackend.

Uses per-operation connections with explicit close() to avoid holding file
handles open between calls (critical on Windows where open handles block
temporary directory cleanup and file deletion).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .base import RegistryBackend, TestRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS test_records (
    test_id         TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    test_type       TEXT,
    language        TEXT,
    framework       TEXT,
    requirement_ids TEXT,
    score           REAL,
    content         TEXT,
    status          TEXT DEFAULT 'generated',
    created_at      TEXT,
    updated_at      TEXT,
    PRIMARY KEY (test_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_project ON test_records(project_id);
CREATE INDEX IF NOT EXISTS idx_status  ON test_records(project_id, status);
CREATE INDEX IF NOT EXISTS idx_req     ON test_records(requirement_ids);

CREATE TABLE IF NOT EXISTS coverage_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT,
    snapshot_date TEXT,
    total_tests   INTEGER,
    passing_tests INTEGER,
    failing_tests INTEGER,
    gap_tests     INTEGER,
    health_score  REAL,
    created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_snap_project ON coverage_snapshots(project_id, snapshot_date);

CREATE TABLE IF NOT EXISTS execution_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id        TEXT NOT NULL,
    project_id     TEXT NOT NULL,
    run_timestamp  TEXT NOT NULL,
    exec_status    TEXT NOT NULL,
    exec_duration  REAL,
    contract_score REAL,
    section_scores TEXT,
    gaps           TEXT,
    error_message  TEXT
);
CREATE INDEX IF NOT EXISTS idx_exec_test    ON execution_results(test_id, project_id);
CREATE INDEX IF NOT EXISTS idx_exec_ts      ON execution_results(run_timestamp);

CREATE TABLE IF NOT EXISTS contract_trend (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          TEXT NOT NULL,
    run_timestamp       TEXT NOT NULL,
    avg_contract_score  REAL NOT NULL,
    blocked_count       INTEGER NOT NULL DEFAULT 0,
    test_count          INTEGER NOT NULL DEFAULT 0,
    section_scores_json TEXT,
    exec_pass_rate      REAL,
    test_type           TEXT,
    language            TEXT
);
CREATE INDEX IF NOT EXISTS idx_trend_project ON contract_trend(project_id, run_timestamp);
"""


class SQLiteBackend(RegistryBackend):
    """SQLite registry backend.

    Opens and explicitly closes a connection for every operation so the
    database file is never held open between calls.  This is especially
    important on Windows, where an open handle prevents directory deletion.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._open()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _open(self) -> sqlite3.Connection:
        """Return a new connection.  Caller MUST call conn.close()."""
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _conn(self):
        """Context manager that always closes the connection on exit."""
        conn = self._open()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    def _row_to_record(self, row: sqlite3.Row) -> TestRecord:
        return TestRecord(
            test_id=row["test_id"],
            project_id=row["project_id"],
            test_type=row["test_type"] or "",
            language=row["language"] or "",
            framework=row["framework"] or "",
            requirement_ids=json.loads(row["requirement_ids"] or "[]"),
            score=row["score"] or 0.0,
            content=row["content"] or "",
            status=row["status"] or "generated",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    # ------------------------------------------------------------------
    def upsert(self, record: TestRecord) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO test_records
                    (test_id, project_id, test_type, language, framework,
                     requirement_ids, score, content, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(test_id, project_id) DO UPDATE SET
                    test_type       = excluded.test_type,
                    language        = excluded.language,
                    framework       = excluded.framework,
                    requirement_ids = excluded.requirement_ids,
                    score           = excluded.score,
                    content         = excluded.content,
                    status          = excluded.status,
                    updated_at      = excluded.updated_at
                """,
                (
                    record.test_id,
                    record.project_id,
                    record.test_type,
                    record.language,
                    record.framework,
                    json.dumps(record.requirement_ids),
                    record.score,
                    record.content,
                    record.status,
                    record.created_at or now,
                    now,
                ),
            )

    # ------------------------------------------------------------------
    def query(
        self,
        project_id: str | None,
        test_type: str | None,
        language: str | None,
        status: str | None,
        requirement_id: str | None,
    ) -> list[TestRecord]:
        conditions: list[str] = []
        params: list = []

        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)
        if test_type is not None:
            conditions.append("test_type = ?")
            params.append(test_type)
        if language is not None:
            conditions.append("language = ?")
            params.append(language)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if requirement_id is not None:
            # JSON array stored as text — LIKE-based contains check
            conditions.append("requirement_ids LIKE ?")
            params.append(f'%"{requirement_id}"%')

        sql = "SELECT * FROM test_records"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    def get_by_id(self, test_id: str, project_id: str) -> Optional[TestRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM test_records WHERE test_id = ? AND project_id = ?",
                (test_id, project_id),
            ).fetchone()
        return self._row_to_record(row) if row else None

    # ------------------------------------------------------------------
    def mark_status(self, test_id: str, project_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE test_records SET status = ?, updated_at = ? "
                "WHERE test_id = ? AND project_id = ?",
                (status, now, test_id, project_id),
            )

    # ------------------------------------------------------------------
    def coverage_summary(self, project_id: str) -> dict:
        records = self.query(
            project_id=project_id,
            test_type=None,
            language=None,
            status=None,
            requirement_id=None,
        )
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_language: dict[str, int] = {}
        for r in records:
            by_type[r.test_type] = by_type.get(r.test_type, 0) + 1
            by_status[r.status] = by_status.get(r.status, 0) + 1
            by_language[r.language] = by_language.get(r.language, 0) + 1
        return {
            "total": len(records),
            "by_type": by_type,
            "by_status": by_status,
            "by_language": by_language,
        }

    # ------------------------------------------------------------------
    def gap_analysis(self, project_id: str) -> list[str]:
        records = self.query(
            project_id=project_id,
            test_type=None,
            language=None,
            status="gap",
            requirement_id=None,
        )
        return [r.test_id for r in records]

    # ------------------------------------------------------------------
    def save_snapshot(self, project_id: str, snapshot: dict) -> None:
        """Upsert a daily coverage snapshot (one row per project per date)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            # Delete any existing snapshot for this project+date to avoid duplicates
            conn.execute(
                "DELETE FROM coverage_snapshots WHERE project_id = ? AND snapshot_date = ?",
                (project_id, snapshot.get("snapshot_date", "")),
            )
            conn.execute(
                """
                INSERT INTO coverage_snapshots
                    (project_id, snapshot_date, total_tests, passing_tests,
                     failing_tests, gap_tests, health_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    snapshot.get("snapshot_date", ""),
                    snapshot.get("total_tests", 0),
                    snapshot.get("passing_tests", 0),
                    snapshot.get("failing_tests", 0),
                    snapshot.get("gap_tests", 0),
                    snapshot.get("health_score", 0.0),
                    snapshot.get("created_at", now),
                ),
            )

    # ------------------------------------------------------------------
    def get_snapshots(self, project_id: str, days: int = 30) -> list[dict]:
        """Return coverage snapshots for *project_id* within the last *days* days."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT project_id, snapshot_date, total_tests, passing_tests,
                       failing_tests, gap_tests, health_score, created_at
                FROM coverage_snapshots
                WHERE project_id = ? AND snapshot_date >= ?
                ORDER BY snapshot_date ASC
                """,
                (project_id, cutoff),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Phase 3 — Execution results
    # ------------------------------------------------------------------
    def insert_execution_result(self, project_id: str, record: dict) -> None:
        """Persist one execution result row linking test_id to exec status + contract score."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO execution_results
                    (test_id, project_id, run_timestamp, exec_status, exec_duration,
                     contract_score, section_scores, gaps, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("test_id", ""),
                    project_id,
                    record.get("run_timestamp", now),
                    record.get("exec_status", "unknown"),
                    record.get("exec_duration"),
                    record.get("contract_score"),
                    json.dumps(record.get("section_scores")) if record.get("section_scores") else None,
                    record.get("gaps"),
                    record.get("error_message"),
                ),
            )

    def get_execution_results(
        self, project_id: str, test_id: Optional[str] = None, last_n: int = 100
    ) -> list[dict]:
        """Return execution results for a project, optionally filtered by test_id."""
        if test_id:
            sql = (
                "SELECT * FROM execution_results WHERE project_id = ? AND test_id = ? "
                "ORDER BY run_timestamp DESC LIMIT ?"
            )
            params = (project_id, test_id, last_n)
        else:
            sql = (
                "SELECT * FROM execution_results WHERE project_id = ? "
                "ORDER BY run_timestamp DESC LIMIT ?"
            )
            params = (project_id, last_n)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Phase 3 — Contract trend
    # ------------------------------------------------------------------
    def insert_contract_trend(self, project_id: str, record: dict) -> None:
        """Persist a contract trend snapshot row."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO contract_trend
                    (project_id, run_timestamp, avg_contract_score, blocked_count,
                     test_count, section_scores_json, exec_pass_rate, test_type, language)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    record.get("run_timestamp", now),
                    record.get("avg_contract_score", 0.0),
                    record.get("blocked_count", 0),
                    record.get("test_count", 0),
                    json.dumps(record.get("section_scores_json")) if record.get("section_scores_json") else None,
                    record.get("exec_pass_rate"),
                    record.get("test_type"),
                    record.get("language"),
                ),
            )

    def get_contract_trend(self, project_id: str, last_n: int = 10) -> list[dict]:
        """Return the last N contract trend rows for a project."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM contract_trend WHERE project_id = ?
                ORDER BY run_timestamp DESC LIMIT ?
                """,
                (project_id, last_n),
            ).fetchall()
        return [dict(row) for row in rows]

