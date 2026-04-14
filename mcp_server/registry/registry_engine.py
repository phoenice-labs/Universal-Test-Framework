"""
registry/registry_engine.py — Public API for the UTF Persistent Test Registry.

This module provides high-level helpers used by run_engine() and MCP tools.
"""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mcp_server.config.utf_config import load_utf_config
from mcp_server.registry.backends.base import RegistryBackend, TestRecord

# ---------------------------------------------------------------------------
# Backend cache — keyed on (resolved_cwd, config_signature)
# ---------------------------------------------------------------------------

_backend_cache: dict[str, RegistryBackend] = {}


def get_registry(cwd: Path | None = None) -> RegistryBackend:
    """Return the configured backend (sqlite or rest) based on utf-config.yaml."""
    root = Path(cwd if cwd is not None else Path.cwd()).resolve()
    config = load_utf_config(root)
    reg = config.registry

    cache_key = f"{root}|{reg.backend}|{reg.sqlite_path}|{reg.rest_url}"
    if cache_key not in _backend_cache:
        if reg.backend == "rest" and reg.rest_url:
            from mcp_server.registry.backends.rest_backend import RESTBackend
            _backend_cache[cache_key] = RESTBackend(reg.rest_url, reg.rest_api_key)
        else:
            from mcp_server.registry.backends.sqlite_backend import SQLiteBackend
            db_path = root / reg.sqlite_path
            _backend_cache[cache_key] = SQLiteBackend(db_path)

    return _backend_cache[cache_key]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REQ_PATTERN = re.compile(
    r'\b(?:US|AC|TC|REQ|JIRA|STORY|FEAT|BUG|FIX|USER|STORY)-[\w\d.]+\b'
)


def _parse_req_ids_from_text(text: str) -> list[str]:
    """Extract requirement IDs from free text."""
    ids = _REQ_PATTERN.findall(text)
    # Deduplicate preserving order
    seen: set[str] = set()
    result = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            result.append(i)
    return result


def _parse_test_id_from_content(content: str) -> str:
    """Attempt to extract a Test ID from the content text."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("test id") or "test_id" in stripped.lower():
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                candidate = parts[1].strip()
                if candidate:
                    return candidate
    return ""


def _extract_test_info(test) -> tuple[str, list[str], float, str]:
    """Return (test_id, requirement_ids, score, content) from a dict or GeneratedTest dataclass."""
    if dataclasses.is_dataclass(test) and not isinstance(test, type):
        # GeneratedTest (or any dataclass)
        import json as _json
        test_id: str = getattr(test, "test_id", "")
        req_ids = _parse_req_ids_from_text(getattr(test, "requirement_mapping", ""))
        score: float = getattr(test, "validation_score", 0.85)
        # Store a JSON blob with all 8 sections + rendered_code so
        # ContractReporter/_SyntheticTest can re-read section data later.
        content: str = _json.dumps({
            "test_id": test_id,
            "why_generated": getattr(test, "why_generated", ""),
            "requirement_mapping": getattr(test, "requirement_mapping", ""),
            "how_it_exercises": getattr(test, "how_it_exercises", ""),
            "coverage_contribution": getattr(test, "coverage_contribution", ""),
            "expected_outcome": getattr(test, "expected_outcome", ""),
            "gaps_missing": getattr(test, "gaps_missing", ""),
            "meaningfulness_check": getattr(test, "meaningfulness_check", ""),
            "rendered_code": getattr(test, "rendered_code", ""),
            "validation_violations": getattr(test, "validation_violations", []),
        }, ensure_ascii=False)
    else:
        # Plain dict
        test_id = test.get("test_id", "") or _parse_test_id_from_content(test.get("content", ""))
        # Prefer explicit 'requirements' list; fall back to text parsing
        raw_reqs = test.get("requirements")
        if raw_reqs and isinstance(raw_reqs, list):
            req_ids = raw_reqs
        else:
            combined = (
                test.get("content", "")
                + " "
                + test.get("requirement_mapping", "")
            )
            req_ids = _parse_req_ids_from_text(combined)
        score = float(test.get("score", 0.85))
        content = test.get("content", "")

    # Filter: keep only IDs that contain a hyphen (US-001, AC-1.1, TC-001, REQ-001…)
    filtered_req_ids = [r for r in req_ids if "-" in r]
    return test_id, filtered_req_ids or req_ids, score, content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upsert_tests(
    tests: list,
    test_type: str,
    language: str,
    framework: str,
    project_id: str | None = None,
    cwd: Path | None = None,
) -> None:
    """Called after successful test generation. Upserts each test into the registry."""
    backend = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name
    now = datetime.now(timezone.utc).isoformat()

    for test in tests:
        test_id, req_ids, score, content = _extract_test_info(test)
        if not test_id:
            continue

        record = TestRecord(
            test_id=test_id,
            project_id=proj,
            test_type=test_type,
            language=language or "",
            framework=framework or "",
            requirement_ids=req_ids,
            score=score,
            content=content,
            status="generated",
            created_at=now,
            updated_at=now,
        )
        backend.upsert(record)


def query_registry(
    project_id: str | None = None,
    test_type: str | None = None,
    language: str | None = None,
    status: str | None = None,
    requirement_id: str | None = None,
    cwd: Path | None = None,
) -> dict:
    """Return registry query results as a serializable dict."""
    backend = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name
    records = backend.query(
        project_id=proj,
        test_type=test_type,
        language=language,
        status=status,
        requirement_id=requirement_id,
    )
    return {"records": [dataclasses.asdict(r) for r in records]}


def coverage_summary(
    project_id: str | None = None,
    cwd: Path | None = None,
) -> dict:
    """Return coverage summary for the project."""
    backend = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name
    return backend.coverage_summary(proj)


def gap_analysis(
    project_id: str | None = None,
    cwd: Path | None = None,
) -> list[str]:
    """Return test IDs of tests marked as 'gap' for the project."""
    backend = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name
    return backend.gap_analysis(proj)
