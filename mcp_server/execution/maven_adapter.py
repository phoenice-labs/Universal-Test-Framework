import re
import time
from pathlib import Path

from mcp_server.execution.base import ExecutionAdapter, TestRunResult


class MavenAdapter(ExecutionAdapter):
    name = "maven"
    supported_frameworks = ["junit", "junit5", "testng", "maven", "gradle"]

    def can_run(self, project_dir: str) -> bool:
        """Check for pom.xml (Maven) or build.gradle / build.gradle.kts (Gradle)."""
        root = Path(project_dir)
        return (
            (root / "pom.xml").exists()
            or (root / "build.gradle").exists()
            or (root / "build.gradle.kts").exists()
        )

    def _is_gradle(self, project_dir: str) -> bool:
        root = Path(project_dir)
        return (root / "build.gradle").exists() or (root / "build.gradle.kts").exists()

    def run(self, test_file: str, project_dir: str, timeout: int = 120) -> TestRunResult:
        start = time.monotonic()

        # Derive test class name from file path (e.g. src/test/.../FooTest.java → FooTest)
        test_class = Path(test_file).stem

        if self._is_gradle(project_dir):
            cmd = ["./gradlew", "test", "--tests", test_class]
            adapter_name = "gradle"
        else:
            cmd = ["mvn", "test", "-pl", ".", f"-Dtest={test_class}", "-q"]
            adapter_name = "maven"

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
        # Surefire: "Tests run: 5, Failures: 1, Errors: 0, Skipped: 0"
        m = re.search(
            r'Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)',
            output,
        )
        if m:
            total = int(m.group(1))
            failed = int(m.group(2))
            errors = int(m.group(3))
            skipped = int(m.group(4))
            passed = total - failed - errors - skipped
        return passed, failed, errors, skipped

    def _extract_error_details(self, output: str) -> list[str]:
        details = []
        for line in output.splitlines():
            stripped = line.strip()
            if re.search(r'FAILED|FAILURE|ERROR', stripped):
                details.append(stripped)
        return details
