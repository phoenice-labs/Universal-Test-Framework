"""
feedback/gap_reopener.py — Gap analysis and coverage health for UTF feedback loop.

Scans the registry for failed/gap tests and requirements with no passing coverage,
and computes a normalised health score for the project.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def check_and_reopen_gaps(
    project_id: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> dict:
    """
    Scan registry for:
    - Tests marked as 'failed'
    - Tests marked as 'gap'
    - Requirements covered by 0 passing tests

    Returns summary of reopened gaps and recommendations.
    """
    from mcp_server.registry.registry_engine import get_registry

    registry = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name

    all_records = registry.query(
        project_id=proj,
        test_type=None,
        language=None,
        status=None,
        requirement_id=None,
    )

    failed_tests: list[str] = []
    gap_tests: list[str] = []
    passing_reqs: set[str] = set()
    all_reqs: set[str] = set()

    for record in all_records:
        for req_id in record.requirement_ids:
            all_reqs.add(req_id)
        if record.status == "failed":
            failed_tests.append(record.test_id)
        elif record.status == "gap":
            gap_tests.append(record.test_id)
        elif record.status in ("executed", "passed"):
            for req_id in record.requirement_ids:
                passing_reqs.add(req_id)

    uncovered_reqs = sorted(all_reqs - passing_reqs)
    reopened = len(failed_tests) + len(gap_tests)

    recommendations: list[str] = []
    if failed_tests:
        recommendations.append(
            f"Fix {len(failed_tests)} failing test(s) to restore coverage."
        )
    if gap_tests:
        recommendations.append(
            f"Regenerate {len(gap_tests)} gap test(s) to fill missing coverage."
        )
    if uncovered_reqs:
        sample = ", ".join(uncovered_reqs[:5])
        suffix = "..." if len(uncovered_reqs) > 5 else ""
        recommendations.append(
            f"Generate tests for {len(uncovered_reqs)} requirement(s) with no passing tests: "
            f"{sample}{suffix}"
        )

    return {
        "project_id": proj,
        "failed_tests": failed_tests,
        "gap_tests": gap_tests,
        "uncovered_requirements": uncovered_reqs,
        "reopened_count": reopened,
        "recommendations": recommendations,
    }


def compute_coverage_health(
    project_id: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> dict:
    """
    Returns:
    {
        "total_tests": N,
        "passing": N,
        "failing": N,
        "gaps": N,
        "health_score": 0.0-1.0,  # passing / total
        "at_risk_requirements": [...]  # req IDs with < 1 passing test
    }
    """
    from mcp_server.registry.registry_engine import get_registry

    registry = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name

    all_records = registry.query(
        project_id=proj,
        test_type=None,
        language=None,
        status=None,
        requirement_id=None,
    )

    total = len(all_records)
    passing = 0
    failing = 0
    gaps = 0
    passing_reqs: set[str] = set()
    all_reqs: set[str] = set()

    for record in all_records:
        for req_id in record.requirement_ids:
            all_reqs.add(req_id)
        if record.status in ("executed", "passed"):
            passing += 1
            for req_id in record.requirement_ids:
                passing_reqs.add(req_id)
        elif record.status == "failed":
            failing += 1
        elif record.status == "gap":
            gaps += 1

    health_score = (passing / total) if total > 0 else 0.0
    at_risk = sorted(all_reqs - passing_reqs)

    has_tests = total > 0
    if not has_tests:
        status = "no_tests"
    elif health_score >= 0.90:
        status = "healthy"
    elif health_score >= 0.50:
        status = "degraded"
    else:
        status = "critical"

    return {
        "project_id": proj,
        "total_tests": total,
        "passing": passing,
        "failing": failing,
        "gap_tests": gaps,
        "health_score": round(health_score, 4),
        "has_tests": has_tests,
        "initialized": has_tests,
        "status": status,
        "at_risk_requirements": at_risk,
    }
