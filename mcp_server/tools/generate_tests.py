"""
generate_tests.py — MCP Tool: generate_tests
Generates a full test suite for given source code and/or requirements.
"""
from __future__ import annotations

from typing import Any, Optional

from ..engine.rule_engine import run_engine, EngineOutput


def generate_tests(
    test_type: str,
    source_code: Optional[str] = None,
    requirements_text: Optional[str] = None,
    language: Optional[str] = None,
    framework: Optional[str] = None,
    file_path: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict[str, Any]:
    """
    Generate a test suite satisfying the 8-section contract.

    Args:
        test_type: One of unit|integration|api|e2e|contract|performance|security
        source_code: Source code to analyze (optional)
        requirements_text: Requirements, user stories, or AC text (optional)
        language: Override language detection (optional)
        framework: Override framework detection (optional)
        file_path: Hint for language detection via file extension (optional)
        project_dir: Absolute path to caller's project root. Registry and reports
                     are stored under <project_dir>/.utf/. Defaults to cwd.

    Returns:
        Dict with: tests, traceability_matrix, coverage_summary,
                   suite_code, gaps, recommendations, validation_errors
    """
    if not source_code and not requirements_text:
        return {
            "error": "Provide at least one of: source_code or requirements_text",
            "tests": [],
            "validation_errors": ["No input provided"],
        }

    from pathlib import Path as _Path
    cwd = _Path(project_dir) if project_dir else None

    output: EngineOutput = run_engine(
        source_code=source_code,
        requirements_text=requirements_text,
        test_type=test_type,
        language=language,
        framework=framework,
        file_path=file_path,
        cwd=cwd,
    )

    # Serialize tests
    tests_out = []
    for t in output.tests:
        tests_out.append({
            "test_id": t.test_id,
            "why_generated": t.why_generated,
            "requirement_mapping": t.requirement_mapping,
            "how_it_exercises": t.how_it_exercises,
            "coverage_contribution": t.coverage_contribution,
            "expected_outcome": t.expected_outcome,
            "gaps_missing": t.gaps_missing,
            "meaningfulness_check": t.meaningfulness_check,
            "rendered_code": t.rendered_code,
            "validation_score": round(t.validation_score, 3),
            "validation_passed": t.validation_passed,
            "validation_violations": t.validation_violations,
        })

    # Serialize traceability
    traceability_out = [
        {
            "requirement_id": e.requirement_id,
            "test_ids": e.test_ids,
            "coverage_status": e.coverage_status,
            "risk_level": e.risk_level,
            "gaps": e.gaps,
        }
        for e in output.traceability_matrix
    ]

    # Full suite code is in first passing test's rendered_code (set by rule_engine)
    suite_code = output.tests[0].rendered_code if output.tests else ""

    blocked = bool(output.validation_errors) and not output.suite_validation.get("suite_passed", False)

    # Serialize blocked tests (failed contract validation — not included in suite)
    blocked_tests_out = [
        {
            "test_id": t.test_id,
            "validation_score": round(t.validation_score, 3),
            "violations": [v for v in t.validation_violations if not v.startswith("[Soft]")],
            "soft_recommendations": [v for v in t.validation_violations if v.startswith("[Soft]")],
        }
        for t in output.blocked_tests
    ]

    return {
        "suite_code": suite_code,
        "tests": tests_out,
        "blocked_tests": blocked_tests_out,
        "traceability_matrix": traceability_out,
        "coverage_summary": output.coverage_summary,
        "suite_validation": output.suite_validation,
        "gaps": output.gaps,
        "recommendations": output.recommendations,
        "detected_language": output.detected_language,
        "detected_framework": output.detected_framework,
        "detection_confidence": output.detection_confidence,
        "validation_errors": output.validation_errors,
        "blocked": blocked,
        "total_tests_generated": len(output.tests) + len(output.blocked_tests),
        "passing_tests_count": len(output.tests),
        "blocked_tests_count": len(output.blocked_tests),
        "all_tests_valid": len(output.blocked_tests) == 0,
        # Phase 3 — implicit lifecycle fields
        "suite_contract_score": round(output.suite_contract_score, 4),
        "blocked_count": output.blocked_count,
        "report_path": output.report_path,
        # ── 3-Phase Workflow Reminder ────────────────────────────────────────────
        # These next_steps guide Copilot CLI and human engineers through the
        # mandatory register → run → import → report pipeline.
        "next_steps": (
            "Phase 1 (Contract): "
            "① Write per-method test code — each method needs its own TC-{PRJ}-{MODULE}-{NNN} "
            "comment block with all 8 sections (WHY_GENERATED, REQUIREMENT_MAPPING, "
            "HOW_IT_EXERCISES, COVERAGE_CONTRIBUTION, EXPECTED_OUTCOME, GAPS_MISSING, "
            "MEANINGFULNESS_CHECK). "
            "② Validate with validate_test_contract (score must be ≥ 0.85). "
            "③ Run utf_register.py (or register_contracts MCP tool) to upsert status=generated "
            "rows — this populates the Per-Test Contract Detail section of the report. "
            "Phase 2 (Execution): "
            "④ pytest --junit-xml=utf-tests/reports/results.xml. "
            "⑤ import_test_results(junit_xml_path=...) — upserts executed/failed rows. "
            "Phase 3 (Report): "
            "⑥ generate_report() — HTML shows both 8-section contract cards AND pass/fail. "
            "⑦ feedback_status() for gap analysis and drift alerts."
        ),
    }
