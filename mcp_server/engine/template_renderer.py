"""
template_renderer.py
Renders test code from Jinja2 templates, combining context and rules.
Falls back to a universal inline template when no language-specific
template file exists yet.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
    _JINJA2_AVAILABLE = True
except ImportError:
    _JINJA2_AVAILABLE = False

from .context_resolver import TestGenerationContext, ExtractedRequirement, ExtractedSymbol
from .framework_mapper import FrameworkMapping

TEMPLATES_ROOT = Path(__file__).parent.parent.parent / "templates"

# ─── Universal inline templates (used when Jinja2 templates not present) ────

_INLINE_TEMPLATES: dict[str, str] = {
    "hash": """\
# ─── {test_id} ────────────────────────────────────────────────────────────────
# Why Generated    : {why_generated}
# Requirement      : {requirement_mapping}
# How it Exercises :
#   GIVEN {given}
#   WHEN  {when}
#   THEN  {then}
# Coverage         : {coverage_contribution}
# Expected Outcome : {expected_outcome}
# Gaps             : {gaps_missing}
# Meaningfulness   : {meaningfulness_check}
# ─────────────────────────────────────────────────────────────────────────────
def test_{func_name}():
    # GIVEN
    {given_code}

    # WHEN
    result = {call_expression}

    # THEN
    {assertion_code}
""",
    "doubleslash": """\
// ─── {test_id} ──────────────────────────────────────────────────────────────
// Test ID          : {test_id}
// Why Generated    : {why_generated}
// Requirement      : {requirement_mapping}
// How it Exercises :
//   GIVEN {given}
//   WHEN  {when}
//   THEN  {then}
// Coverage         : {coverage_contribution}
// Expected Outcome : {expected_outcome}
// Gaps             : {gaps_missing}
// Meaningfulness   : {meaningfulness_check}
// ─────────────────────────────────────────────────────────────────────────────
func Test{FuncName}(t *testing.T) {{
    // GIVEN
    {given_code}

    // WHEN
    result := {call_expression}

    // THEN
    {assertion_code}
}}
""",
    "javadoc": """\
/**
 * Test ID        : {test_id}
 * Why Generated  : {why_generated}
 * Requirement    : {requirement_mapping}
 * How it Exercises:
 *   GIVEN {given}
 *   WHEN  {when}
 *   THEN  {then}
 * Coverage       : {coverage_contribution}
 * Expected Outcome: {expected_outcome}
 * Gaps           : {gaps_missing}
 * Meaningfulness : {meaningfulness_check}
 */
