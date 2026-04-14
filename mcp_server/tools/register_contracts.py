"""
tools/register_contracts.py — MCP Tool: register_contracts
===========================================================
Parses one or more pytest test files and upserts per-method 8-section contract
records (status=generated) into the UTF registry.

This is the *registration bridge* between LLM-written test code and the UTF
report engine.  Without it, generate_report has no Per-Test Contract Detail
cards — only execution rows from import_test_results.

Design principles (modularity):
  • All parsing logic lives in _parse_methods() — testable independently.
  • All section extraction lives in _extract_sections() — one dict per method.
  • Upsert uses the existing registry_engine.upsert_tests() — no new DB code.
  • This module has zero awareness of FiberIQ or any specific project.

Usage (MCP):
    register_contracts(test_files=["utf-tests/test_fiberiq_e2e.py"],
                       project_dir="C:/...fiber-intelligence-platform")

Usage (CLI / script):
    python -m mcp_server.tools.register_contracts utf-tests/test_fiberiq_e2e.py

Mandatory 8-section comment block per test method
(supports both UPPER and legacy Title-Case formats):

    def test_example(self):
        # ─── TC-FIQ-HLT-001 ──────────────────────────────────────────────
        # WHY_GENERATED: Business rationale tied to a requirement (≥50 chars)
        # REQUIREMENT_MAPPING: REQ-E2E-001
        # HOW_IT_EXERCISES: GIVEN ... WHEN ... THEN ...
        # COVERAGE_CONTRIBUTION: Line coverage of X; ~N%
        # EXPECTED_OUTCOME: HTTP 200; body.status == "ok"
        # GAPS_MISSING: Does not test auth; no load testing
        # MEANINGFULNESS_CHECK: Meaningful — gateway for all platform tests
        # ─────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from ..registry.registry_engine import upsert_tests, get_registry

# ── Section extraction ────────────────────────────────────────────────────────

# Map section key → (upper tag pattern, legacy title-case pattern)
_SECTION_DEFS: list[tuple[str, str, str]] = [
    ("why_generated",         "WHY_GENERATED",         r"Why Generated"),
    ("requirement_mapping",   "REQUIREMENT_MAPPING",   r"Requirement"),
    ("how_it_exercises",      "HOW_IT_EXERCISES",       r"How it Exercises"),
    ("coverage_contribution", "COVERAGE_CONTRIBUTION", r"Coverage"),
    ("expected_outcome",      "EXPECTED_OUTCOME",       r"Expected Outcome"),
    ("gaps_missing",          "GAPS_MISSING",           r"Gaps"),
    ("meaningfulness_check",  "MEANINGFULNESS_CHECK",  r"Meaningfulness"),
]

# Build regex for each section — match from label to next # section or end
_SECTION_PATTERNS: list[tuple[str, re.Pattern, re.Pattern]] = []
_KEY_LIST = [sd[0] for sd in _SECTION_DEFS]

for _i, (_key, _upper, _legacy) in enumerate(_SECTION_DEFS):
    # Look-ahead: stop at next section label or closing dashes
    _lookahead = r"(?=\n\s*#\s*(?:" + "|".join(
        re.escape(sd[1]) + r"|" + sd[2]
        for sd in _SECTION_DEFS[_i + 1:]
    ) + r"|[-─]{3,})|\Z)" if _i < len(_SECTION_DEFS) - 1 else r"(?=\n\s*#\s*[-─]{3,}|\Z)"

    _upper_pat = re.compile(
        rf"{re.escape(_upper)}\s*:\s*(.+?){_lookahead}", re.DOTALL | re.IGNORECASE
    )
    _legacy_pat = re.compile(
        rf"{_legacy}\s*:\s*(.+?){_lookahead}", re.DOTALL
    )
    _SECTION_PATTERNS.append((_key, _upper_pat, _legacy_pat))

_TC_PATTERN = re.compile(r"TC-[A-Z][A-Z0-9]+-[A-Z][A-Z0-9]+-\d+|TC-[A-Z][A-Z0-9]+-\d+")


def _clean(text: str) -> str:
    """Strip comment markers and normalise whitespace."""
    lines = [ln.strip().lstrip("#").strip() for ln in text.strip().splitlines()]
    return " ".join(ln for ln in lines if ln).strip()


def _extract_sections(fn_src: str) -> dict[str, str]:
    """
    Extract 8-section data from a test method's source text.
    Tries UPPER format first; falls back to legacy Title-Case if most are empty.
    Returns a dict keyed by section name.
    """
    sections: dict[str, str] = {}
    for key, upper_pat, legacy_pat in _SECTION_PATTERNS:
        m = upper_pat.search(fn_src)
        if m:
            sections[key] = _clean(m.group(1))
        else:
            sections[key] = ""

    # Fall back to legacy format if fewer than 4 sections were found
    if sum(1 for v in sections.values() if v) < 4:
        for key, _, legacy_pat in _SECTION_PATTERNS:
            m = legacy_pat.search(fn_src)
            if m:
                sections[key] = _clean(m.group(1))

    return sections


def _score_sections(sections: dict[str, str]) -> float:
    """
    Compute contract score from extracted sections.
    Weights match test-contract.yaml: test_id=0.10 (always present) +
    why=0.10, req=0.15, how=0.20, cov=0.15, out=0.15, gap=0.10, mean=0.05.
    """
    weights = [
        ("why_generated",         0.10),
        ("requirement_mapping",   0.15),
        ("how_it_exercises",      0.20),
        ("coverage_contribution", 0.15),
        ("expected_outcome",      0.15),
        ("gaps_missing",          0.10),
        ("meaningfulness_check",  0.05),
    ]
    score = 0.10  # test_id base
    for key, w in weights:
        if sections.get(key):
            score += w
    return round(score, 3)


def _parse_methods(path: Path) -> list[dict[str, Any]]:
    """
    Parse a pytest file via AST.  For every test METHOD inside a Test class,
    extract the TC-ID and 8-section content from inline comments.
    Returns a list of contract dicts ready to pass to upsert_tests().
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    src_lines = source.splitlines()
    records: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not node.name.startswith("Test"):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not item.name.startswith("test_"):
                continue

            fn_src = "\n".join(src_lines[item.lineno - 1 : item.end_lineno])

            tc_m = _TC_PATTERN.search(fn_src)
            test_id = tc_m.group(0) if tc_m else f"TC-REG-MISC-{len(records)+1:03d}"

            sections = _extract_sections(fn_src)
            req_ids = list(set(re.findall(r"\bREQ-[A-Z0-9_.-]+", fn_src)))
            score = _score_sections(sections)

            violations: list[str] = []
            if score < 0.85:
                missing = [k for k, v in sections.items() if not v]
                violations.append(
                    f"Score {score:.2f} < 0.85. Missing: {', '.join(missing)}"
                )

            # Build the content JSON blob — registry_engine._extract_test_info()
            # reads test.get("content", "") for plain dicts, so we must include it.
            content_blob = json.dumps({
                "test_id": test_id,
                "why_generated":         sections.get("why_generated", ""),
                "requirement_mapping":   sections.get("requirement_mapping", ""),
                "how_it_exercises":      sections.get("how_it_exercises", ""),
                "coverage_contribution": sections.get("coverage_contribution", ""),
                "expected_outcome":      sections.get("expected_outcome", ""),
                "gaps_missing":          sections.get("gaps_missing", ""),
                "meaningfulness_check":  sections.get("meaningfulness_check", ""),
                "rendered_code":         fn_src,
                "validation_violations": violations,
                "class_name":            node.name,
                "function_name":         item.name,
                "source_file":           path.name,
            }, ensure_ascii=False)

            records.append({
                "test_id": test_id,
                # ── 8-section fields (for dataclass path) ──────────────────
                "why_generated":         sections.get("why_generated", ""),
                "requirement_mapping":   sections.get("requirement_mapping", ""),
                "how_it_exercises":      sections.get("how_it_exercises", ""),
                "coverage_contribution": sections.get("coverage_contribution", ""),
                "expected_outcome":      sections.get("expected_outcome", ""),
                "gaps_missing":          sections.get("gaps_missing", ""),
                "meaningfulness_check":  sections.get("meaningfulness_check", ""),
                "rendered_code":         fn_src,
                "validation_score":      score,
                "validation_passed":     score >= 0.85,
                "validation_violations": violations,
                # ── content blob (for dict path in _extract_test_info) ──────
                "content": content_blob,
                # ── registry_engine dict path extras ────────────────────────
                "requirements": req_ids,
                "score": score,
            })

    return records


