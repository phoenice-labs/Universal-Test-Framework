"""
server.py — Universal Test Framework MCP Server
Exposes 6 MCP tools via FastMCP.
Supports two transports:
  - stdio (default) — for local VS Code / Copilot integration
  - HTTP/SSE        — for remote/team deployment (--transport http)

Usage:
  Local:  python -m mcp_server.server
  Remote: python -m mcp_server.server --transport http --port 8765
  CLI:    utf-server             (via pyproject.toml entry point)
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any, Optional

_SERVER_START_TIME = time.monotonic()

try:
    from fastmcp import FastMCP
except ImportError:
    print(
        "FastMCP not installed. Run: pip install 'fastmcp>=3.0.0'",
        file=sys.stderr,
    )
    sys.exit(1)

from .tools.generate_tests import generate_tests as _generate_tests
from .tools.validate_contract import validate_test_contract as _validate_contract
from .tools.analyze_coverage import analyze_coverage as _analyze_coverage
from .tools.build_traceability import build_traceability_matrix as _build_traceability
from .tools.suggest_types import suggest_test_types as _suggest_types
from .tools.generate_report import generate_report as _generate_report
from .engine.language_detector import detect_language_and_framework as _detect_lang

# ─── Create the MCP server instance ─────────────────────────────────────────

mcp = FastMCP(name="Universal Test Framework")


# ─── Helper: parse markdown test content into contract dict ──────────────────

_HEADER_MAP: dict[str, str] = {
    "test id": "test_id",
    "why": "why_generated",
    "why generated": "why_generated",
    "why this test": "why_generated",
    "requirement": "requirement_mapping",
    "requirement mapping": "requirement_mapping",
    "behavior": "requirement_mapping",
    "how": "how_it_exercises",
    "how it exercises": "how_it_exercises",
    "how the test": "how_it_exercises",
    "coverage": "coverage_contribution",
    "coverage contribution": "coverage_contribution",
    "expected outcome": "expected_outcome",
    "expected": "expected_outcome",
    "gap": "gaps_missing",
    "missing": "gaps_missing",
    "what's missing": "gaps_missing",
    "meaningful": "meaningfulness_check",
    "meaningfulness": "meaningfulness_check",
}


def _parse_test_markdown(content: str) -> dict[str, Any]:
    """Parse a markdown test description into a contract dict.

    Scans for ``## Section Header`` lines and collects the text beneath each.
    Maps common header names to the 8-section contract keys.
    """
    result: dict[str, Any] = {}
    current_key: Optional[str] = None
    current_lines: list[str] = []

    def _flush() -> None:
        if current_key:
            result[current_key] = "\n".join(current_lines).strip()

    for line in content.splitlines():
        if line.startswith("##"):
            _flush()
            current_lines = []
            header_text = line.lstrip("#").strip().lower()
            current_key = _HEADER_MAP.get(header_text)
        else:
            if current_key is not None:
                current_lines.append(line)

    _flush()
    return result


# ─── Tool 1: generate_tests ───────────────────────────────────────────────────

@mcp.tool()
def generate_tests(
    test_type: str,
    source_code: Optional[str] = None,
    requirements_text: Optional[str] = None,
    language: Optional[str] = None,
    framework: Optional[str] = None,
    file_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    Generate a complete test suite satisfying the 8-section test contract.

    The framework automatically:
    - Detects language and framework from source code
    - Generates tests for happy path, failure paths, and boundary cases
    - Validates every test against the 8-section contract before returning
    - Builds a traceability matrix linking tests to requirements
    - Identifies coverage gaps and makes recommendations

    Args:
        test_type: Type of tests to generate. One of:
                   unit | integration | api | e2e | contract | performance | security
        source_code: Source code to analyze (function/class/module). Optional but recommended.
        requirements_text: User stories, acceptance criteria, Jira tickets, or requirements.
                           Include IDs like US-001, AC-2.1, REQ-042 for traceability.
        language: Override language detection. One of:
                  python | typescript | javascript | java | go | cpp
        framework: Override framework detection. One of:
                   pytest | jest | junit5 | go-test | playwright | k6
        file_path: File path hint for language detection (e.g., 'src/auth.py')

    Returns:
        suite_code: Complete executable test file
        tests: List of tests with all 8 contract sections
        traceability_matrix: Requirements → tests mapping
        coverage_summary: Coverage targets and analysis
        gaps: Identified coverage gaps
        recommendations: Suggested additional tests
        validation_errors: Non-empty if any test failed contract validation
        blocked: True if validation errors prevent output (contract enforcement)
    """
    return _generate_tests(
        test_type=test_type,
        source_code=source_code,
        requirements_text=requirements_text,
        language=language,
        framework=framework,
        file_path=file_path,
    )


