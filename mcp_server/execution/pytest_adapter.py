import re
import sys
import time
from pathlib import Path

from mcp_server.execution.base import ExecutionAdapter, TestRunResult


def _find_python(project_dir: str) -> str:
    """Return the best python executable for the given project directory.

    Search order (stops at first hit):
      1. <project_dir>/.venv/Scripts/python.exe  (Windows venv)
      2. <project_dir>/.venv/bin/python           (Unix venv)
      3. <project_dir>/venv/Scripts/python.exe
      4. <project_dir>/venv/bin/python
      5. <project_dir>/.env/Scripts/python.exe
      6. <project_dir>/.env/bin/python
      7. sys.executable                            (the interpreter running the MCP server)
      8. "python" / "python3"                      (last-resort PATH look-up)
    """
    root = Path(project_dir)
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / "venv"  / "Scripts" / "python.exe",
        root / "venv"  / "bin" / "python",
        root / ".env"  / "Scripts" / "python.exe",
        root / ".env"  / "bin" / "python",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # sys.executable is the python running the MCP server — best fallback
    if sys.executable:
        return sys.executable
    return "python"


class PytestAdapter(ExecutionAdapter):
    name = "pytest"
    supported_frameworks = ["pytest"]

    def can_run(self, project_dir: str) -> bool:
        """Check if pytest is available using the project's own python."""
        python = _find_python(project_dir)
        exit_code, _ = self._run_subprocess(
            [python, "-m", "pytest", "--version"],
            cwd=project_dir,
            timeout=10,
        )
        return exit_code == 0

    def run(self, test_file: str, project_dir: str, timeout: int = 120) -> TestRunResult:
        python = _find_python(project_dir)
        start = time.monotonic()
        cmd = [python, "-m", "pytest", test_file, "-v", "--tb=short", "--no-header", "-q"]
        exit_code, output = self._run_subprocess(cmd, cwd=project_dir, timeout=timeout)
        duration = round(time.monotonic() - start, 3)

        passed, failed, errors, skipped = self._parse_summary(output)
        error_details = self._extract_error_details(output)

        return TestRunResult(
            adapter=self.name,
            exit_code=exit_code,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_seconds=duration,
            output=output,
            test_file=test_file,
            error_details=error_details,
        )

    def _parse_summary(self, output: str) -> tuple[int, int, int, int]:
        passed = failed = errors = skipped = 0
        # Match pytest summary line: "3 passed, 1 failed, 2 error, 1 skipped"
        for m in re.finditer(r'(\d+)\s+(passed|failed|error|errors|skipped)', output):
            count = int(m.group(1))
            label = m.group(2)
            if label == "passed":
                passed = count
            elif label == "failed":
                failed = count
            elif label in ("error", "errors"):
                errors = count
            elif label == "skipped":
                skipped = count
        return passed, failed, errors, skipped

    def _extract_error_details(self, output: str) -> list[str]:
        details = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("FAILED") or stripped.startswith("ERROR"):
                details.append(stripped)
        return details