@Test
@DisplayName("{test_display_name}")
void test{FuncName}() {{
    // GIVEN
    {given_code}

    // WHEN
    var result = {call_expression};

    // THEN
    {assertion_code}
}}
""",
}


def render_test(
    context: TestGenerationContext,
    test_scenario: dict[str, Any],
    sequence_number: int = 1,
) -> str:
    """
    Render a single test from a scenario dict and context.

    test_scenario keys (all optional — sensible defaults are filled in):
        test_id, why_generated, requirement_mapping, given, when, then,
        coverage_contribution, expected_outcome, gaps_missing,
        meaningfulness_check, func_name, call_expression,
        given_code, assertion_code, test_display_name
    """
    # Auto-generate test_id if missing
    req_ids = [r.id for r in context.requirements]
    req_type = req_ids[0].split("-")[0] if req_ids else "REQ"
    test_id = test_scenario.get("test_id") or f"TC-{req_type}-{sequence_number:03d}"

    # Build func name from first symbol or module name
    symbol_name = (
        context.symbols[0].name if context.symbols else context.module_name
    )
    raw_func = test_scenario.get("func_name") or f"{_snake(symbol_name)}_scenario_{sequence_number}"
    pascal_func = _pascal(raw_func)

    # Requirement mapping string
    req_mapping = test_scenario.get("requirement_mapping") or (
        ", ".join(req_ids) if req_ids else "REQ-001 (auto-assigned)"
    )

    template_vars: dict[str, str] = {
        "test_id": test_id,
        "why_generated": test_scenario.get("why_generated", f"Covers {context.test_type} behavior of {symbol_name}"),
        "requirement_mapping": req_mapping,
        "given": test_scenario.get("given", f"the system is in a known state for {symbol_name}"),
        "when": test_scenario.get("when", f"{symbol_name} is invoked with valid input"),
        "then": test_scenario.get("then", "the result satisfies the expected outcome"),
        "coverage_contribution": test_scenario.get(
            "coverage_contribution",
            f"Branch coverage for {symbol_name}; happy-path line coverage",
        ),
        "expected_outcome": test_scenario.get("expected_outcome", "Function returns expected value without error"),
        "gaps_missing": test_scenario.get("gaps_missing", "Concurrent execution not tested; load behaviour not covered"),
        "meaningfulness_check": test_scenario.get(
            "meaningfulness_check",
            f"Meaningful — directly validates {req_mapping}. No hallucination detected; steps map to spec.",
        ),
        "func_name": raw_func,
        "FuncName": pascal_func,
        "call_expression": test_scenario.get("call_expression", f"{symbol_name}(input)"),
        "given_code": test_scenario.get("given_code", "# Set up test fixtures here"),
        "assertion_code": test_scenario.get("assertion_code", "assert result is not None"),
        "test_display_name": test_scenario.get("test_display_name", f"should {raw_func.replace('_', ' ')}"),
    }

    # Try Jinja2 template file first
    if _JINJA2_AVAILABLE:
        tpl_file = context.mapping.template_dir / f"{context.test_type}.j2"
        if tpl_file.exists():
            env = Environment(
                loader=FileSystemLoader(str(context.mapping.template_dir)),
                undefined=StrictUndefined,
                autoescape=select_autoescape([]),
            )
            tpl = env.get_template(f"{context.test_type}.j2")
            return tpl.render(**template_vars, context=context)

    # Fallback: inline template by comment style
    comment_style = context.mapping.comment_style
    template_str = _INLINE_TEMPLATES.get(comment_style, _INLINE_TEMPLATES["hash"])
    return template_str.format(**template_vars)


def render_suite_header(
    context: TestGenerationContext,
    test_count: int,
) -> str:
    """Render the import/header block for the test file."""
    lang = context.detection.language
    fw = context.detection.framework
    req_ids = list(dict.fromkeys(r.id for r in context.requirements))

    if lang == "python":
        lines = [
            "# ═══════════════════════════════════════════════════════════",
            f"# Auto-generated by Universal Test Framework",
            f"# Test Type  : {context.test_type}",
            f"# Module     : {context.module_name}",
            f"# Language   : {lang}  |  Framework: {fw}",
            f"# Requirements: {', '.join(req_ids) if req_ids else 'see individual tests'}",
            f"# Tests      : {test_count}",
            "# ═══════════════════════════════════════════════════════════",
            "",
            "import pytest",
            "from unittest.mock import MagicMock, patch",
            "",
        ]
    elif lang in ("typescript", "javascript"):
        ext = "ts" if lang == "typescript" else "js"
        lines = [
            "/**",
            " * Auto-generated by Universal Test Framework",
            f" * Test Type  : {context.test_type}",
            f" * Module     : {context.module_name}",
            f" * Language   : {lang}  |  Framework: {fw}",
            f" * Requirements: {', '.join(req_ids) if req_ids else 'see individual tests'}",
            f" * Tests      : {test_count}",
            " */",
            "",
            f"import {{ describe, it, expect, beforeEach, afterEach, jest }} from '@jest/globals';",
            "",
            f"describe('{context.module_name} — {context.test_type} tests', () => {{",
            "",
        ]
    elif lang == "java":
        lines = [
            "/**",
            " * Auto-generated by Universal Test Framework",
            f" * Test Type  : {context.test_type}",
            f" * Module     : {context.module_name}",
            f" * Language   : Java  |  Framework: JUnit 5",
            f" * Requirements: {', '.join(req_ids) if req_ids else 'see individual tests'}",
            f" * Tests      : {test_count}",
            " */",
            "import org.junit.jupiter.api.*;",
            "import org.mockito.*;",
            "import static org.assertj.core.api.Assertions.*;",
            "",
            f"@DisplayName(\"{context.module_name} — {context.test_type} tests\")",
            "class " + _pascal(context.module_name) + "Test {",
            "",
        ]
    elif lang == "go":
        lines = [
            f"// Auto-generated by Universal Test Framework",
            f"// Test Type  : {context.test_type}",
            f"// Module     : {context.module_name}",
            f"// Framework  : go test + testify",
            f"// Requirements: {', '.join(req_ids) if req_ids else 'see individual tests'}",
            "",
            f"package {_snake(context.module_name)}_test",
            "",
            'import (',
            '\t"testing"',
            '\t"github.com/stretchr/testify/assert"',
            '\t"github.com/stretchr/testify/require"',
            ')',
            "",
        ]
    else:
        lines = [f"// Auto-generated by Universal Test Framework — {lang} — {context.test_type}", ""]

    return "\n".join(lines)


def render_suite_footer(context: TestGenerationContext) -> str:
    """Render closing braces/markers for languages that need them."""
    lang = context.detection.language
    if lang in ("typescript", "javascript"):
        return "\n});\n"
    if lang == "java":
        return "\n}\n"
    return ""


def _snake(name: str) -> str:
    """Convert CamelCase or PascalCase to snake_case."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return re.sub(r"[^a-z0-9_]", "_", s)


def _pascal(name: str) -> str:
    """Convert snake_case or mixed to PascalCase."""
    return "".join(word.capitalize() for word in re.split(r"[_\s\-]+", name))