def register_contracts(
    test_files: list[str],
    project_dir: Optional[str] = None,
    project_id: Optional[str] = None,
    test_type: str = "e2e",
    language: str = "python",
    framework: str = "pytest",
) -> dict[str, Any]:
    """
    Parse test files, extract per-method 8-section contract data, and upsert
    status=generated records into the UTF registry.

    This is Phase 1, Step ③ of the UTF 3-phase workflow — it must run BEFORE
    pytest so that the Per-Test Contract Detail section of generate_report has
    content to display.

    Args:
        test_files:  List of test file paths (absolute or relative to project_dir).
        project_dir: Absolute path to project root (.utf/utf.db lives here).
                     Defaults to UTF_PROJECT_DIR env var or cwd.
        project_id:  Registry project label. Defaults to project_dir basename.
        test_type:   "unit"|"integration"|"api"|"e2e"|... Default: "e2e"
        language:    "python"|"typescript"|... Default: "python"
        framework:   "pytest"|"jest"|... Default: "pytest"

    Returns:
        {
          "registered":    int   — total test methods upserted,
          "low_score":     int   — tests below 0.85 threshold (need fixing),
          "files_parsed":  list  — file paths processed,
          "registry":      str   — absolute path to utf.db,
          "summary":       list  — per-file {file, tests, low_score} dicts,
          "next_step":     str   — reminder of Phase 2,
        }
    """
    cwd = Path(project_dir) if project_dir else None
    proj = project_id or Path(cwd if cwd is not None else Path.cwd()).name

    all_records: list[dict] = []
    summary: list[dict] = []
    files_parsed: list[str] = []

    for raw_path in test_files:
        p = Path(raw_path)
        if not p.is_absolute() and cwd:
            p = cwd / p
        p = p.resolve()

        if not p.exists():
            summary.append({"file": str(p), "error": "File not found"})
            continue

        records = _parse_methods(p)
        low = [r for r in records if r["validation_score"] < 0.85]
        summary.append({
            "file": p.name,
            "tests": len(records),
            "low_score": len(low),
            "low_score_ids": [r["test_id"] for r in low],
        })
        all_records.extend(records)
        files_parsed.append(str(p))

    if all_records:
        upsert_tests(
            tests=all_records,
            test_type=test_type,
            language=language,
            framework=framework,
            project_id=proj,
            cwd=cwd,
        )

    # Resolve registry path for display
    backend = get_registry(cwd)
    registry_path = getattr(backend, "db_path", "")

    low_total = sum(s.get("low_score", 0) for s in summary if "error" not in s)

    return {
        "registered":   len(all_records),
        "low_score":    low_total,
        "files_parsed": files_parsed,
        "registry":     str(registry_path),
        "summary":      summary,
        "next_step": (
            f"Registered {len(all_records)} contract records (status=generated). "
            f"Phase 2: run pytest --junit-xml=<path> then import_test_results(<path>). "
            f"Phase 3: generate_report() to see both contract cards and pass/fail."
        ),
    }


# ── CLI shim (python -m mcp_server.tools.register_contracts <file> ...) ─────

def _cli() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m mcp_server.tools.register_contracts <test_file> ...")
        sys.exit(1)
    result = register_contracts(test_files=sys.argv[1:])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
