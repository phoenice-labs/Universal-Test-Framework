import re
import time
from pathlib import Path

from mcp_server.execution.base import ExecutionAdapter, TestRunResult


class GoAdapter(ExecutionAdapter):
    name = "go"
    supported_frameworks = ["go", "go-test"]

    def can_run(self, project_dir: str) -> bool:
        """Check for go.mod in project_dir."""
        return (Path(project_dir) / "go.mod").exists()

    def run(self, test_file: str, project_dir: str, timeout: int = 120) -> TestRunResult:
        start = time.monotonic()

        # Derive the test function name from the file stem (e.g. foo_test.go → TestFoo)
        # Fall back to running all tests when we can't derive a specific function name.
        stem = Path(test_file).stem  # e.g. "auth_test"
        test_func = self._stem_to_func(stem)

        cmd = ["go", "test", "./...", "-v", f"-run={test_func}", f"-timeout={timeout}s"]
        exit_code, output = self._run_subprocess(cmd, cwd=project_dir, timeout=timeout + 5)
        duration = round(time.monotonic() - start, 3)

        passed, failed, errors, skipped = self._parse_output(output)
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

    def _stem_to_func(self, stem: str) -> str:
        """Convert file stem to a regex pattern for -run. Uses '.' to match all if uncertain."""
        # Remove _test suffix, title-case words → "auth_service_test" → "TestAuthService"
        base = re.sub(r'_test$', '', stem)
        parts = base.split('_')
        func_name = "Test" + "".join(p.title() for p in parts if p)
        return func_name if func_name != "Test" else "."

    def _parse_output(self, output: str) -> tuple[int, int, int, int]:
        passed = failed = errors = skipped = 0
        for line in output.splitlines():
            if line.strip().startswith("--- PASS:"):
                passed += 1
            elif line.strip().startswith("--- FAIL:"):
                failed += 1
            elif line.strip().startswith("--- SKIP:"):
                skipped += 1
        return passed, failed, errors, skipped

    def _extract_error_details(self, output: str) -> list[str]:
        details = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("--- FAIL:") or stripped.startswith("FAIL\t"):
                details.append(stripped)
        return details
