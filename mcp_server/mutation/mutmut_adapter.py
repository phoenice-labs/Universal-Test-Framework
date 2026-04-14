from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from mcp_server.mutation.base import MutationAdapter, MutationResult

_NOT_AVAILABLE = MutationResult(
    adapter="mutmut",
    mutation_score=0.0,
    killed=0,
    survived=0,
    total=0,
    timeout_mutants=0,
    error_mutants=0,
    duration_seconds=0.0,
    output="mutmut not available",
    report_path=None,
    passed_threshold=False,
    blocked=False,
)


class MutmutAdapter(MutationAdapter):
    name = "mutmut"
    supported_languages = ["python"]

    def is_available(self, project_dir: str) -> bool:
        return shutil.which("mutmut") is not None

    def run(
        self,
        source_file: str,
        test_file: str,
        project_dir: str,
        timeout: int = 300,
        minimum_score: float = 0.70,
        block_below: float = 0.50,
    ) -> MutationResult:
        if not self.is_available(project_dir):
            return _NOT_AVAILABLE

        test_dir = str(Path(test_file).parent)
        start = time.monotonic()
        output_parts: list[str] = []

        # Step 1: run mutations
        try:
            r1 = subprocess.run(
                ["mutmut", "run", "--paths-to-mutate", source_file, "--tests-dir", test_dir],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            output_parts.append(r1.stdout + r1.stderr)
        except subprocess.TimeoutExpired:
            elapsed = round(time.monotonic() - start, 2)
            return MutationResult(
                adapter="mutmut",
                mutation_score=0.0,
                killed=0,
                survived=0,
                total=0,
                timeout_mutants=0,
                error_mutants=0,
                duration_seconds=elapsed,
                output=f"mutmut run timed out after {timeout}s",
                report_path=None,
                passed_threshold=False,
                blocked=False,
            )
        except Exception as e:
            elapsed = round(time.monotonic() - start, 2)
            return MutationResult(
                adapter="mutmut",
                mutation_score=0.0,
                killed=0,
                survived=0,
                total=0,
                timeout_mutants=0,
                error_mutants=0,
                duration_seconds=elapsed,
                output=str(e),
                report_path=None,
                passed_threshold=False,
                blocked=False,
            )

        # Step 2: collect results
        try:
            r2 = subprocess.run(
                ["mutmut", "results"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            results_output = r2.stdout + r2.stderr
            output_parts.append(results_output)
        except Exception as e:
            results_output = ""
            output_parts.append(str(e))

        elapsed = round(time.monotonic() - start, 2)
        raw_output = "\n".join(output_parts)[:10240]

        killed, survived, timeouts, errors, survivors = _parse_mutmut_results(results_output)
        total = killed + survived + timeouts + errors
        score = self._calc_score(killed, total)
        passed = score >= minimum_score
        blocked = score < block_below

        return MutationResult(
            adapter="mutmut",
            mutation_score=score,
            killed=killed,
            survived=survived,
            total=total,
            timeout_mutants=timeouts,
            error_mutants=errors,
            duration_seconds=elapsed,
            output=raw_output,
            report_path=None,
            passed_threshold=passed,
            blocked=blocked,
            surviving_mutants=survivors,
        )


def _parse_mutmut_results(output: str) -> tuple[int, int, int, int, list[str]]:
    """Parse `mutmut results` output into (killed, survived, timeouts, errors, survivors)."""
    killed = survived = timeouts = errors = 0
    survivors: list[str] = []

    # mutmut results summary lines like:
    #   15 out of 20 mutants were killed
    #   5 mutants survived
    #   0 mutants timed out
    killed_m = re.search(r"(\d+)\s+out of\s+\d+\s+mutants? were killed", output)
    if killed_m:
        killed = int(killed_m.group(1))

    total_m = re.search(r"\d+\s+out of\s+(\d+)\s+mutants? were killed", output)
    if total_m:
        total = int(total_m.group(1))
        survived = total - killed

    survived_m = re.search(r"(\d+)\s+mutants? survived", output)
    if survived_m:
        survived = int(survived_m.group(1))

    timeout_m = re.search(r"(\d+)\s+mutants? timed? out", output, re.IGNORECASE)
    if timeout_m:
        timeouts = int(timeout_m.group(1))

    error_m = re.search(r"(\d+)\s+mutants? caused\s+(?:a\s+)?(?:compile\s+)?error", output, re.IGNORECASE)
    if error_m:
        errors = int(error_m.group(1))

    # Collect surviving mutant descriptions (lines like "Survived: mutmut_src/foo.py:12")
    for line in output.splitlines():
        if re.search(r"(?:survived|SURVIVED)", line) and ":" in line:
            survivors.append(line.strip())

    return killed, survived, timeouts, errors, survivors
