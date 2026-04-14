"""
mcp_server/reporting — 8-Section Contract Reporting Module.

Public API:
    ContractReporter  — builds HTML / JUnit XML / JSON from EngineOutput
    write_contract_report(output, cfg, cwd) — auto-called by run_engine()
"""
from .contract_reporter import ContractReporter
from .report_writer import write_contract_report

__all__ = ["ContractReporter", "write_contract_report"]
