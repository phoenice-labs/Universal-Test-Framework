"""
mcp_server/reporting/contract_reporter.py

Canonical 8-section contract report builder.

Produces three output formats from an EngineOutput (with optional execution results):
  - HTML  : Visual KPI strip, heatmap (test × 8 sections), per-test detail cards
  - JUnit : Standard <testsuites> XML enriched with utf.contract_score properties
  - JSON  : Machine-readable summary for CI/CD consumption

All formats are generated from the same ContractReporter instance.
Works from EngineOutput alone — execution results are optional.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from xml.sax.saxutils import escape

# Section metadata (canonical order matches the 8-section contract)
_SECTION_META: list[dict[str, Any]] = [
    {"key": "test_id",              "id": 1, "name": "Test ID",               "weight": 0.10},
    {"key": "why_generated",        "id": 2, "name": "Why Generated",          "weight": 0.10},
    {"key": "requirement_mapping",  "id": 3, "name": "Requirement Mapping",    "weight": 0.15},
    {"key": "how_it_exercises",     "id": 4, "name": "How it Exercises",       "weight": 0.20},
    {"key": "coverage_contribution","id": 5, "name": "Coverage Contribution",  "weight": 0.15},
    {"key": "expected_outcome",     "id": 6, "name": "Expected Outcome",       "weight": 0.15},
    {"key": "gaps_missing",         "id": 7, "name": "Gaps / Missing",         "weight": 0.10},
    {"key": "meaningfulness_check", "id": 8, "name": "Meaningfulness Check",   "weight": 0.05},
]
_SECTION_KEYS = [s["key"] for s in _SECTION_META]
_SECTION_WEIGHTS = {s["key"]: s["weight"] for s in _SECTION_META}


@dataclass
class TestContractRecord:
    """Flattened record for a single test's 8-section contract data."""
    test_id: str
    section_scores: dict[str, float]     # key → score (0.0–1.0 contribution)
    contract_score: float                 # overall score
    violations: list[str]
    exec_status: Optional[str] = None    # passed | failed | error | skipped | None
    exec_duration_s: Optional[float] = None
    exec_output: str = ""                # stdout/stderr from test execution
    gaps_text: str = ""
    is_blocked: bool = False
    # Section content — the actual text for each of the 8 sections
    section_content: dict[str, str] = None   # key → full section text
    rendered_code: str = ""              # the generated test code

    def __post_init__(self):
        if self.section_content is None:
            self.section_content = {}


@dataclass
class ContractReport:
    """Fully computed report ready for serialisation."""
    suite_contract_score: float
    test_count: int
    blocked_count: int
    exec_pass_rate: Optional[float]       # None if execution not run
    section_pass_rates: dict[str, float]  # key → fraction of tests with full score
    section_averages: dict[str, float]    # key → average score across tests
    weakest_section: Optional[str]
    weakest_section_avg: float
    records: list[TestContractRecord]
    generated_at: str
    report_version: str = "1.0"
    language: str = ""
    framework: str = ""
    test_type: str = ""
    trend: Optional[dict[str, Any]] = None


