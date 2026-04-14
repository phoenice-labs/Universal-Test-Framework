"""
contract_validator.py
Validates that a generated test (or test suite) satisfies the 8-section
test contract defined in rules/core/test-contract.yaml.

Returns a ContractValidationResult with a numeric score, missing sections,
and specific violation messages. Output is BLOCKED if score < minimum_score.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


_CONTRACT_PATH = Path(__file__).parent.parent.parent / "rules" / "core" / "test-contract.yaml"

# Cache the loaded contract (loaded once at module import)
_CONTRACT: Optional[dict] = None


def _load_contract() -> dict:
    global _CONTRACT
    if _CONTRACT is None:
        with open(_CONTRACT_PATH, encoding="utf-8") as f:
            _CONTRACT = yaml.safe_load(f)
    return _CONTRACT


@dataclass
class SectionValidationResult:
    section_id: int
    section_key: str
    section_name: str
    present: bool
    valid: bool
    score: float            # 0.0–1.0 contribution to total score
    violations: list[str] = field(default_factory=list)
    value_snippet: str = ""  # First 100 chars of the value


@dataclass
class ContractValidationResult:
    is_valid: bool
    score: float                        # 0.0–1.0 overall
    minimum_score: float
    sections: list[SectionValidationResult] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    violation_messages: list[str] = field(default_factory=list)
    recommendation: str = ""

    @property
    def blocked(self) -> bool:
        """Output should be blocked if score below threshold or required sections missing."""
        return not self.is_valid

    def summary(self) -> str:
        status = "✅ PASSED" if self.is_valid else "❌ BLOCKED"
        lines = [
            f"{status} — Contract Score: {self.score:.0%} (minimum: {self.minimum_score:.0%})",
        ]
        if self.missing_sections:
            lines.append(f"Missing sections: {', '.join(self.missing_sections)}")
        if self.violation_messages:
            lines.extend(f"  • {v}" for v in self.violation_messages)
        if self.recommendation:
            lines.append(f"Recommendation: {self.recommendation}")
        return "\n".join(lines)


def validate_test_contract(test_dict: dict[str, Any]) -> ContractValidationResult:
    """
    Validate a single test dict against the 8-section contract.

    Args:
        test_dict: Dict with keys matching section `key` fields from the contract.
                   e.g. {"test_id": "TC-REQ-001", "why_generated": "...", ...}

    Returns:
        ContractValidationResult
    """
    contract = _load_contract()
    sections_spec = contract["contract"]["sections"]
    minimum_score = contract["contract"]["minimum_score"]
    require_all = contract["contract"]["require_all_sections"]

    section_results: list[SectionValidationResult] = []
    missing_sections: list[str] = []
    violations: list[str] = []
    total_score = 0.0

    for spec in sections_spec:
        key = spec["key"]
        name = spec["name"]
        sid = spec["id"]
        weight = spec["score_weight"]
        validation = spec.get("validation", {})

        value = test_dict.get(key)
        present = bool(value and str(value).strip())
        section_violations: list[str] = []
        section_score = 0.0

        if not present:
            missing_sections.append(name)
            violations.append(f"Section {sid} '{name}' is missing or empty")
        else:
            val_str = str(value).strip()
            section_score = weight  # Start with full weight; deduct for violations

            # min_length
            if min_len := validation.get("min_length"):
                if len(val_str) < min_len:
                    msg = f"Section '{name}' too short ({len(val_str)} < {min_len} chars)"
                    section_violations.append(msg)
                    violations.append(msg)
                    section_score *= 0.5

            # max_length
            if max_len := validation.get("max_length"):
                if len(val_str) > max_len:
                    msg = f"Section '{name}' too long ({len(val_str)} > {max_len} chars)"
                    section_violations.append(msg)
                    section_score *= 0.9  # Minor deduction

            # pattern
            if pattern := validation.get("pattern"):
                if not re.match(pattern, val_str, re.IGNORECASE):
                    msg = f"Section '{name}' value '{val_str}' doesn't match pattern {pattern}"
                    section_violations.append(msg)
                    violations.append(msg)
                    section_score *= 0.3

            # must_not_match
            for bad_pattern in validation.get("must_not_match", []):
                if re.match(bad_pattern, val_str, re.IGNORECASE):
                    msg = f"Section '{name}' value is too generic (matched '{bad_pattern}')"
                    section_violations.append(msg)
                    violations.append(msg)
                    section_score *= 0.2

            # must_include_one_of
            required_terms = validation.get("must_include_one_of", [])
            if required_terms:
                found = any(term.lower() in val_str.lower() for term in required_terms)
                if not found:
                    msg = (
                        f"Section '{name}' must include one of: "
                        f"{required_terms[:5]} (got: '{val_str[:80]}')"
                    )
                    section_violations.append(msg)
                    violations.append(msg)
                    section_score *= 0.5

            # recommended_keywords — soft enforcement (score deduction only, not a hard fail)
            rec_keyword_groups: list[list[str]] = validation.get("recommended_keywords", [])
            if rec_keyword_groups:
                missing_groups = [
                    group for group in rec_keyword_groups
                    if not any(kw.lower() in val_str.lower() for kw in group)
                ]
                if missing_groups:
                    deduction = min(0.25, len(missing_groups) * 0.10)
                    rec_msg = (
                        f"[Soft] Section '{name}': consider including structural keywords "
                        f"{[g[0] for g in missing_groups]} "
                        f"(e.g., GIVEN/WHEN/THEN or assert/returns/expect)"
                    )
                    section_violations.append(rec_msg)
                    # Not added to violations list — soft recommendation only
                    section_score = section_score * (1.0 - deduction)

        total_score += section_score

        section_results.append(SectionValidationResult(
            section_id=sid,
            section_key=key,
            section_name=name,
            present=present,
            valid=present and not section_violations,
            score=section_score,
            violations=section_violations,
            value_snippet=(str(value or "")[:100]),
        ))

    is_valid = (
        total_score >= minimum_score
        and (not require_all or len(missing_sections) == 0)
    )

    weight_map = {spec["key"]: spec["score_weight"] for spec in sections_spec}
    recommendation = ""
    if missing_sections:
        recommendation = f"Add the following sections: {', '.join(missing_sections)}"
    elif total_score < minimum_score:
        low_sections = [
            r.section_name for r in section_results
            if r.score < weight_map.get(r.section_key, 0.10) * 0.8
        ]
        recommendation = (
            f"Improve these sections with more detail: {', '.join(low_sections[:3])}"
            if low_sections
            else "Expand all section content to meet the minimum score threshold"
        )

    return ContractValidationResult(
        is_valid=is_valid,
        score=total_score,
        minimum_score=minimum_score,
        sections=section_results,
        missing_sections=missing_sections,
        violation_messages=violations,
        recommendation=recommendation,
    )


def validate_test_suite(tests: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Validate an entire test suite.

    Returns a suite-level report including per-test results and overall pass/fail.
    """
    results = [validate_test_contract(t) for t in tests]
    all_passed = all(r.is_valid for r in results)
    avg_score = sum(r.score for r in results) / len(results) if results else 0.0

    # Check suite-level requirements
    contract = _load_contract()
    suite_reqs = contract.get("suite_requirements", {})
    suite_violations: list[str] = []

    if suite_reqs.get("require_negative_tests"):
        # Heuristic: at least one test should mention negative/failure in its why_generated
        negative_keywords = ["negative", "invalid", "failure", "error", "reject", "forbidden", "unauthorized"]
        has_negative = any(
            any(kw in str(t.get("why_generated", "")).lower() for kw in negative_keywords)
            for t in tests
        )
        if not has_negative:
            suite_violations.append("Suite is missing negative/failure scenario tests")

    if suite_reqs.get("require_boundary_tests"):
        boundary_keywords = ["boundary", "edge", "min", "max", "zero", "empty", "null", "overflow"]
        has_boundary = any(
            any(kw in str(t.get("why_generated", "")).lower() for kw in boundary_keywords)
            for t in tests
        )
        if not has_boundary:
            suite_violations.append("Suite is missing boundary/edge case tests")

    return {
        "suite_passed": all_passed and not suite_violations,
        "total_tests": len(tests),
        "passed_tests": sum(1 for r in results if r.is_valid),
        "failed_tests": sum(1 for r in results if not r.is_valid),
        "average_score": round(avg_score, 3),
        "suite_violations": suite_violations,
        "test_results": [
            {
                "test_index": i,
                "test_id": tests[i].get("test_id", f"test_{i}"),
                "is_valid": r.is_valid,
                "score": round(r.score, 3),
                "missing_sections": r.missing_sections,
                "violations": r.violation_messages,
            }
            for i, r in enumerate(results)
        ],
    }