# ─── Tool 2: validate_test_contract ──────────────────────────────────────────

@mcp.tool()
def validate_test_contract(
    test_content: Optional[str] = None,
    test_dict: Optional[dict[str, Any]] = None,
    tests_list: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Validate a test or test suite against the 8-section contract.

    Use this to check any existing test — generated or hand-written — for compliance.
    The contract requires all 8 sections: Test ID, Why Generated, Requirement Mapping,
    How it Exercises, Coverage Contribution, Expected Outcome, Gaps, Meaningfulness Check.

    Args:
        test_content: Raw markdown test text (paste any test here for quick validation)
        test_dict: Structured test as dict with 8-section keys
        tests_list: List of raw markdown strings for suite-level validation

    Returns:
        is_valid, score (0–1), missing_sections, violations, summary
    """
    # If a markdown string is provided, parse it into a dict first
    resolved_dict: Optional[dict[str, Any]] = test_dict
    if test_content and not test_dict:
        resolved_dict = _parse_test_markdown(test_content)

    # If tests_list is a list of strings, parse each one
    resolved_tests_list: Optional[list[dict[str, Any]]] = None
    if tests_list:
        resolved_tests_list = [
            _parse_test_markdown(item) if isinstance(item, str) else item
            for item in tests_list
        ]

    return _validate_contract(
        test_content=None,          # already converted to dict above
        test_dict=resolved_dict,
        tests_list=resolved_tests_list,
    )


# ─── Tool 3: analyze_coverage ────────────────────────────────────────────────

@mcp.tool()
def analyze_coverage(
    tests: list[dict[str, Any]],
    source_code: Optional[str] = None,
    test_type: str = "unit",
    language: Optional[str] = None,
) -> dict[str, Any]:
    """
    Analyze the coverage of a test suite and identify gaps.

    Args:
        tests: List of test dicts (output from generate_tests)
        source_code: Source code to identify uncovered symbols
        test_type: Test type for threshold lookup
        language: Language for tool recommendations

    Returns:
        covered_paths, uncovered_symbols, thresholds, recommendations
    """
    return _analyze_coverage(
        tests=tests,
        source_code=source_code,
        test_type=test_type,
        language=language,
    )


# ─── Tool 4: build_traceability_matrix ───────────────────────────────────────

@mcp.tool()
def build_traceability_matrix(
    tests: list[dict[str, Any]],
    requirements: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Build a requirements-to-tests traceability matrix.

    Args:
        tests: List of test dicts (must include test_id and requirement_mapping)
        requirements: Explicit list of requirement IDs to check coverage against

    Returns:
        matrix, matrix_markdown, summary, high_risk_uncovered, blocks_release
    """
    return _build_traceability(tests=tests, requirements=requirements)


# ─── Tool 5: suggest_test_types ──────────────────────────────────────────────

@mcp.tool()
def suggest_test_types(
    source_code: Optional[str] = None,
    requirements_text: Optional[str] = None,
) -> dict[str, Any]:
    """
    Analyze code/requirements and suggest which test types to apply.

    Args:
        source_code: Source code to analyze
        requirements_text: Requirements or user stories

    Returns:
        recommended_types with priority and rationale, risk_flags
    """
    return _suggest_types(
        source_code=source_code,
        requirements_text=requirements_text,
    )


# ─── Tool 6: detect_language_framework ───────────────────────────────────────

@mcp.tool()
def detect_language_framework(
    source_code: str,
    file_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    Detect programming language and test framework from source code.

    Args:
        source_code: Source code to analyze
        file_path: Optional file path for extension-based detection

    Returns:
        language, framework, confidence, detected_from (evidence list)
    """
    result = _detect_lang(source_code=source_code, file_path=file_path)
    return {
        "language": result.language,
        "framework": result.framework,
        "confidence": round(result.confidence, 3),
        "detected_from": result.detected_from,
        "version_hint": result.version_hint,
    }


# ─── Health / Liveness Tool ──────────────────────────────────────────────────

@mcp.tool()
def health() -> dict[str, Any]:
    """
    Health check for the Universal Test Framework MCP server.

    Returns server status, version, and uptime. Suitable for use as a
    Docker HEALTHCHECK command, Kubernetes liveness/readiness probe, or
    basic availability verification.

    Returns:
        status   : "ok" when the server is healthy
        version  : UTF semantic version string
        uptime_s : seconds the server process has been running
        tools    : number of registered MCP tools
    """
    return {
        "status": "ok",
        "service": "Universal Test Framework",
        "version": "1.0.0",
        "uptime_s": round(time.monotonic() - _SERVER_START_TIME, 1),
        "tools": 11,  # generate_tests, validate_contract, analyze_coverage,
                     # build_traceability_matrix, suggest_test_types,
                     # detect_language_framework, health, query_registry,
                     # run_tests, run_mutation_tests, feedback_status
    }


# ─── Tool 8: query_registry ───────────────────────────────────────────────────

@mcp.tool()
def query_registry(
    project_id: Optional[str] = None,
    test_type: Optional[str] = None,
    language: Optional[str] = None,
    status: Optional[str] = None,
    requirement_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Query the UTF persistent test registry.

    Args:
        project_id:     Filter by project (defaults to current directory name)
        test_type:      Filter by test type (unit | integration | api | …)
        language:       Filter by language (python | typescript | …)
        status:         Filter by status (generated | executed | failed | gap)
        requirement_id: Filter tests that cover a specific requirement ID

    Returns:
        results: matching test records, coverage_summary, gaps, total_matching
    """
    from mcp_server.registry.registry_engine import (
        query_registry as _qr,
        coverage_summary as _cs,
        gap_analysis as _ga,
    )
    results = _qr(
        project_id=project_id,
        test_type=test_type,
        language=language,
        status=status,
        requirement_id=requirement_id,
    )
    summary = _cs(project_id=project_id)
    gaps = _ga(project_id=project_id)
    return {
        "results": results,
        "coverage_summary": summary,
        "gaps": gaps,
        "total_matching": len(results.get("records", [])),
    }


# ─── Tool 9: run_tests ───────────────────────────────────────────────────────

@mcp.tool()
def run_tests(
    test_files: list[str],
    language: str,
    framework: Optional[str] = None,
    project_dir: Optional[str] = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """
    Execute test files and return structured results with CI annotations.

    Execution is always optional — controlled by UTF config. Never blocks generation.

    Args:
        test_files:      List of test file paths to execute
        language:        Language of the tests (python | typescript | javascript | java | go)
        framework:       Test framework hint (pytest | vitest | jest | junit5 | maven | gradle | go)
        project_dir:     Project root directory (defaults to cwd)
        timeout_seconds: Per-file execution timeout in seconds (default: 120)

    Returns:
        CI report with summary, per-file results, and GitHub Actions annotations
    """
    from mcp_server.execution.runner import run_tests as _run
    from mcp_server.execution.ci_reporter import format_ci_report
    from mcp_server.registry.registry_engine import get_registry
    from pathlib import Path

    results = []
    for tf in test_files:
        r = _run(
            tf,
            language=language,
            framework=framework or "",
            project_dir=project_dir,
            timeout=timeout_seconds,
        )
        results.append(r)
        # Best-effort registry update
        try:
            reg = get_registry(Path(project_dir) if project_dir else None)
            status = "executed" if r.success else "failed"
            reg  # registry reference kept for future upsert integration
        except Exception:
            pass

    report = format_ci_report(results, project_id=Path(project_dir or ".").name)
    return report


# ─── Tool 10: run_mutation_tests ─────────────────────────────────────────────

@mcp.tool()
def run_mutation_tests(
    source_file: str,
    test_file: str,
    language: str,
    project_dir: Optional[str] = None,
    timeout_seconds: int = 300,
    minimum_score: float = 0.70,
    block_below: float = 0.50,
) -> dict[str, Any]:
    """
    Run mutation testing on a source+test file pair and return coverage metrics.

    Supports mutmut (Python), Stryker (JS/TS), PIT (Java), and gremlins (Go).
    The adapter is auto-detected based on language and tool availability.

    Args:
        source_file:     Path to the source file to mutate
        test_file:       Path to the test file to run against mutants
        language:        Language of the files (python | javascript | typescript | java | go)
        project_dir:     Project root directory (defaults to cwd)
        timeout_seconds: Mutation run timeout in seconds (default: 300)
        minimum_score:   Threshold to pass (default: 0.70 = 70% killed)
        block_below:     Score below which the result is flagged as blocked (default: 0.50)

    Returns:
        adapter, mutation_score, killed, survived, total, passed_threshold,
        blocked, surviving_mutants (up to 10), duration_seconds
    """
    from mcp_server.mutation.mutation_runner import run_mutation_tests as _run
    result = _run(
        source_file=source_file,
        test_file=test_file,
        language=language,
        project_dir=project_dir,
        timeout=timeout_seconds,
        minimum_score=minimum_score,
        block_below=block_below,
    )
    return {
        "adapter": result.adapter,
        "mutation_score": result.mutation_score,
        "killed": result.killed,
        "survived": result.survived,
        "total": result.total,
        "passed_threshold": result.passed_threshold,
        "blocked": result.blocked,
        "surviving_mutants": result.surviving_mutants[:10],
        "duration_seconds": result.duration_seconds,
    }


# ─── Tool 11: feedback_status ─────────────────────────────────────────────────

@mcp.tool()
def feedback_status(
    project_id: Optional[str] = None,
    requirements: Optional[str] = None,
    check_gaps: bool = True,
    compute_trend: bool = True,
    trend_days: int = 30,
) -> dict[str, Any]:
    """
    Get UTF feedback loop status: gap analysis, coverage health, trend, and delta requirements.

    Args:
        project_id:    Project to report on (defaults to current directory name)
        requirements:  Requirements text to compare against registry for delta detection
        check_gaps:    Run gap analysis and coverage health check (default: True)
        compute_trend: Compute coverage trend over time (default: True)
        trend_days:    Number of days of history to include in trend (default: 30)

    Returns:
        gap_analysis, coverage_health, trend, and/or delta depending on arguments
    """
    from mcp_server.feedback.gap_reopener import check_and_reopen_gaps, compute_coverage_health
    from mcp_server.feedback.trend_reporter import get_coverage_trend
    from mcp_server.feedback.delta_generator import get_delta_requirements

    result: dict[str, Any] = {"project_id": project_id}

    if check_gaps:
        result["gap_analysis"] = check_and_reopen_gaps(project_id=project_id)
        result["coverage_health"] = compute_coverage_health(project_id=project_id)

    if compute_trend:
        result["trend"] = get_coverage_trend(project_id=project_id, days=trend_days)

    if requirements:
        result["delta"] = get_delta_requirements(requirements, project_id=project_id)

    return result


# ─── Tool 12: generate_report ────────────────────────────────────────────────

@mcp.tool()
def generate_report(
    formats: Optional[list[str]] = None,
    open_html: bool = False,
    project_id: Optional[str] = None,
    cwd: Optional[str] = None,
) -> dict[str, Any]:
    """
    Generate the 8-section contract compliance report (Tool #12).

    Reads test records and execution results from the registry, builds the
    contract report in the requested formats, and returns report paths + summary.

    The 8-section contract lifecycle:
      generate_tests → enforcement → auto-report (this tool on demand)
      run_tests → execution binding → generate_report for unified view

    Args:
        formats:    Output formats: subset of ["html", "junit", "json"].
                    Defaults to all three.
        open_html:  Open the HTML report in the default browser (dev mode).
        project_id: Registry project ID (defaults to current directory name).
        cwd:        Project root directory (defaults to server cwd).

    Returns:
        report_path:          {html, junit, json} absolute file paths
        suite_contract_score: Average 8-section contract score (0.0–1.0)
        sections_summary:     Per-section pass rates and averages
        blocked_count:        Tests blocked at generation time (contract < 0.85)
        exec_pass_rate:       Pass rate from run_tests (None if not run)
        trend:                Contract score trend over last 10 runs
        generated_at:         ISO timestamp
        test_count:           Total tests in this report
    """
    return _generate_report(
        formats=formats,
        open_html=open_html,
        project_id=project_id,
        cwd=cwd,
    )


# ─── CLI entry point ─────────────────────────────────────────────────────────

def cli() -> None:
    """CLI entry point for `utf-server` command."""
    parser = argparse.ArgumentParser(
        description="Universal Test Framework MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start local MCP server (stdio) for VS Code integration
  utf-server

  # Start HTTP server for team/remote use
  utf-server --transport http --port 8765

  # Start HTTP server with host binding
  utf-server --transport http --host 0.0.0.0 --port 8765
        """,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: 'stdio' for local VS Code, 'http' for remote/team (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for HTTP transport (default: 8765)",
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        print("Starting Universal Test Framework MCP Server (stdio)...", file=sys.stderr)
        mcp.run(transport="stdio")
    else:
        print(
            f"Starting Universal Test Framework MCP Server (HTTP) on {args.host}:{args.port}...",
            file=sys.stderr,
        )
        mcp.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    cli()