class ContractReporter:
    """Builds HTML, JUnit XML, and JSON contract reports from EngineOutput data."""

    REPORT_VERSION = "1.0"

    def __init__(self, engine_output: Any, execution_results: Optional[list[dict]] = None):
        """
        Args:
            engine_output:     EngineOutput from run_engine()
            execution_results: Optional list of dicts from execution binding:
                               [{test_id, exec_status, exec_duration_s, contract_score, ...}]
        """
        self._output = engine_output
        self._exec_map: dict[str, dict] = {}
        if execution_results:
            for r in execution_results:
                tid = r.get("test_id", "")
                if tid:
                    self._exec_map[tid] = r
        self._report: Optional[ContractReport] = None

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def build(self) -> ContractReport:
        """Compute and cache the ContractReport."""
        if self._report is not None:
            return self._report
        self._report = self._compute_report()
        return self._report

    def to_html(self) -> str:
        """Return a self-contained HTML string for the 8-section contract report."""
        report = self.build()
        return _render_html(report)

    def to_junit_xml(self) -> str:
        """Return JUnit XML enriched with utf.contract_score properties."""
        report = self.build()
        return _render_junit(report)

    def to_json(self) -> str:
        """Return a JSON string with the machine-readable summary."""
        report = self.build()
        return _render_json(report)

    def to_summary_dict(self) -> dict[str, Any]:
        """Return a lightweight summary dict for MCP responses."""
        report = self.build()
        return {
            "suite_contract_score": round(report.suite_contract_score, 4),
            "test_count": report.test_count,
            "blocked_count": report.blocked_count,
            "exec_pass_rate": report.exec_pass_rate,
            "section_averages": {k: round(v, 4) for k, v in report.section_averages.items()},
            "weakest_section": report.weakest_section,
            "weakest_section_avg": round(report.weakest_section_avg, 4),
            "generated_at": report.generated_at,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Internal computation
    # ──────────────────────────────────────────────────────────────────────

    def _compute_report(self) -> ContractReport:
        output = self._output
        passing_tests = output.tests
        blocked_tests = getattr(output, "blocked_tests", [])
        all_tests = list(passing_tests) + list(blocked_tests)

        records: list[TestContractRecord] = []
        for t in passing_tests:
            exec_info = self._exec_map.get(t.test_id, {})
            rec = self._test_to_record(t, exec_info, is_blocked=False)
            records.append(rec)
        for t in blocked_tests:
            exec_info = self._exec_map.get(t.test_id, {})
            rec = self._test_to_record(t, exec_info, is_blocked=True)
            records.append(rec)

        # Suite-level aggregation
        passing_records = [r for r in records if not r.is_blocked]
        suite_score = (
            sum(r.contract_score for r in passing_records) / len(passing_records)
            if passing_records else 0.0
        )

        # Per-section averages over passing tests
        section_averages: dict[str, float] = {}
        section_pass_rates: dict[str, float] = {}
        for key in _SECTION_KEYS:
            weight = _SECTION_WEIGHTS[key]
            scores = [r.section_scores.get(key, 0.0) for r in passing_records]
            avg = sum(scores) / len(scores) if scores else 0.0
            section_averages[key] = avg
            # "full score" = within 5% of the section's weight
            full_threshold = weight * 0.95
            section_pass_rates[key] = (
                sum(1 for s in scores if s >= full_threshold) / len(scores)
                if scores else 0.0
            )

        weakest_key = min(section_averages, key=section_averages.get) if section_averages else None
        weakest_avg = section_averages.get(weakest_key, 0.0) if weakest_key else 0.0

        # Execution pass rate
        exec_pass_rate: Optional[float] = None
        if self._exec_map:
            total_exec = len(self._exec_map)
            passed_exec = sum(
                1 for v in self._exec_map.values() if v.get("exec_status") == "passed"
            )
            exec_pass_rate = passed_exec / total_exec if total_exec else None

        cov = getattr(output, "coverage_summary", {}) or {}

        return ContractReport(
            suite_contract_score=suite_score,
            test_count=len(passing_records),
            blocked_count=len(blocked_tests),
            exec_pass_rate=exec_pass_rate,
            section_pass_rates=section_pass_rates,
            section_averages=section_averages,
            weakest_section=weakest_key,
            weakest_section_avg=weakest_avg,
            records=records,
            generated_at=datetime.now(timezone.utc).isoformat(),
            language=getattr(output, "detected_language", ""),
            framework=getattr(output, "detected_framework", ""),
            test_type=cov.get("test_type", ""),
        )

    def _test_to_record(self, t: Any, exec_info: dict, is_blocked: bool) -> TestContractRecord:
        """Convert a GeneratedTest to a TestContractRecord."""
        # Build section_scores from per-section validation data if available
        section_scores: dict[str, float] = {}

        # Try to get per-section scores from the validation result embedded on the test
        # GeneratedTest stores validation_score (overall) and validation_violations (list)
        # We approximate per-section scores using the contract weights and violations
        overall_score = getattr(t, "validation_score", 0.0)
        violations = getattr(t, "validation_violations", [])

        # Capture all 8 section content fields
        section_content = {
            "test_id":              getattr(t, "test_id", ""),
            "why_generated":        getattr(t, "why_generated", ""),
            "requirement_mapping":  getattr(t, "requirement_mapping", ""),
            "how_it_exercises":     getattr(t, "how_it_exercises", ""),
            "coverage_contribution": getattr(t, "coverage_contribution", ""),
            "expected_outcome":     getattr(t, "expected_outcome", ""),
            "gaps_missing":         getattr(t, "gaps_missing", ""),
            "meaningfulness_check": getattr(t, "meaningfulness_check", ""),
        }

        test_dict = dict(section_content)

        # Re-validate to get per-section granular scores
        try:
            from mcp_server.engine.contract_validator import validate_test_contract
            result = validate_test_contract(test_dict)
            for sec in result.sections:
                section_scores[sec.section_key] = sec.score
            overall_score = result.score
        except Exception:
            # Fallback: distribute overall score proportionally across sections
            for key in _SECTION_KEYS:
                weight = _SECTION_WEIGHTS[key]
                section_scores[key] = weight * overall_score

        return TestContractRecord(
            test_id=t.test_id,
            section_scores=section_scores,
            contract_score=overall_score,
            violations=violations,
            exec_status=exec_info.get("exec_status"),
            exec_duration_s=exec_info.get("exec_duration_s"),
            exec_output=exec_info.get("exec_output", ""),
            gaps_text=getattr(t, "gaps_missing", ""),
            is_blocked=is_blocked,
            section_content=section_content,
            rendered_code=getattr(t, "rendered_code", ""),
        )


# ────────────────────────────────────────────────────────────────────────────
# HTML Renderer
# ────────────────────────────────────────────────────────────────────────────

def _score_color(score: float, weight: float) -> str:
    """Return a CSS background colour based on score vs weight."""
    ratio = score / weight if weight > 0 else 0.0
    if ratio >= 0.95:
        return "#22c55e"   # green
    if ratio >= 0.75:
        return "#86efac"   # light green
    if ratio >= 0.50:
        return "#fbbf24"   # amber
    return "#f87171"       # red


def _kpi_color(score: float) -> str:
    if score >= 0.90:
        return "#22c55e"
    if score >= 0.75:
        return "#fbbf24"
    return "#f87171"


def _render_html(report: ContractReport) -> str:
    suite_pct = f"{report.suite_contract_score:.0%}"
    kpi_col = _kpi_color(report.suite_contract_score)
    exec_pct = (
        f"{report.exec_pass_rate:.0%}" if report.exec_pass_rate is not None else "—"
    )
    weakest_name = next(
        (m["name"] for m in _SECTION_META if m["key"] == report.weakest_section), "—"
    )
    ts = report.generated_at[:19].replace("T", " ") + " UTC"

    # Section weight legend
    legend_rows = "".join(
        f'<tr><td>{m["id"]}</td><td>{m["name"]}</td>'
        f'<td style="text-align:right">{m["weight"]:.0%}</td></tr>'
        for m in _SECTION_META
    )

    # Heatmap header
    heatmap_headers = "".join(
        f'<th title="{m["name"]}">{m["id"]}</th>' for m in _SECTION_META
    )

    # Heatmap rows
    heatmap_rows = ""
    for rec in report.records:
        status_badge = ""
        if rec.exec_status:
            colour = {
                "passed": "#22c55e", "failed": "#f87171",
                "error": "#f87171", "skipped": "#94a3b8",
            }.get(rec.exec_status, "#94a3b8")
            status_badge = (
                f'<span style="background:{colour};color:#fff;border-radius:4px;'
                f'padding:1px 6px;font-size:0.7rem;margin-left:6px">'
                f'{rec.exec_status}</span>'
            )
        if rec.is_blocked:
            status_badge += (
                '<span style="background:#f87171;color:#fff;border-radius:4px;'
                'padding:1px 6px;font-size:0.7rem;margin-left:4px">BLOCKED</span>'
            )
        cells = "".join(
            f'<td style="background:{_score_color(rec.section_scores.get(m["key"], 0), m["weight"])};'
            f'text-align:center;font-size:0.75rem" '
            f'title="{m["name"]}: {rec.section_scores.get(m["key"], 0):.3f}">'
            f'{rec.section_scores.get(m["key"], 0):.2f}</td>'
            for m in _SECTION_META
        )
        overall_col = _kpi_color(rec.contract_score)
        heatmap_rows += (
            f'<tr>'
            f'<td style="white-space:nowrap;font-family:monospace;font-size:0.8rem">'
            f'{escape(rec.test_id)}{status_badge}</td>'
            f'{cells}'
            f'<td style="text-align:center;font-weight:bold;'
            f'color:{overall_col}">{rec.contract_score:.3f}</td>'
            f'</tr>'
        )

    # Section average footer row
    avg_cells = "".join(
        f'<td style="background:{_score_color(report.section_averages.get(m["key"],0), m["weight"])};'
        f'text-align:center;font-size:0.75rem;font-weight:bold">'
        f'{report.section_averages.get(m["key"],0):.2f}</td>'
        for m in _SECTION_META
    )

    # Per-test detail cards
    detail_cards = ""
    for rec in report.records:
        border_color = "#f87171" if rec.is_blocked or (rec.exec_status == "failed") else (
            "#fbbf24" if rec.contract_score < 0.85 else "#e2e8f0"
        )
        score_color = _kpi_color(rec.contract_score)

        # ── Violations + recommendations ───────────────────────────────
        viol_html = ""
        if rec.violations:
            hard = [v for v in rec.violations if not v.startswith("[Soft]")]
            soft = [v for v in rec.violations if v.startswith("[Soft]")]
            if hard:
                viol_html += "<p><strong>⚠ Violations:</strong></p><ul>" + "".join(
                    f"<li>{escape(v)}</li>" for v in hard
                ) + "</ul>"
            if soft:
                viol_html += "<p><strong>💡 Recommendations:</strong></p><ul>" + "".join(
                    f"<li>{escape(v)}</li>" for v in soft
                ) + "</ul>"

        # ── Execution status banner ─────────────────────────────────────
        exec_banner = ""
        if rec.exec_status:
            dur = f" ({rec.exec_duration_s:.3f}s)" if rec.exec_duration_s else ""
            exec_col = {"passed": "#22c55e", "failed": "#f87171",
                        "error": "#f97316", "skipped": "#94a3b8"}.get(
                            rec.exec_status, "#64748b")
            exec_banner = (
                f'<div style="background:{exec_col}22;border-left:4px solid {exec_col};'
                f'padding:8px 12px;border-radius:4px;margin:8px 0;font-weight:600">'
                f'🚦 Execution: {escape(rec.exec_status)}{escape(dur)}</div>'
            )
        if rec.exec_output:
            exec_banner += (
                f'<details style="margin:4px 0">'
                f'<summary style="cursor:pointer;color:#64748b;font-size:0.8rem">▶ Execution output</summary>'
                f'<pre style="background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;'
                f'font-size:0.78rem;overflow-x:auto;white-space:pre-wrap;word-break:break-word;margin:4px 0">'
                f'{escape(rec.exec_output[:4000])}</pre></details>'
            )

        # ── 8-section content rows ──────────────────────────────────────
        sc = rec.section_content or {}
        section_rows_html = ""
        for m in _SECTION_META:
            key = m["key"]
            weight = m["weight"]
            score = rec.section_scores.get(key, 0.0)
            pct = score / weight * 100 if weight else 0.0
            status_icon = "✅" if pct >= 95 else ("⚠️" if pct >= 70 else "❌")
            status_col = "#22c55e" if pct >= 95 else ("#fbbf24" if pct >= 70 else "#f87171")
            content_text = sc.get(key, "")
            # For test_id section, the "content" is the ID itself
            if key == "test_id":
                content_text = rec.test_id
            content_html = (
                f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;'
                f'padding:8px 10px;font-size:0.82rem;color:#334155;white-space:pre-wrap;'
                f'word-break:break-word;margin-top:4px">{escape(content_text)}</div>'
            ) if content_text else (
                f'<div style="color:#94a3b8;font-size:0.8rem;font-style:italic;padding:4px 0">'
                f'(no content captured)</div>'
            )
            section_rows_html += f"""
<div style="border:1px solid {status_col}44;border-radius:8px;padding:10px 14px;margin:6px 0;background:#fff">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
    <span style="font-weight:700;font-size:0.85rem;color:#1e293b">{m["id"]}. {m["name"]}</span>
    <span style="font-size:0.78rem;color:{status_col};font-weight:600;margin-left:auto">
      {status_icon} {score:.4f} / {weight:.2f} ({pct:.0f}%)
    </span>
  </div>
  {content_html}
</div>"""

        # ── Rendered test code ──────────────────────────────────────────
        code_html = ""
        if rec.rendered_code:
            code_html = f"""
<details style="margin:8px 0">
  <summary style="cursor:pointer;font-weight:600;color:#1e293b;padding:6px 0">
    📝 Generated Test Code
    <span style="font-weight:normal;color:#64748b;font-size:0.8rem;margin-left:8px">
      (click to expand)
    </span>
  </summary>
  <pre style="background:#0f172a;color:#e2e8f0;padding:16px;border-radius:8px;
font-size:0.78rem;overflow-x:auto;white-space:pre;line-height:1.5;margin:6px 0">{escape(rec.rendered_code)}</pre>
</details>"""

        detail_cards += f"""
<details style="border:2px solid {border_color};border-radius:10px;margin:10px 0;padding:0 14px;background:#fff">
  <summary style="cursor:pointer;padding:12px 0;display:flex;align-items:center;gap:10px">
    <span style="font-weight:700;font-family:monospace;font-size:1rem">{escape(rec.test_id)}</span>
    <span style="background:{score_color}22;color:{score_color};border:1px solid {score_color}66;
border-radius:20px;padding:2px 10px;font-size:0.8rem;font-weight:700">
      {rec.contract_score:.0%}
    </span>
    {"<span style=\"background:#f87171;color:#fff;border-radius:4px;padding:1px 6px;font-size:0.75rem\">BLOCKED</span>" if rec.is_blocked else ""}
    {"<span style=\"background:#22c55e22;color:#16a34a;border-radius:4px;padding:1px 6px;font-size:0.75rem\">PASSED</span>" if rec.exec_status == "passed" else ""}
    {"<span style=\"background:#f8717122;color:#dc2626;border-radius:4px;padding:1px 6px;font-size:0.75rem\">FAILED</span>" if rec.exec_status == "failed" else ""}
    <span style="margin-left:auto;font-size:0.75rem;color:#94a3b8">▼ expand for 8-section detail</span>
  </summary>
  <div style="padding:4px 0 16px 0">
    {exec_banner}
    {viol_html}
    <h4 style="margin:12px 0 6px 0;font-size:0.9rem;color:#475569;text-transform:uppercase;
letter-spacing:.05em">📋 8-Section Contract Detail</h4>
    {section_rows_html}
    {code_html}
  </div>
</details>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>UTF 8-Section Contract Report</title>
  <style>
    body{{font-family:system-ui,sans-serif;margin:0;padding:0;background:#f8fafc;color:#1e293b}}
    .container{{max-width:1200px;margin:0 auto;padding:24px}}
    h1{{font-size:1.5rem;margin-bottom:4px}}
    .meta{{color:#64748b;font-size:0.85rem;margin-bottom:24px}}
    .kpi-strip{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}}
    .kpi{{background:#fff;border-radius:12px;padding:16px 24px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px}}
    .kpi-value{{font-size:2rem;font-weight:700}}
    .kpi-label{{font-size:0.75rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em}}
    table{{border-collapse:collapse;width:100%}}
    th{{background:#1e293b;color:#fff;padding:6px 10px;font-size:0.8rem}}
    td{{border:1px solid #e2e8f0;padding:4px 6px}}
    section{{background:#fff;border-radius:12px;padding:20px;margin-bottom:24px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
    h2{{font-size:1.1rem;margin-top:0}}
    .avg-row{{background:#f1f5f9;font-weight:bold}}
    details > summary{{list-style:none}}
    details > summary::-webkit-details-marker{{display:none}}
    details[open] > summary .toggle-hint::after{{content:" ▲"}}
    details > summary .toggle-hint::after{{content:" ▼"}}
    pre{{font-family:"Fira Code","Cascadia Code","Consolas",monospace}}
  </style>
</head>
<body>
<div class="container">
  <h1>🧪 UTF — 8-Section Contract Report</h1>
  <div class="meta">Generated: {ts} &nbsp;|&nbsp; Language: {escape(report.language)}
    &nbsp;|&nbsp; Framework: {escape(report.framework)}
    &nbsp;|&nbsp; Test type: {escape(report.test_type)}
    &nbsp;|&nbsp; Report v{report.report_version}</div>

  <!-- KPI Strip -->
  <div class="kpi-strip">
    <div class="kpi">
      <div class="kpi-value" style="color:{kpi_col}">{suite_pct}</div>
      <div class="kpi-label">Suite Contract Score</div>
    </div>
    <div class="kpi">
      <div class="kpi-value">{report.test_count}</div>
      <div class="kpi-label">Tests Generated</div>
    </div>
    <div class="kpi">
      <div class="kpi-value" style="color:{'#f87171' if report.blocked_count else '#22c55e'}">{report.blocked_count}</div>
      <div class="kpi-label">Blocked (Contract)</div>
    </div>
    <div class="kpi">
      <div class="kpi-value">{exec_pct}</div>
      <div class="kpi-label">Execution Pass Rate</div>
    </div>
    <div class="kpi">
      <div class="kpi-value" style="color:#f87171;font-size:1rem">{escape(weakest_name)}</div>
      <div class="kpi-label">Weakest Section</div>
    </div>
  </div>

  <!-- Section Weight Legend -->
  <section>
    <h2>📋 Section Weight Legend</h2>
    <table>
      <thead><tr><th>#</th><th>Section Name</th><th>Weight</th></tr></thead>
      <tbody>{legend_rows}</tbody>
    </table>
  </section>

  <!-- Heatmap -->
  <section>
    <h2>🔥 Contract Compliance Heatmap (Test × Section)</h2>
    <div style="overflow-x:auto">
    <table>
      <thead>
        <tr>
          <th>Test ID</th>
          {heatmap_headers}
          <th>Overall</th>
        </tr>
      </thead>
      <tbody>
        {heatmap_rows}
        <tr class="avg-row">
          <td><strong>Section Averages</strong></td>
          {avg_cells}
          <td style="text-align:center;font-weight:bold;color:{kpi_col}">{report.suite_contract_score:.3f}</td>
        </tr>
      </tbody>
    </table>
    </div>
    <p style="font-size:0.75rem;color:#64748b;margin-top:8px">
      🟢 ≥ 95% of weight &nbsp; 🟡 75–94% &nbsp; 🟠 50–74% &nbsp; 🔴 &lt; 50%
    </p>
  </section>

  <!-- Per-test Detail Cards -->
  <section>
    <h2>📄 Per-Test Detail</h2>
    {detail_cards}
  </section>
</div>
</body>
</html>"""


# ────────────────────────────────────────────────────────────────────────────
# JUnit XML Renderer
# ────────────────────────────────────────────────────────────────────────────

def _render_junit(report: ContractReport) -> str:
    ts = report.generated_at[:19]
    total = report.test_count
    failures = sum(
        1 for r in report.records
        if not r.is_blocked and r.exec_status == "failed"
    )
    blocked = report.blocked_count

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<testsuites name="UTF Contract Report" tests="{total}" '
            f'failures="{failures}" errors="{blocked}" time="0">'
        ),
        f'  <testsuite name="contract_suite" tests="{total}" '
        f'failures="{failures}" errors="{blocked}" timestamp="{ts}">',
    ]

    for rec in report.records:
        time_attr = f'{rec.exec_duration_s:.3f}' if rec.exec_duration_s else "0"
        lines.append(
            f'    <testcase name="{escape(rec.test_id)}" '
            f'classname="utf.contract" time="{time_attr}">'
        )

        # Contract properties
        props = [
            ('utf.contract_score', f"{rec.contract_score:.4f}"),
            ('utf.blocked', str(rec.is_blocked).lower()),
        ]
        for m in _SECTION_META:
            score = rec.section_scores.get(m["key"], 0.0)
            props.append((f'utf.section.{m["key"]}', f"{score:.4f}"))
        if rec.gaps_text:
            props.append(('utf.gaps', rec.gaps_text[:300]))
        if rec.exec_status:
            props.append(('utf.exec_status', rec.exec_status))

        lines.append('      <properties>')
        for name, val in props:
            lines.append(f'        <property name="{escape(name)}" value="{escape(val)}"/>')
        lines.append('      </properties>')

        if rec.is_blocked:
            hard_viols = [v for v in rec.violations if not v.startswith("[Soft]")]
            msg = escape("; ".join(hard_viols[:3]))
            lines.append(f'      <error message="{msg}" type="ContractViolation"/>')
        elif rec.exec_status == "failed":
            lines.append(f'      <failure message="Test execution failed" type="AssertionError"/>')

        lines.append('    </testcase>')

    lines += ['  </testsuite>', '</testsuites>']
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# JSON Renderer
# ────────────────────────────────────────────────────────────────────────────

