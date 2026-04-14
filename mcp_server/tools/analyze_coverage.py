"""
analyze_coverage.py — MCP Tool: analyze_coverage
Analyzes test suite coverage and returns gap analysis + recommendations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

RULES_ROOT = Path(__file__).parent.parent.parent / "rules"


def analyze_coverage(
    tests: list[dict[str, Any]],
    source_code: Optional[str] = None,
    test_type: str = "unit",
    language: Optional[str] = None,
) -> dict[str, Any]:
    """
    Analyze coverage of a test suite.

    Args:
        tests: List of test dicts (with test_id, coverage_contribution, gaps_missing)
        source_code: Source code to extract uncovered symbols (optional)
        test_type: Test type for threshold lookup
        language: Language for threshold lookup

    Returns:
        coverage_report, uncovered_paths, recommendations, thresholds
    """
    # Load coverage rules
    coverage_rules_path = RULES_ROOT / "core" / "coverage-rules.yaml"
    with open(coverage_rules_path, encoding="utf-8") as f:
        coverage_rules = yaml.safe_load(f).get("coverage", {})

    type_rules = coverage_rules.get("by_test_type", {}).get(test_type, {})
    defaults = coverage_rules.get("defaults", {})

    line_threshold = type_rules.get("line_coverage_minimum", defaults.get("line_coverage_minimum", 80))
    branch_threshold = type_rules.get("branch_coverage_minimum", defaults.get("branch_coverage_minimum", 70))

    # Collect all coverage mentions from tests
    covered_paths: list[str] = []
    all_gaps: list[str] = []
    test_types_seen: set[str] = set()

    for t in tests:
        cov = t.get("coverage_contribution", "")
        if cov:
            covered_paths.append(cov)

        gaps = t.get("gaps_missing", "")
        if gaps:
            all_gaps.append(gaps)

        test_types_seen.add(t.get("test_type", test_type))

    # Extract symbols from source code (if provided)
    uncovered_symbols: list[str] = []
    if source_code:
        import re
        all_symbols = re.findall(r"(?:def|function|func)\s+(\w+)", source_code)
        covered_symbols = set()
        for path in covered_paths:
            for sym in all_symbols:
                if sym.lower() in path.lower():
                    covered_symbols.add(sym)
        uncovered_symbols = [s for s in all_symbols if s not in covered_symbols and not s.startswith("_")]

    # Build recommendations
    recommendations: list[str] = []

    if uncovered_symbols:
        recommendations.append(
            f"Add tests for uncovered symbols: {', '.join(uncovered_symbols[:5])}"
            + (" (and more)" if len(uncovered_symbols) > 5 else "")
        )

    # Analyze gaps for common missing patterns
    gap_text = " ".join(all_gaps).lower()

    if "concurrent" in gap_text:
        recommendations.append("Add concurrency tests — gaps mention concurrent execution")
    if "timeout" in gap_text or "slow" in gap_text:
        recommendations.append("Add timeout/slow response tests")
    if "null" in gap_text or "none" in gap_text:
        recommendations.append("Add null/None/undefined input tests")
    if "boundary" in gap_text or "edge" in gap_text:
        recommendations.append("Add boundary/edge case tests")
    if "security" not in test_types_seen and test_type not in ("security",):
        recommendations.append("Consider adding security tests for authentication and injection vulnerabilities")
    if "performance" not in test_types_seen and test_type not in ("performance",):
        recommendations.append("Consider adding performance tests for critical paths")

    # Estimate coverage (heuristic when actual tool data not available)
    estimated_line_pct = min(100, len(tests) * 15)  # rough heuristic
    estimated_branch_pct = min(100, len(tests) * 12)

    meets_line_threshold = estimated_line_pct >= line_threshold
    meets_branch_threshold = estimated_branch_pct >= branch_threshold

    return {
        "test_type": test_type,
        "total_tests_analyzed": len(tests),
        "covered_paths": covered_paths,
        "uncovered_symbols": uncovered_symbols,
        "all_gaps_identified": list(set(all_gaps)),
        "thresholds": {
            "line_coverage_minimum": line_threshold,
            "branch_coverage_minimum": branch_threshold,
        },
        "estimated_coverage": {
            "line_pct": estimated_line_pct,
            "branch_pct": estimated_branch_pct,
            "meets_line_threshold": meets_line_threshold,
            "meets_branch_threshold": meets_branch_threshold,
        },
        "coverage_tools_to_run": type_rules.get("tools", {}).get(language or "python", []),
        "recommendations": recommendations,
        "note": (
            "Coverage percentages are heuristic estimates. "
            "Run the language-specific coverage tool for accurate measurements."
        ),
    }
