"""
validate_contract.py — MCP Tool: validate_test_contract
Validates a single test or a full suite against the 8-section contract.
"""
from __future__ import annotations

from typing import Any, Optional

from ..engine.contract_validator import (
    validate_test_contract as _validate_single,
    validate_test_suite as _validate_suite,
)


def validate_test_contract(
    test_content: Optional[str] = None,
    test_dict: Optional[dict[str, Any]] = None,
    tests_list: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Validate test(s) against the 8-section contract.

    Can receive:
    - test_dict: A single test as a dict (keys = contract section keys)
    - tests_list: A list of test dicts for suite validation
    - test_content: Raw text (parsed for section markers) — convenience input

    Returns:
        Dict with is_valid, score, missing_sections, violations, summary
    """
    if tests_list:
        result = _validate_suite(tests_list)
        return {
            "mode": "suite",
            "suite_passed": result["suite_passed"],
            "total_tests": result["total_tests"],
            "passed_tests": result["passed_tests"],
            "failed_tests": result["failed_tests"],
            "average_score": result["average_score"],
            "suite_violations": result.get("suite_violations", []),
            "test_results": result.get("test_results", []),
        }

    if test_dict:
        result = _validate_single(test_dict)
        return {
            "mode": "single",
            "is_valid": result.is_valid,
            "score": round(result.score, 3),
            "minimum_score": result.minimum_score,
            "missing_sections": result.missing_sections,
            "violation_messages": result.violation_messages,
            "recommendation": result.recommendation,
            "summary": result.summary(),
            "sections": [
                {
                    "id": s.section_id,
                    "name": s.section_name,
                    "present": s.present,
                    "valid": s.valid,
                    "score": round(s.score, 3),
                    "violations": s.violations,
                    "value_snippet": s.value_snippet,
                }
                for s in result.sections
            ],
        }

    if test_content:
        # If test_content is already a dict, use it directly
        if isinstance(test_content, dict):
            return validate_test_contract(test_dict=test_content)
        # Parse test_content text into a dict by looking for section markers
        parsed = _parse_text_to_dict(test_content)
        return validate_test_contract(test_dict=parsed)

    return {
        "error": "Provide one of: test_dict, tests_list, or test_content",
        "is_valid": False,
    }


def _parse_text_to_dict(text: str) -> dict[str, Any]:
    """
    Heuristically parse freetext test content into 8-section dict.
    Looks for patterns like 'Test ID:', 'Why Generated:', etc.
    """
    import re

    mappings = {
        "test_id": [r"test\s*id\s*[:\-]?\s*(.+)", r"TC-\w+-\d+"],
        "why_generated": [r"why\s*(generated|this\s*test)\s*[:\-]?\s*(.+)"],
        "requirement_mapping": [r"requirement\s*(mapping|mapped|links?)\s*[:\-]?\s*(.+)"],
        "how_it_exercises": [r"how\s*(it\s*exercises|the\s*test)\s*[:\-]?\s*(.+)"],
        "coverage_contribution": [r"coverage\s*(contribution)?\s*[:\-]?\s*(.+)"],
        "expected_outcome": [r"expected\s*outcome\s*[:\-]?\s*(.+)"],
        "gaps_missing": [r"(what'?s?\s*missing|gaps?)\s*[:\-]?\s*(.+)"],
        "meaningfulness_check": [r"meaningfulness\s*(check)?\s*[:\-]?\s*(.+)"],
    }

    result: dict[str, Any] = {}
    for key, patterns in mappings.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                # Get the last capturing group
                groups = [g for g in match.groups() if g]
                if groups:
                    # Take up to 500 chars, strip whitespace and comment chars
                    value = groups[-1].strip().lstrip("#/*").strip()[:500]
                    if value:
                        result[key] = value
                        break

    # Fallback: if test_id not found, try inline TC- pattern
    if "test_id" not in result:
        import re as _re
        m = _re.search(r"TC-[A-Z]+-\d+", text)
        if m:
            result["test_id"] = m.group(0)

    return result