def _render_json(report: ContractReport) -> str:
    doc = {
        "report_version": report.report_version,
        "generated_at": report.generated_at,
        "language": report.language,
        "framework": report.framework,
        "test_type": report.test_type,
        "suite_contract_score": round(report.suite_contract_score, 4),
        "test_count": report.test_count,
        "blocked_count": report.blocked_count,
        "exec_pass_rate": (
            round(report.exec_pass_rate, 4) if report.exec_pass_rate is not None else None
        ),
        "section_averages": {k: round(v, 4) for k, v in report.section_averages.items()},
        "section_pass_rates": {k: round(v, 4) for k, v in report.section_pass_rates.items()},
        "weakest_section": report.weakest_section,
        "weakest_section_avg": round(report.weakest_section_avg, 4),
        "tests": [
            {
                "test_id": r.test_id,
                "contract_score": round(r.contract_score, 4),
                "section_scores": {k: round(v, 4) for k, v in r.section_scores.items()},
                "section_content": r.section_content or {},
                "rendered_code": r.rendered_code or "",
                "exec_status": r.exec_status,
                "exec_duration_s": r.exec_duration_s,
                "exec_output": r.exec_output or "",
                "is_blocked": r.is_blocked,
                "violations": r.violations,
                "gaps": r.gaps_text or "",
            }
            for r in report.records
        ],
    }
    return json.dumps(doc, indent=2)
