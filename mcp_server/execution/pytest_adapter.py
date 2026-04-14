import re
import time
from pathlib import Path

from mcp_server.execution.base import ExecutionAdapter, TestRunResult


class PytestAdapter(ExecutionAdapter):
    name = "pytest"
    supported_frameworks = ["pytest"]

    def can_run(self, project_dir: str) -> bool:
        """Check if pytest is available by trying `python -m pytest --version`."""
        exit_code, _ = self._run_subprocess(
            ["python", "-m", "pytest", "--version"],
            cwd=project_dir,
            timeout=10,
        )
        return exit_code == 0

    def run(self, test_file: str, project_dir: str, timeout: int = 120) -> TestRunResult:
        start = time.monotonic()
        cmd = ["python", "-m", "pytest", test_file, "-v", "--tb=short", "--no-header", "-q"]
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
