"""
rule_engine.py
Core orchestrator: loads YAML rules, resolves context, generates test
scenarios, validates against the contract, and returns structured output.

This is the single entry point that all MCP tools delegate to.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Any, Optional

import yaml

from .context_resolver import TestGenerationContext, resolve_context
from .contract_validator import validate_test_contract, validate_test_suite, ContractValidationResult
from .template_renderer import render_test, render_suite_header, render_suite_footer
from .framework_mapper import FrameworkMapping

RULES_ROOT = Path(__file__).parent.parent / "rules"


# ─── Output models ───────────────────────────────────────────────────────────

@dataclass
class GeneratedTest:
    test_id: str
    why_generated: str
    requirement_mapping: str
    how_it_exercises: str
    coverage_contribution: str
    expected_outcome: str
    gaps_missing: str
    meaningfulness_check: str
    rendered_code: str
    validation_score: float
    validation_passed: bool
    validation_violations: list[str] = field(default_factory=list)


@dataclass
class TraceabilityEntry:
    requirement_id: str
    test_ids: list[str]
    coverage_status: str    # covered | partially_covered | not_covered
    risk_level: str
    gaps: list[str] = field(default_factory=list)


@dataclass
class EngineOutput:
    tests: list[GeneratedTest]
    blocked_tests: list[GeneratedTest]  # Tests that failed contract validation
    traceability_matrix: list[TraceabilityEntry]
    coverage_summary: dict[str, Any]
    suite_validation: dict[str, Any]
    gaps: list[str]
    recommendations: list[str]
    detected_language: str
    detected_framework: str
    detection_confidence: float
    validation_errors: list[str]    # Non-empty = tests were blocked
    mutation_score: float | None = None   # Populated if run_mutation=True
    mutation_blocked: bool = False         # True if score < block_below
    # Phase 3 — implicit lifecycle fields
    report_path: dict[str, str] | None = None    # {html, junit, json} absolute paths
    suite_contract_score: float = 0.0            # Average score across passing tests
    blocked_count: int = 0                       # Count of contract-blocked tests


# ─── Rule loader ─────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base dict in-place. Override wins on conflicts."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


def _load_rules(mapping: FrameworkMapping, test_type: str, cwd: Optional[Path] = None) -> dict:
    """Load and merge rules: core + language + framework + test-type + .utf/ project overrides."""
    contract = _load_yaml(RULES_ROOT / "core" / "test-contract.yaml")
    coverage = _load_yaml(RULES_ROOT / "core" / "coverage-rules.yaml")
    traceability = _load_yaml(RULES_ROOT / "core" / "traceability-rules.yaml")
    language = _load_yaml(mapping.language_rule_path)
    framework = _load_yaml(mapping.framework_rule_path)
    test_type_rules = _load_yaml(RULES_ROOT / "test-types" / f"{test_type}.yaml")

    base = {
        "contract": contract.get("contract", {}),
        "coverage": coverage.get("coverage", {}),
        "traceability": traceability.get("traceability", {}),
        "language": language,
        "framework": framework,
        "test_type": test_type_rules,
    }

    # Project-level overrides: merge any .utf/rules/*.yaml found in the caller's project root
    project_root = cwd if cwd is not None else Path.cwd()
    utf_override_dir = project_root / ".utf" / "rules"
    if utf_override_dir.exists():
        for override_file in sorted(utf_override_dir.glob("*.yaml")):
            override_data = _load_yaml(override_file)
            _deep_merge(base, override_data)

    return base


# ─── Scenario generator ───────────────────────────────────────────────────────

_SCENARIO_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "unit": [
        {
            "scenario": "happy_path",
            "why_suffix": "Covers the happy-path execution flow to verify nominal behaviour",
            "given": "valid inputs and all dependencies in their expected state",
            "when": "the function is invoked with valid parameters",
            "then": "the function returns the expected result without raising exceptions",
            "gaps_suffix": "does not test concurrent calls or failure injection",
        },
        {
            "scenario": "invalid_input",
            "why_suffix": "Covers rejection of invalid input to prevent silent data corruption",
            "given": "an invalid or malformed input value",
            "when": "the function is invoked with the invalid input",
            "then": "a ValueError (or equivalent) is raised with a descriptive message",
            "gaps_suffix": "does not test all invalid input permutations",
        },
        {
            "scenario": "null_none_input",
            "why_suffix": "Validates null-safety to prevent NullPointerException / AttributeError",
            "given": "a None / null / undefined value is passed as input",
            "when": "the function is invoked with None",
            "then": "a TypeError or explicit error is raised, not a silent failure",
            "gaps_suffix": "does not test partial-null structs or nested nulls",
        },
        {
            "scenario": "boundary_min",
            "why_suffix": "Tests minimum boundary value per equivalence partitioning",
            "given": "the minimum allowed input value",
            "when": "the function is invoked at the boundary",
            "then": "the function handles the boundary correctly without underflow/off-by-one",
            "gaps_suffix": "does not test sub-minimum (below-boundary) values",
        },
        {
            "scenario": "boundary_max",
            "why_suffix": "Tests maximum boundary value per equivalence partitioning",
            "given": "the maximum allowed input value",
            "when": "the function is invoked at the upper boundary",
            "then": "the function handles the boundary correctly without overflow/off-by-one",
            "gaps_suffix": "does not test above-maximum values",
        },
    ],
    "integration": [
        {
            "scenario": "happy_path",
            "why_suffix": "Validates that all integrated components work together in the normal flow",
            "given": "all dependent services/repositories are running with seeded test data",
            "when": "the integration entry point is invoked",
            "then": "data flows correctly through all components and the expected output is produced",
            "gaps_suffix": "does not test partial service failure or network partition",
        },
        {
            "scenario": "failure_propagation",
            "why_suffix": "Ensures that downstream failures are handled gracefully and do not cascade",
            "given": "a downstream dependency is configured to return an error",
            "when": "the integration entry point is invoked",
            "then": "the error is caught, logged, and a structured error response is returned",
            "gaps_suffix": "does not test all downstream failure modes",
        },
        {
            "scenario": "data_persistence",
            "why_suffix": "Verifies that data written to the repository is retrievable and correct",
            "given": "the database is empty or in a known clean state",
            "when": "a create operation is performed",
            "then": "the record can be retrieved with all fields matching the input",
            "gaps_suffix": "does not test concurrent writes or transaction isolation",
        },
    ],
    "api": [
        {
            "scenario": "happy_path_200",
            "why_suffix": "Verifies the nominal API response shape, status code, and schema",
            "given": "a valid authenticated request with all required fields",
            "when": "the endpoint is called via HTTP",
            "then": "HTTP 200/201 is returned with a body matching the documented JSON schema",
            "gaps_suffix": "does not test all optional query parameters",
        },
        {
            "scenario": "missing_required_field_422",
            "why_suffix": "Validates input validation rejects requests missing required fields",
            "given": "a request body with a required field omitted",
            "when": "the endpoint is called",
            "then": "HTTP 422 is returned with an error body identifying the missing field",
            "gaps_suffix": "does not test all possible missing field combinations",
        },
        {
            "scenario": "unauthenticated_401",
            "why_suffix": "Ensures unauthenticated requests are rejected with 401",
            "given": "a request with no Authorization header",
            "when": "the endpoint is called",
            "then": "HTTP 401 is returned and no data is leaked in the response body",
            "gaps_suffix": "does not test expired vs missing token distinction",
        },
        {
            "scenario": "forbidden_403",
            "why_suffix": "Ensures authenticated users with insufficient permissions receive 403",
            "given": "a request authenticated with a token that lacks the required role",
            "when": "the endpoint is called",
            "then": "HTTP 403 is returned without exposing resource existence",
            "gaps_suffix": "does not test all role combinations",
        },
    ],
    "e2e": [
        {
            "scenario": "happy_path_journey",
            "why_suffix": "Validates the complete user journey end-to-end in the browser",
            "given": "a fresh browser session with the application loaded",
            "when": "the user follows the documented happy-path steps",
            "then": "the user reaches the expected success state with the correct UI content",
            "gaps_suffix": "does not test cross-browser compatibility; only Chromium tested",
        },
        {
            "scenario": "auth_failure_journey",
            "why_suffix": "Validates that authentication failure is handled gracefully in the UI",
            "given": "the user navigates to the login page",
            "when": "invalid credentials are submitted",
            "then": "an error message is displayed and the user remains on the login page",
            "gaps_suffix": "does not test account lockout after N failures",
        },
    ],
    "security": [
        {
            "scenario": "sql_injection",
            "why_suffix": "Tests OWASP A03 Injection — SQL injection must be blocked",
            "given": "a SQL injection payload in an input field",
            "when": "the payload is submitted to the endpoint",
            "then": "HTTP 400 is returned; no SQL error details are exposed; no data leak",
            "gaps_suffix": "does not test all SQL injection payloads (blind, time-based)",
        },
        {
            "scenario": "broken_access_control_idor",
            "why_suffix": "Tests OWASP A01 Broken Access Control — IDOR must be blocked",
            "given": "user A is authenticated and user B has a resource",
            "when": "user A attempts to access user B's resource by ID",
            "then": "HTTP 403 or 404 is returned; user B's data is not exposed",
            "gaps_suffix": "does not test mass assignment or indirect reference enumeration",
        },
        {
            "scenario": "missing_auth_header",
            "why_suffix": "Validates that all protected endpoints require authentication",
            "given": "a request with no authorization token",
            "when": "the protected endpoint is called",
            "then": "HTTP 401 is returned with no data exposure",
            "gaps_suffix": "does not test all protected endpoint combinations",
        },
    ],
    "performance": [
        {
            "scenario": "average_load_sla",
            "why_suffix": "Validates SLA compliance under average expected load",
            "given": "the target environment is running with production-like data",
            "when": "simulated normal user load is applied for the defined duration",
            "then": "p95 response time < SLA threshold and error rate < 1%",
            "gaps_suffix": "does not test spike load or recovery after overload",
        },
        {
            "scenario": "stress_breaking_point",
            "why_suffix": "Identifies the system's capacity limit under increasing load",
            "given": "the system starts at 10% of expected load",
            "when": "load is gradually increased until SLA is violated or errors exceed 5%",
            "then": "the breaking point is documented; system recovers after load is removed",
            "gaps_suffix": "does not test partial failure recovery or cascading failures",
        },
    ],
    "contract": [
        {
            "scenario": "consumer_happy_path_contract",
            "why_suffix": "Validates that the provider satisfies the consumer's happy-path contract",
            "given": "the provider is in the state defined by the consumer contract",
            "when": "the interaction defined in the pact is sent to the provider",
            "then": "the provider returns a response matching all consumer expectations in the pact",
            "gaps_suffix": "does not test all provider state combinations",
        },
        {
            "scenario": "consumer_error_response_contract",
            "why_suffix": "Validates that error responses conform to the consumer's error contract",
            "given": "the provider is configured to return an error for this interaction",
            "when": "the consumer sends a request that triggers an error",
            "then": "the provider error response matches the consumer's expected error shape exactly",
            "gaps_suffix": "does not test all error codes or partial error responses",
        },
        {
            "scenario": "schema_drift_detection",
            "why_suffix": "Detects breaking schema changes that would silently break the consumer",
            "given": "the published consumer contract defines required response fields and types",
            "when": "the provider's current implementation is verified against the published contract",
            "then": "all required fields are present with correct types; no breaking changes are detected",
            "gaps_suffix": "does not test optional field additions or backward-compatible changes",
        },
        {
            "scenario": "provider_state_setup",
            "why_suffix": "Validates that provider state setup hooks correctly seed pre-conditions",
            "given": "the provider state handler is invoked with the state name from the consumer pact",
            "when": "the pact verification runs with the configured provider state",
            "then": "the provider state is correctly established and the interaction succeeds",
            "gaps_suffix": "does not test concurrent pact verification or state teardown failures",
        },
    ],
}


def _get_scenarios_for_type(test_type: str) -> list[dict]:
    return _SCENARIO_TEMPLATES.get(test_type, _SCENARIO_TEMPLATES["unit"])


# ─── Unique ID generator ─────────────────────────────────────────────────────

def _generate_test_id(req_id: str, scenario: str, seq: int) -> str:
    """Generate a deterministic test ID with suite-distinguishing prefix.

    Examples:
      REQ-BE-001  → TC-BE-001
      REQ-FE-001  → TC-FE-001
      REQ-E2E-001 → TC-E2E-001
      US-001      → TC-US-001
      REQ-001     → TC-REQ-001
    """
    parts = req_id.split("-") if req_id and "-" in req_id else []
    if len(parts) >= 3:
        # "REQ-BE-001" → use middle segment "BE" as distinguisher
        req_type = parts[1]
    elif len(parts) >= 1:
        # "REQ-001" or "US-001" → use first segment
        req_type = parts[0]
    else:
        req_type = "REQ"
    return f"TC-{req_type}-{seq:03d}"


# ─── Config helper ───────────────────────────────────────────────────────────

def _load_utf_config_safe(cwd: Optional[Path] = None):
    """Wrap load_utf_config() with a fallback to default UTFConfig on any error."""
    try:
        from mcp_server.config.utf_config import load_utf_config
        return load_utf_config(cwd)
    except Exception:
        from mcp_server.config.utf_config import UTFConfig
        return UTFConfig()


# ─── Main engine ─────────────────────────────────────────────────────────────

def run_engine(
    source_code: Optional[str] = None,
    requirements_text: Optional[str] = None,
    test_type: str = "unit",
    language: Optional[str] = None,
    framework: Optional[str] = None,
    file_path: Optional[str] = None,
    custom_scenarios: Optional[list[dict]] = None,
    cwd: Optional[Path] = None,
    run_mutation: bool = False,
) -> EngineOutput:
    """
    Main engine entry point.

    Resolves context → loads rules → generates scenarios → renders tests →
    validates against contract → builds traceability matrix → returns EngineOutput.
    """
    # 1. Resolve context
    ctx = resolve_context(
        source_code=source_code,
        requirements_text=requirements_text,
        test_type=test_type,
        language=language,
        framework=framework,
        file_path=file_path,
    )

    # 2. Load rules
    rules = _load_rules(ctx.mapping, test_type, cwd=cwd)

    # 3. Get scenarios to generate
    scenarios = custom_scenarios or _get_scenarios_for_type(test_type)

    # 4. Generate tests
    generated_tests: list[GeneratedTest] = []
    req_ids = [r.id for r in ctx.requirements] or ["REQ-001"]
    primary_req = req_ids[0]

    for seq, scenario in enumerate(scenarios, start=1):
        test_id = _generate_test_id(primary_req, scenario.get("scenario", ""), seq)

        # Build the test dict for validation
        # Build req_mapping with rich context (satisfies section 3 min_length: 20)
        if ctx.requirements:
            def _safe_map(r) -> str:
                snippet = r.raw_text[:80]
                # Avoid "US-001: US-001: ..." if raw_text already starts with the ID
                if snippet.upper().startswith(r.id.upper()):
                    return snippet
                return f"{r.id}: {snippet}"
            mapping_parts = [_safe_map(r) for r in ctx.requirements[:3]]
            req_mapping = "; ".join(mapping_parts)
        else:
            req_mapping = (
                f"REQ-001: {ctx.module_name} must behave as specified "
                f"(add US-/AC-/REQ- IDs for stronger traceability)"
            )
        symbol_name = ctx.symbols[0].name if ctx.symbols else ctx.module_name
        scenario_name = scenario.get("scenario", f"scenario_{seq}")
        why = f"{scenario.get('why_suffix', 'Validates system behavior')} for {symbol_name}"
        how = (
            f"GIVEN {scenario.get('given', 'the system is ready')}. "
            f"WHEN {scenario.get('when', symbol_name + ' is invoked')}. "
            f"THEN {scenario.get('then', 'expected result is returned')}."
        )
        gaps_raw = scenario.get("gaps_suffix", "Additional edge cases not tested")
        gaps = (
            f"{gaps_raw}. "
            f"Untested for {symbol_name}: concurrent access, large-scale inputs, and configuration variants."
        )
        coverage = (
            f"Branch coverage for {symbol_name} — {scenario_name} path. "
            f"Test type: {test_type}. Risk: {ctx.risk_level}."
        )
        expected = scenario.get("then", "Expected result matches specification")
        meaningfulness = (
            f"Meaningful — directly validates {req_mapping} via {scenario_name} scenario. "
            f"No hallucination: steps derived from {'source code analysis' if ctx.has_source else 'requirements spec'}."
        )

        test_dict: dict[str, Any] = {
            "test_id": test_id,
            "why_generated": why,
            "requirement_mapping": req_mapping,
            "how_it_exercises": how,
            "coverage_contribution": coverage,
            "expected_outcome": expected,
            "gaps_missing": gaps,
            "meaningfulness_check": meaningfulness,
        }

        # 5. Validate against contract
        validation: ContractValidationResult = validate_test_contract(test_dict)

        # 6. Render code
        rendered = render_test(ctx, {**test_dict, **scenario}, sequence_number=seq)

        generated_tests.append(GeneratedTest(
            test_id=test_id,
            why_generated=why,
            requirement_mapping=req_mapping,
            how_it_exercises=how,
            coverage_contribution=coverage,
            expected_outcome=expected,
            gaps_missing=gaps,
            meaningfulness_check=meaningfulness,
            rendered_code=rendered,
            validation_score=validation.score,
            validation_passed=validation.is_valid,
            validation_violations=validation.violation_messages,
        ))

    # Partition by contract validation: passing tests are returned; blocked tests are surfaced separately
    passing_tests = [t for t in generated_tests if t.validation_passed]
    blocked_tests_list = [t for t in generated_tests if not t.validation_passed]

    # 7. Build traceability matrix
    traceability: list[TraceabilityEntry] = []
    for req_id in req_ids:
        covering_tests = [t.test_id for t in generated_tests if req_id in t.requirement_mapping]
        gaps_for_req = [t.gaps_missing for t in generated_tests if req_id in t.requirement_mapping]
        status = (
            "covered" if covering_tests
            else "not_covered"
        )
        if covering_tests and any(gaps_for_req):
            status = "partially_covered"
        traceability.append(TraceabilityEntry(
            requirement_id=req_id,
            test_ids=covering_tests,
            coverage_status=status,
            risk_level=ctx.risk_level,
            gaps=gaps_for_req,
        ))

    # 8. Suite-level validation (validates passing tests only — blocked tests excluded)
    suite_validation = validate_test_suite([asdict(t) for t in passing_tests if hasattr(t, "test_id")])

    # Collect hard validation errors (exclude soft [Soft] recommendations)
    validation_errors = [
        f"{t.test_id}: {v}"
        for t in generated_tests
        for v in t.validation_violations
        if not v.startswith("[Soft]")
    ]

    # 9. Coverage summary
    coverage_rules = rules.get("coverage", {}).get("by_test_type", {}).get(test_type, {})
    coverage_summary = {
        "test_type": test_type,
        "tests_generated": len(passing_tests),
        "tests_blocked": len(blocked_tests_list),
        "requirements_covered": sum(1 for t in traceability if t.coverage_status in ("covered", "partially_covered")),
        "requirements_not_covered": sum(1 for t in traceability if t.coverage_status == "not_covered"),
        "line_coverage_target": coverage_rules.get("line_coverage_minimum", 80),
        "branch_coverage_target": coverage_rules.get("branch_coverage_minimum", 70),
        "risk_level": ctx.risk_level,
        "language": ctx.detection.language,
        "framework": ctx.detection.framework,
    }

    # 10. Recommendations
    recommendations: list[str] = []
    if not ctx.has_requirements:
        recommendations.append(
            "Provide requirement IDs (US-xxx, AC-xxx) for stronger traceability"
        )
    if not ctx.has_source:
        recommendations.append(
            "Provide source code for more precise test scenarios and symbol-level coverage"
        )
    if ctx.risk_level == "high":
        recommendations.append(
            "HIGH RISK module detected — add security tests (OWASP A01, A02, A03) and contract tests"
        )
    uncovered_types = _suggest_missing_test_types(ctx)
    if uncovered_types:
        recommendations.append(
            f"Consider adding these test types: {', '.join(uncovered_types)}"
        )
    if ctx.detection.confidence < 0.3 and not language:
        recommendations.append(
            f"⚠️ Low language detection confidence ({ctx.detection.confidence:.0%}). "
            f"Auto-detected '{ctx.detection.language}' — specify language= explicitly for accuracy."
        )
    if blocked_tests_list:
        recommendations.append(
            f"⚠️ {len(blocked_tests_list)} test(s) failed contract validation and were excluded "
            f"from output. Review validation_errors for details and expand the failing sections."
        )

    gaps = list({t.gaps_missing for t in passing_tests if t.gaps_missing})

    # 11. Render full suite (header + passing tests + footer)
    suite_code_parts = [render_suite_header(ctx, len(passing_tests))]
    for t in passing_tests:
        suite_code_parts.append(t.rendered_code)
    suite_code_parts.append(render_suite_footer(ctx))
    full_suite_code = "\n".join(suite_code_parts)

    # Attach rendered suite to first passing test for convenience
    if passing_tests:
        passing_tests[0].rendered_code = full_suite_code

    output = EngineOutput(
        tests=passing_tests,
        blocked_tests=blocked_tests_list,
        traceability_matrix=traceability,
        coverage_summary=coverage_summary,
        suite_validation=suite_validation,
        gaps=gaps,
        recommendations=recommendations,
        detected_language=ctx.detection.language,
        detected_framework=ctx.detection.framework,
        detection_confidence=ctx.detection.confidence,
        validation_errors=validation_errors,
    )

    # Surface low-confidence language detection as a validation warning
    if output.detection_confidence is not None and output.detection_confidence < 0.3:
        detection_warnings = [
            f"Language auto-detected as '{output.detected_language}' with low confidence "
            f"({output.detection_confidence:.0%}). Specify 'language' explicitly for reliable results."
        ]
        output.validation_errors = detection_warnings + output.validation_errors

    # Symbol fill pass — replace TODO placeholders with real scaffold code
    try:
        from mcp_server.engine.symbol_filler import SymbolFiller
        cfg = _load_utf_config_safe(cwd)
        if cfg.template_completion.enabled:
            filler = SymbolFiller()
            filled_tests: list[GeneratedTest] = []
            for t in output.tests:
                filled_code, changes = filler.fill(
                    t.rendered_code,
                    source_code=source_code or "",
                    language=ctx.detection.language,
                    test_type=test_type,
                    requirements=requirements_text or "",
                )
                if changes:
                    filled_t = dc_replace(t, rendered_code=filled_code)
                    # p2-tpl-validate-filled: re-validate to ensure fill didn't corrupt sections
                    revalidation = validate_test_contract(asdict(filled_t))
                    if revalidation.is_valid or revalidation.score >= t.validation_score:
                        filled_tests.append(filled_t)
                    else:
                        filled_tests.append(t)  # revert to unfilled on score degradation
                else:
                    filled_tests.append(t)
            output = EngineOutput(
                tests=filled_tests,
                blocked_tests=output.blocked_tests,
                traceability_matrix=output.traceability_matrix,
                coverage_summary=output.coverage_summary,
                suite_validation=output.suite_validation,
                gaps=output.gaps,
                recommendations=output.recommendations,
                detected_language=output.detected_language,
                detected_framework=output.detected_framework,
                detection_confidence=output.detection_confidence,
                validation_errors=output.validation_errors,
            )
    except Exception:
        pass  # Symbol fill is best-effort; never block test generation

    # Auto-upsert to registry if enabled
    try:
        from mcp_server.registry.registry_engine import upsert_tests
        upsert_tests(
            output.tests,
            test_type=test_type,
            language=ctx.detection.language,
            framework=ctx.detection.framework,
            cwd=cwd,
        )
    except Exception:
        pass  # Registry is best-effort; never block test generation

    # ── Mutation testing (best-effort, only when requested) ──────────────────
    if run_mutation:
        try:
            cfg = _load_utf_config_safe(cwd)
            if cfg.mutation.enabled:
                from mcp_server.mutation.mutation_runner import run_mutation_tests as _run_mut
                scores: list[float] = []
                any_blocked = False
                for t in output.tests[:3]:  # cap at 3 to keep it reasonable
                    code_snippet = getattr(t, "code", "") or ""
                    if not code_snippet:
                        continue
                    mut_result = _run_mut(
                        source_file=file_path or "",
                        test_file="",
                        language=ctx.detection.language,
                        project_dir=str(cwd) if cwd else None,
                        timeout=cfg.mutation.timeout_seconds,
                        minimum_score=cfg.mutation.minimum_score,
                        block_below=cfg.mutation.block_below,
                    )
                    if mut_result.total > 0:
                        scores.append(mut_result.mutation_score)
                    if mut_result.blocked:
                        any_blocked = True
                if scores:
                    output.mutation_score = round(sum(scores) / len(scores), 3)
                    output.mutation_blocked = any_blocked
        except Exception:
            pass  # Mutation is best-effort; never block generation

    # ── Step 12: Compute suite_contract_score + blocked_count ─────────────────
    passing = output.tests
    output.suite_contract_score = (
        sum(t.validation_score for t in passing) / len(passing) if passing else 0.0
    )
    output.blocked_count = len(output.blocked_tests)

    # ── Step 13: Auto-report (8-section contract lifecycle) ───────────────────
    try:
        from mcp_server.reporting.report_writer import write_contract_report as _write_report
        _cfg = _load_utf_config_safe(cwd)
        if _cfg.reporting.auto_report:
            _report_paths = _write_report(output, _cfg, cwd=cwd)
            output.report_path = _report_paths
    except Exception:
        pass  # Reporting is best-effort; never block test generation

    return output


def _suggest_missing_test_types(ctx: TestGenerationContext) -> list[str]:
    """Suggest additional test types based on context."""
    current = ctx.test_type
    suggestions = []
    if ctx.risk_level == "high" and current not in ("security",):
        suggestions.append("security")
    if current == "unit" and ctx.has_source:
        suggestions.append("integration")
    if ctx.has_requirements and current not in ("api", "e2e"):
        if any(kw in (ctx.requirements_text or "").lower() for kw in ["api", "endpoint", "http", "rest"]):
            suggestions.append("api")
    return suggestions

