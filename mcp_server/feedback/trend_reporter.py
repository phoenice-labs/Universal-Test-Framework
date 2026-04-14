"""
feedback/trend_reporter.py — Coverage trend analysis for UTF feedback loop.

Reads coverage snapshots from the registry and computes trend direction,
7-day delta, and historical series.

Phase 3 extensions: contract score trend tracking (record_contract_snapshot,
get_contract_trend, detect_contract_drift).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


_SECTION_KEYS = [
    "test_id", "why_generated", "requirement_mapping", "how_it_exercises",
    "coverage_contribution", "expected_outcome", "gaps_missing", "meaningfulness_check",
]


def get_coverage_trend(
    project_id: Optional[str] = None,
    days: int = 30,
    cwd: Optional[Path] = None,
) -> dict:
    """
    Read historical snapshots from the registry and compute trend.

    Returns:
    {
        "project_id": "...",
        "period_days": 30,
        "snapshots": [{"date": "YYYY-MM-DD", "total": N, "passing": N, "score": 0.0-1.0}],
        "trend": "improving" | "stable" | "degrading",
        "current_score": 0.0-1.0,
        "delta_7_days": +0.05
    }
    """
    from mcp_server.registry.registry_engine import get_registry

    registry = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name

    raw_snapshots: list[dict] = []
    try:
        raw_snapshots = registry.get_snapshots(proj, days)  # type: ignore[attr-defined]
    except AttributeError:
        # Backend doesn't support snapshots — return minimal result
        pass

    snapshots = [
        {
            "date": s.get("snapshot_date", ""),
            "total": s.get("total_tests", 0),
            "passing": s.get("passing_tests", 0),
            "score": round(s.get("health_score", 0.0), 4),
        }
        for s in raw_snapshots
    ]

    current_score = snapshots[-1]["score"] if snapshots else 0.0

    # Compute 7-day delta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    old_snapshots = [s for s in snapshots if s["date"] < cutoff]
    baseline_score = old_snapshots[-1]["score"] if old_snapshots else (snapshots[0]["score"] if snapshots else 0.0)
    delta_7_days = round(current_score - baseline_score, 4)

    # Determine trend direction
    if len(snapshots) < 2:
        trend = "stable"
    elif delta_7_days > 0.02:
        trend = "improving"
    elif delta_7_days < -0.02:
        trend = "degrading"
    else:
        trend = "stable"

    return {
        "project_id": proj,
        "period_days": days,
        "snapshots": snapshots,
        "trend": trend,
        "current_score": current_score,
        "delta_7_days": delta_7_days,
    }


def save_daily_snapshot(
    project_id: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> None:
    """Save a snapshot of current coverage to the registry trend table."""
    from mcp_server.registry.registry_engine import get_registry
    from mcp_server.feedback.gap_reopener import compute_coverage_health

    registry = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name

    health = compute_coverage_health(project_id=proj, cwd=cwd)

    snapshot = {
        "project_id": proj,
        "snapshot_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_tests": health["total_tests"],
        "passing_tests": health["passing"],
        "failing_tests": health["failing"],
        "gap_tests": health["gap_tests"],
        "health_score": health["health_score"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        registry.save_snapshot(proj, snapshot)  # type: ignore[attr-defined]
    except AttributeError:
        pass  # Backend doesn't support snapshots — silently skip


# ────────────────────────────────────────────────────────────────────────────
# Phase 3 — Contract score trend helpers
# ────────────────────────────────────────────────────────────────────────────

def record_contract_snapshot(
    engine_output: object,
    exec_pass_rate: Optional[float] = None,
    project_id: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> None:
    """
    Persist a contract score snapshot for the given engine_output.

    Inserts one row into contract_trend with the suite score, section averages,
    and optional execution pass rate.

    Args:
        engine_output:  EngineOutput from run_engine()
        exec_pass_rate: Optional execution pass rate (from run_tests)
        project_id:     Registry project ID (defaults to cwd name)
        cwd:            Project root (defaults to Path.cwd())
    """
    from mcp_server.registry.registry_engine import get_registry
    from mcp_server.reporting.contract_reporter import ContractReporter

    registry = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name

    try:
        reporter = ContractReporter(engine_output)
        report = reporter.build()
        now = datetime.now(timezone.utc).isoformat()

        registry.insert_contract_trend(proj, {  # type: ignore[attr-defined]
            "run_timestamp": now,
            "avg_contract_score": round(report.suite_contract_score, 4),
            "blocked_count": report.blocked_count,
            "test_count": report.test_count,
            "section_scores_json": report.section_averages,
            "exec_pass_rate": exec_pass_rate,
            "test_type": report.test_type,
            "language": report.language,
        })
    except Exception:
        pass  # Trend recording is best-effort


def get_contract_trend(
    project_id: Optional[str] = None,
    last_n: int = 10,
    cwd: Optional[Path] = None,
) -> dict:
    """
    Return the last N contract trend snapshots for the project.

    Returns:
        {
            "project_id": "...",
            "runs": N,
            "avg_score_last_run": 0.97,
            "avg_score_trend": [0.91, 0.93, ...],
            "drift_alert": False,
            "weakest_section": "meaningfulness_check",
            "weakest_section_avg": 0.88,
            "snapshots": [...]
        }
    """
    from mcp_server.registry.registry_engine import get_registry

    registry = get_registry(cwd)
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name

    rows: list[dict] = []
    try:
        rows = registry.get_contract_trend(proj, last_n=last_n)  # type: ignore[attr-defined]
    except AttributeError:
        pass

    if not rows:
        return {
            "project_id": proj,
            "runs": 0,
            "avg_score_last_run": 0.0,
            "avg_score_trend": [],
            "drift_alert": False,
            "weakest_section": None,
            "weakest_section_avg": 0.0,
            "snapshots": [],
        }

    # Rows come back most-recent-first; reverse for chronological trend
    snapshots = list(reversed(rows))
    scores = [r.get("avg_contract_score", 0.0) for r in snapshots]
    last_score = scores[-1] if scores else 0.0
    drift_alert = len(scores) >= 2 and (scores[-1] - scores[-2]) < -0.05

    # Compute weakest section across all snapshots
    section_avgs: dict[str, list[float]] = {k: [] for k in _SECTION_KEYS}
    for row in rows:
        import json
        sec_json = row.get("section_scores_json")
        if sec_json:
            try:
                sec_data = json.loads(sec_json) if isinstance(sec_json, str) else sec_json
                for key in _SECTION_KEYS:
                    if key in sec_data:
                        section_avgs[key].append(float(sec_data[key]))
            except Exception:
                pass

    weakest_key = None
    weakest_avg = 1.0
    for key, vals in section_avgs.items():
        if vals:
            avg = sum(vals) / len(vals)
            if avg < weakest_avg:
                weakest_avg = avg
                weakest_key = key

    return {
        "project_id": proj,
        "runs": len(rows),
        "avg_score_last_run": round(last_score, 4),
        "avg_score_trend": [round(s, 4) for s in scores],
        "drift_alert": drift_alert,
        "weakest_section": weakest_key,
        "weakest_section_avg": round(weakest_avg, 4),
        "snapshots": [
            {
                "run_timestamp": r.get("run_timestamp", ""),
                "avg_contract_score": round(r.get("avg_contract_score", 0.0), 4),
                "blocked_count": r.get("blocked_count", 0),
                "test_count": r.get("test_count", 0),
                "exec_pass_rate": r.get("exec_pass_rate"),
            }
            for r in snapshots
        ],
    }


def detect_contract_drift(
    project_id: Optional[str] = None,
    threshold: float = 0.05,
    cwd: Optional[Path] = None,
) -> dict:
    """
    Alert if the latest contract score dropped more than *threshold* vs the prior run.

    Returns:
        {"drift_detected": bool, "delta": float, "current": float, "previous": float}
    """
    trend = get_contract_trend(project_id=project_id, last_n=2, cwd=cwd)
    scores = trend.get("avg_score_trend", [])
    if len(scores) < 2:
        return {"drift_detected": False, "delta": 0.0, "current": scores[-1] if scores else 0.0, "previous": 0.0}
    delta = scores[-1] - scores[-2]
    return {
        "drift_detected": delta < -threshold,
        "delta": round(delta, 4),
        "current": round(scores[-1], 4),
        "previous": round(scores[-2], 4),
    }

