"""
mcp_server/tools/generate_report.py — MCP Tool: generate_report (Tool #12)

Reads the test registry and execution results, builds the 8-section contract
report in requested formats, and returns report paths + summary.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def generate_report(
    formats: Optional[list[str]] = None,
    open_html: bool = False,
    project_id: Optional[str] = None,
    cwd: Optional[str] = None,
) -> dict[str, Any]:
    """
    Generate the 8-section contract compliance report.

    Reads from the registry (tests + execution_results) and builds HTML,
    JUnit XML, and/or JSON report files.

    Args:
        formats:    Subset of ["html", "junit", "json"]. Defaults to all three.
        open_html:  If True, open the HTML report in the default browser.
        project_id: Registry project ID (defaults to current directory name).
        cwd:        Project root directory (defaults to current working dir).

    Returns:
        report_path:           dict {html, junit, json} of absolute paths
        suite_contract_score:  Average contract score for the run
        sections_summary:      Per-section pass rates + averages
        blocked_count:         Tests blocked at generation time
        exec_pass_rate:        Pass rate from run_tests (None if not run)
        trend:                 Contract score trend data (last 10 runs)
        generated_at:          ISO timestamp
    """
    resolved_cwd = Path(cwd) if cwd else Path.cwd()
    proj = project_id or resolved_cwd.name
    report_formats = formats if formats else ["html", "junit", "json"]

    # Load config
    try:
        from mcp_server.config.utf_config import load_utf_config
        cfg = load_utf_config(resolved_cwd)
    except Exception:
        from mcp_server.config.utf_config import UTFConfig
        cfg = UTFConfig()

    # Get registry + execution results
    try:
        from mcp_server.registry.registry_engine import get_registry
        registry = get_registry(resolved_cwd)
        records = registry.query(
            project_id=proj, test_type=None, language=None,
            status=None, requirement_id=None,
        )
        exec_results_raw = registry.get_execution_results(proj, last_n=200)
    except Exception:
        records = []
        exec_results_raw = []

    if not records:
        return {
            "error": "No test records found in registry. Run generate_tests first.",
            "report_path": None,
            "suite_contract_score": 0.0,
            "sections_summary": {},
            "blocked_count": 0,
            "exec_pass_rate": None,
            "trend": {},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Build a synthetic EngineOutput-like object from registry records
    engine_output = _build_engine_output_from_registry(records, proj)

    # Build execution results mapping (most recent per test_id)
    exec_map: dict[str, dict] = {}
    for row in exec_results_raw:
        tid = row.get("test_id", "")
        if tid and tid not in exec_map:
            exec_map[tid] = {
                "test_id": tid,
                "exec_status": row.get("exec_status"),
                "exec_duration_s": row.get("exec_duration"),
                "contract_score": row.get("contract_score"),
                "section_scores": json.loads(row["section_scores"]) if row.get("section_scores") else {},
            }

    execution_results = list(exec_map.values()) if exec_map else None

    # Build reporter
    from mcp_server.reporting.contract_reporter import ContractReporter
    reporter = ContractReporter(engine_output, execution_results=execution_results)
    report = reporter.build()

    # Override formats from argument
    import dataclasses
    cfg_override = dataclasses.replace(
        cfg,
        reporting=dataclasses.replace(
            cfg.reporting,
            formats=report_formats,
            open_html=open_html,
            auto_report=True,
        ),
    )

    # Write report files
    from mcp_server.reporting.report_writer import write_contract_report
    report_paths = write_contract_report(
        engine_output, cfg_override, cwd=resolved_cwd,
        execution_results=execution_results,
    )

    # Build sections summary
    sections_summary = {
        "averages": {k: round(v, 4) for k, v in report.section_averages.items()},
        "pass_rates": {k: round(v, 4) for k, v in report.section_pass_rates.items()},
        "weakest_section": report.weakest_section,
        "weakest_avg": round(report.weakest_section_avg, 4),
    }

    # Trend data
    trend: dict[str, Any] = {}
    try:
        trend_rows = registry.get_contract_trend(proj, last_n=10)
        if trend_rows:
            scores = [r.get("avg_contract_score", 0.0) for r in reversed(trend_rows)]
            trend = {
                "runs": len(trend_rows),
                "avg_score_last_run": round(scores[-1], 4) if scores else 0.0,
                "avg_score_trend": [round(s, 4) for s in scores],
                "drift_alert": (
                    len(scores) >= 2 and (scores[-1] - scores[-2]) < -0.05
                ),
                "weakest_section": report.weakest_section,
                "weakest_section_avg": round(report.weakest_section_avg, 4),
            }
    except Exception:
        pass

    # Record this run in contract_trend
    try:
        now = datetime.now(timezone.utc).isoformat()
        registry.insert_contract_trend(proj, {
            "run_timestamp": now,
            "avg_contract_score": round(report.suite_contract_score, 4),
            "blocked_count": report.blocked_count,
            "test_count": report.test_count,
            "section_scores_json": report.section_averages,
            "exec_pass_rate": report.exec_pass_rate,
            "test_type": report.test_type,
            "language": report.language,
        })
    except Exception:
        pass

    return {
        "report_path": report_paths,
        "suite_contract_score": round(report.suite_contract_score, 4),
        "sections_summary": sections_summary,
        "blocked_count": report.blocked_count,
        "exec_pass_rate": report.exec_pass_rate,
        "trend": trend,
        "generated_at": report.generated_at,
        "test_count": report.test_count,
    }


# ---------------------------------------------------------------------------
# Internal: build synthetic EngineOutput from registry records
# ---------------------------------------------------------------------------

class _SyntheticTest:
    """Minimal test object compatible with ContractReporter expectations."""
    def __init__(self, record: Any) -> None:
        content = record.content or "{}"
        try:
            data = json.loads(content)
        except Exception:
            data = {}
        self.test_id = record.test_id
        self.why_generated = data.get("why_generated", "")
        self.requirement_mapping = data.get("requirement_mapping", "")
        self.how_it_exercises = data.get("how_it_exercises", "")
        self.coverage_contribution = data.get("coverage_contribution", "")
        self.expected_outcome = data.get("expected_outcome", "")
        self.gaps_missing = data.get("gaps_missing", "")
        self.meaningfulness_check = data.get("meaningfulness_check", "")
        self.rendered_code = data.get("rendered_code", "")
        self.validation_score = record.score or 0.0
        self.validation_passed = (record.score or 0.0) >= 0.85
        self.validation_violations = data.get("validation_violations", [])


class _SyntheticEngineOutput:
    def __init__(self, tests: list, language: str = "", framework: str = "",
                 test_type: str = "") -> None:
        self.tests = tests
        self.blocked_tests = []
        self.coverage_summary = {"test_type": test_type}
        self.suite_contract_score = (
            sum(t.validation_score for t in tests) / len(tests) if tests else 0.0
        )
        self.detected_language = language
        self.detected_framework = framework


def _build_engine_output_from_registry(records: list, proj: str) -> _SyntheticEngineOutput:
    tests = [_SyntheticTest(r) for r in records]
    lang = records[0].language if records else ""
    fw = records[0].framework if records else ""
    tt = records[0].test_type if records else ""
    return _SyntheticEngineOutput(tests=tests, language=lang, framework=fw, test_type=tt)
