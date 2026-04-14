from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import subprocess


@dataclass
class TestRunResult:
    adapter: str           # "pytest" | "vitest" | "jest" | "maven" | "gradle" | "go"
    exit_code: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_seconds: float
    output: str            # full stdout+stderr (truncated to 10KB)
    test_file: str         # path that was run
    error_details: list[str] = field(default_factory=list)  # failed test names/messages
    success: bool = field(init=False)

    def __post_init__(self):
        self.success = self.exit_code == 0 and self.failed == 0 and self.errors == 0


class ExecutionAdapter(ABC):
    """ABC for all test execution adapters."""

    name: str              # class-level
    supported_frameworks: list[str]  # class-level

    @abstractmethod
    def can_run(self, project_dir: str) -> bool:
        """Return True if this adapter's runner is available in project_dir."""
        ...

    @abstractmethod
    def run(self, test_file: str, project_dir: str, timeout: int = 120) -> TestRunResult:
        """Execute test_file and return structured results."""
        ...

    def _run_subprocess(self, cmd: list[str], cwd: str, timeout: int) -> tuple[int, str]:
        """Shared subprocess runner — captures stdout+stderr, enforces timeout."""
        try:
            result = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True,
                timeout=timeout, encoding='utf-8', errors='replace'
            )
            combined = (result.stdout + result.stderr)[:10240]  # 10KB max
            return result.returncode, combined
        except subprocess.TimeoutExpired:
            return -1, f"Timeout after {timeout}s"
        except FileNotFoundError as e:
            return -2, f"Command not found: {e}"
        except Exception as e:
            return -3, str(e)
