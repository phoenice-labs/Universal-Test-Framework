"""
build_traceability.py — MCP Tool: build_traceability_matrix
Builds a requirements-to-tests traceability matrix.
"""
from __future__ import annotations

import re
from typing import Any

from pathlib import Path
import yaml

RULES_ROOT = Path(__file__).parent.parent.parent / "rules"

_REQ_PATTERN = re.compile(r'\b(US|AC|REQ|JIRA|BUG|NFR|SEC)-[\w\-]+', re.IGNORECASE)

_HIGH_RISK_KEYWORDS = [
    "auth", "login", "password", "payment", "pii", "encrypt", "token",
    "permission", "role", "jwt", "oauth", "session", "secret",
]


def build_traceability_matrix(
    tests: list[dict[str, Any]],
    requirements: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Build a traceability matrix from a list of test dicts.

    Args:
        tests: List of test dicts (must have test_id and requirement_mapping)
        requirements: Optional explicit list of requirement IDs to check coverage against

    Returns:
        matrix, coverage_percentage, uncovered_requirements, risk_summary
    """
    # Load traceability rules
    trc_rules_path = RULES_ROOT / "core" / "traceability-rules.yaml"
    with open(trc_rules_path, encoding="utf-8") as f:
        trc_rules = yaml.safe_load(f).get("traceability", {})

    # Extract all requirement IDs referenced in tests
    req_to_tests: dict[str, list[str]] = {}
    for test in tests:
        test_id = test.get("test_id", "UNKNOWN")
        req_mapping = test.get("requirement_mapping", "")
        found = _REQ_PATTERN.findall(req_mapping)
        for req in found:
            req_upper = req.upper()
            req_to_tests.setdefault(req_upper, []).append(test_id)

    # If explicit requirements provided, find uncovered ones
    uncovered: list[str] = []
    if requirements:
        for req in requirements:
            if req.upper() not in req_to_tests:
                uncovered.append(req.upper())

    # Build matrix entries
    matrix_entries: list[dict[str, Any]] = []
    for req_id, test_ids in req_to_tests.items():
        gaps = [
            t.get("gaps_missing", "")
            for t in tests
            if t.get("test_id") in test_ids and t.get("gaps_missing")
        ]
        status = "covered" if not gaps else "partially_covered"
        risk = _assess_req_risk(req_id)

        matrix_entries.append({
            "requirement_id": req_id,
            "test_ids": test_ids,
            "test_count": len(test_ids),
            "coverage_status": status,
            "risk_level": risk,
            "gaps": list(set(gaps)),
        })

    for req in uncovered:
        matrix_entries.append({
            "requirement_id": req,
            "test_ids": [],
            "test_count": 0,
            "coverage_status": "not_covered",
            "risk_level": _assess_req_risk(req),
            "gaps": ["No tests exist for this requirement"],
        })

    total = len(matrix_entries)
    covered_count = sum(1 for e in matrix_entries if e["coverage_status"] in ("covered", "partially_covered"))
    coverage_pct = round((covered_count / total * 100) if total > 0 else 0, 1)

    high_risk_gaps = [
        e for e in matrix_entries
        if e["risk_level"] == "high" and e["coverage_status"] != "covered"
    ]

    # Format as markdown table
    md_lines = [
        "| Requirement | Tests | Status | Risk | Gaps |",
        "|------------|-------|--------|------|------|",
    ]
    for e in matrix_entries:
        tests_str = ", ".join(e["test_ids"]) if e["test_ids"] else "—"
        gaps_str = "; ".join(e["gaps"][:1]) if e["gaps"] else "—"
        status_icon = {"covered": "✅", "partially_covered": "⚠️", "not_covered": "❌"}.get(
            e["coverage_status"], "?"
        )
        risk_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(e["risk_level"], "")
        md_lines.append(
            f"| {e['requirement_id']} | {tests_str} | {status_icon} {e['coverage_status']} | {risk_icon} {e['risk_level']} | {gaps_str[:80]} |"
        )

    return {
        "matrix": matrix_entries,
        "matrix_markdown": "\n".join(md_lines),
        "summary": {
            "total_requirements": total,
            "covered": covered_count,
            "partially_covered": sum(1 for e in matrix_entries if e["coverage_status"] == "partially_covered"),
            "not_covered": len(uncovered),
            "coverage_percentage": coverage_pct,
            "high_risk_gaps": len(high_risk_gaps),
        },
        "high_risk_uncovered": [e["requirement_id"] for e in high_risk_gaps],
        "uncovered_requirements": uncovered,
        "blocks_release": bool(uncovered) or bool(high_risk_gaps),
    }


def _assess_req_risk(req_id: str) -> str:
    """Assess risk level for a requirement based on its ID prefix."""
    prefix = req_id.split("-")[0].upper()
    if prefix == "SEC":
        return "high"
    if prefix in ("US", "AC", "REQ", "JIRA", "BUG"):
        # Check the full ID text for high-risk keywords
        if any(kw in req_id.lower() for kw in _HIGH_RISK_KEYWORDS):
            return "high"
        return "medium"
    return "low"


# Fix missing Optional import
from typing import Optional
