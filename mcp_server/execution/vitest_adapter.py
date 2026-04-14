import json
import re
import time
from pathlib import Path

from mcp_server.execution.base import ExecutionAdapter, TestRunResult


class VitestAdapter(ExecutionAdapter):
    name = "vitest"
    supported_frameworks = ["vitest", "jest"]

    def can_run(self, project_dir: str) -> bool:
        """Check for vitest or jest in node_modules/.bin/ or package.json devDependencies."""
        root = Path(project_dir)
        bin_dir = root / "node_modules" / ".bin"
        if (bin_dir / "vitest").exists() or (bin_dir / "vitest.cmd").exists():
            return True
        if (bin_dir / "jest").exists() or (bin_dir / "jest.cmd").exists():
            return True
        pkg = root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                deps = {**data.get("devDependencies", {}), **data.get("dependencies", {})}
                return "vitest" in deps or "jest" in deps
            except Exception:
                pass
        return False

    def _is_vitest_project(self, project_dir: str) -> bool:
        root = Path(project_dir)
        bin_vitest = root / "node_modules" / ".bin"
        if (bin_vitest / "vitest").exists() or (bin_vitest / "vitest.cmd").exists():
            return True
        pkg = root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                deps = {**data.get("devDependencies", {}), **data.get("dependencies", {})}
                return "vitest" in deps
            except Exception:
                pass
        return False

    def run(self, test_file: str, project_dir: str, timeout: int = 120) -> TestRunResult:
        start = time.monotonic()
        if self._is_vitest_project(project_dir):
            cmd = ["npx", "vitest", "run", test_file, "--reporter=verbose"]
            adapter_name = "vitest"
        else:
            cmd = ["npx", "jest", test_file, "--verbose", "--no-coverage"]
            adapter_name = "jest"

        exit_code, output = self._run_subprocess(cmd, cwd=project_dir, timeout=timeout)
        duration = round(time.monotonic() - start, 3)

        passed, failed, errors, skipped = self._parse_summary(output)
        error_details = self._extract_error_details(output)

        return TestRunResult(
            adapter=adapter_name,
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
        # Vitest: "Tests  5 passed (5)" or "✓ 5 tests pass" / "× 2 tests fail"
        m = re.search(r'Tests\s+(\d+)\s+passed', output)
        if m:
            passed = int(m.group(1))
        m = re.search(r'Tests\s+(\d+)\s+failed', output)
        if m:
            failed = int(m.group(1))
        # Jest: "Tests: 2 failed, 3 passed, 5 total"
        for chunk in re.finditer(r'(\d+)\s+(passed|failed|skipped|pending)', output):
            count, label = int(chunk.group(1)), chunk.group(2)
            if label == "passed" and passed == 0:
                passed = count
            elif label == "failed" and failed == 0:
                failed = count
            elif label in ("skipped", "pending"):
                skipped += count
        return passed, failed, errors, skipped

    def _extract_error_details(self, output: str) -> list[str]:
        details = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("×") or stripped.startswith("FAIL ") or "✕" in stripped:
                details.append(stripped)
        return details
