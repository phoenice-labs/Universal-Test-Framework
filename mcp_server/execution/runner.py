from __future__ import annotations

from pathlib import Path

from mcp_server.execution.base import ExecutionAdapter, TestRunResult
from mcp_server.execution.pytest_adapter import PytestAdapter
from mcp_server.execution.vitest_adapter import VitestAdapter
from mcp_server.execution.maven_adapter import MavenAdapter
from mcp_server.execution.go_adapter import GoAdapter

_ADAPTERS: list[ExecutionAdapter] = [
    PytestAdapter(),
    VitestAdapter(),
    MavenAdapter(),
    GoAdapter(),
]

# Map language/framework hints to preferred adapter class names
_LANGUAGE_MAP: dict[str, str] = {
    "python": "pytest",
    "typescript": "vitest",
    "javascript": "vitest",
    "java": "maven",
    "kotlin": "maven",
    "go": "go",
}

_FRAMEWORK_MAP: dict[str, str] = {
    "pytest": "pytest",
    "unittest": "pytest",
    "vitest": "vitest",
    "jest": "vitest",
    "junit": "maven",
    "junit5": "maven",
    "testng": "maven",
    "gradle": "maven",
    "maven": "maven",
    "go": "go",
    "go-test": "go",
}


def get_adapter(language: str, framework: str, project_dir: str) -> ExecutionAdapter | None:
    """Return the best adapter for the given language/framework, or None if none can run."""
    preferred_name: str | None = None
    if framework:
        preferred_name = _FRAMEWORK_MAP.get(framework.lower())
    if not preferred_name and language:
        preferred_name = _LANGUAGE_MAP.get(language.lower())

    # Try preferred adapter first
    for adapter in _ADAPTERS:
        if preferred_name and adapter.name == preferred_name:
            if adapter.can_run(project_dir):
                return adapter

    # Fall back: first adapter that can_run
    for adapter in _ADAPTERS:
        if adapter.can_run(project_dir):
            return adapter

    return None


def run_tests(
    test_file: str,
    language: str,
    framework: str,
    project_dir: str | None = None,
    timeout: int = 120,
) -> TestRunResult:
    """Find adapter and run. Returns error result if no adapter found."""
    cwd = project_dir or str(Path(test_file).parent)
    adapter = get_adapter(language, framework, cwd)

    if adapter is None:
        return TestRunResult(
            adapter="none",
            exit_code=-4,
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            duration_seconds=0.0,
            output=f"No suitable adapter found for language={language!r}, framework={framework!r} in {cwd!r}",
            test_file=test_file,
            error_details=[f"No adapter available for {language}/{framework}"],
        )

    return adapter.run(test_file, cwd, timeout=timeout)
