"""
mcp_server/reporting/report_writer.py

File I/O layer for contract reports.

Writes timestamped HTML / JUnit XML / JSON files to .utf/reports/ and
maintains a stable `last_contract_report.{ext}` copy for quick access.
Rotates old files beyond `keep_last_n`.

Public API:
    write_contract_report(engine_output, cfg, cwd, execution_results) -> dict[str, str]
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mcp_server.reporting.contract_reporter import ContractReporter


def write_contract_report(
    engine_output: Any,
    cfg: Any,                          # UTFConfig
    cwd: Optional[Path] = None,
    execution_results: Optional[list[dict]] = None,
) -> dict[str, str]:
    """
    Write the 8-section contract report to disk.

    Creates `<report_dir>/contract_YYYYMMDD_HHMMSS.{html,xml,json}` and a
    stable `last_contract_report.{ext}` copy.

    Args:
        engine_output:     EngineOutput from run_engine()
        cfg:               UTFConfig (reporting.* section is used)
        cwd:               Project root; defaults to Path.cwd()
        execution_results: Optional list from execution binding

    Returns:
        dict with keys "html", "junit", "json" (only for enabled formats)
        containing the absolute paths to the written files.
    """
    root = (cwd if cwd is not None else Path.cwd()).resolve()
    rep_cfg = cfg.reporting

    report_dir = root / rep_cfg.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = rep_cfg.report_filename_prefix
    formats: list[str] = list(rep_cfg.formats)

    reporter = ContractReporter(engine_output, execution_results=execution_results)

    written: dict[str, str] = {}

    if "html" in formats:
        html_path = report_dir / f"{prefix}_{ts}.html"
        html_path.write_text(reporter.to_html(), encoding="utf-8")
        stable_html = report_dir / f"last_{prefix}_report.html"
        shutil.copy2(str(html_path), str(stable_html))
        written["html"] = str(html_path.resolve())

    if "junit" in formats:
        xml_path = report_dir / f"{prefix}_{ts}.xml"
        xml_path.write_text(reporter.to_junit_xml(), encoding="utf-8")
        stable_xml = report_dir / f"last_{prefix}_report.xml"
        shutil.copy2(str(xml_path), str(stable_xml))
        written["junit"] = str(xml_path.resolve())

    if "json" in formats:
        json_path = report_dir / f"{prefix}_{ts}.json"
        json_path.write_text(reporter.to_json(), encoding="utf-8")
        stable_json = report_dir / f"last_{prefix}_report.json"
        shutil.copy2(str(json_path), str(stable_json))
        written["json"] = str(json_path.resolve())

    # Rotate old reports (keep only last N of each extension)
    _rotate_old_reports(report_dir, prefix, rep_cfg.keep_last_n)

    # Open HTML in browser if configured (dev mode only)
    if "html" in written and getattr(rep_cfg, "open_html", False):
        try:
            import webbrowser
            webbrowser.open(written["html"])
        except Exception:
            pass

    return written


def _rotate_old_reports(report_dir: Path, prefix: str, keep_last_n: int) -> None:
    """Delete oldest timestamped report files beyond keep_last_n per extension."""
    for ext in ("html", "xml", "json"):
        pattern = f"{prefix}_*.{ext}"
        files = sorted(
            (f for f in report_dir.glob(pattern) if "_" in f.stem),
            key=lambda p: p.stat().st_mtime,
        )
        to_delete = files[: max(0, len(files) - keep_last_n)]
        for f in to_delete:
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
