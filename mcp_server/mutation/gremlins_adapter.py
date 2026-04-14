from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from mcp_server.mutation.base import MutationAdapter, MutationResult


class GremlinsAdapter(MutationAdapter):
    name = "gremlins"
    supported_languages = ["go"]

    def is_available(self, project_dir: str) -> bool:
        return shutil.which("gremlins") is not None or shutil.which("go-mutesting") is not None

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
            return MutationResult(
                adapter="gremlins",
                mutation_score=0.0,
                killed=0,
                survived=0,
                total=0,
                timeout_mutants=0,
                error_mutants=0,
                duration_seconds=0.0,
                output="gremlins/go-mutesting not available",
                report_path=None,
                passed_threshold=False,
                blocked=False,
            )

        start = time.monotonic()

        if shutil.which("gremlins") is not None:
            cmd = ["gremlins", "unleash", "--dry-run", "."]
        else:
            # Fall back to go-mutesting
            cmd = ["go-mutesting", "./..."]

        try:
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            raw_output = (result.stdout + result.stderr)[:10240]
        except subprocess.TimeoutExpired:
            elapsed = round(time.monotonic() - start, 2)
            return MutationResult(
                adapter="gremlins",
                mutation_score=0.0,
                killed=0,
                survived=0,
                total=0,
                timeout_mutants=0,
                error_mutants=0,
                duration_seconds=elapsed,
                output=f"gremlins run timed out after {timeout}s",
                report_path=None,
                passed_threshold=False,
                blocked=False,
            )
        except Exception as e:
            elapsed = round(time.monotonic() - start, 2)
            return MutationResult(
                adapter="gremlins",
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

        elapsed = round(time.monotonic() - start, 2)
        killed, survived, survivors = _parse_gremlins_output(raw_output)
        total = killed + survived
        score = self._calc_score(killed, total)
        passed = score >= minimum_score
        blocked_flag = score < block_below

        return MutationResult(
            adapter="gremlins",
            mutation_score=score,
            killed=killed,
            survived=survived,
            total=total,
            timeout_mutants=0,
            error_mutants=0,
            duration_seconds=elapsed,
            output=raw_output,
            report_path=None,
            passed_threshold=passed,
            blocked=blocked_flag,
            surviving_mutants=survivors,
        )


def _parse_gremlins_output(output: str) -> tuple[int, int, list[str]]:
    """Parse gremlins/go-mutesting output into (killed, survived, survivors)."""
    killed = survived = 0
    survivors: list[str] = []

    # gremlins: "X surviving mutations out of Y"
    m = re.search(r"(\d+)\s+surviving\s+mutations?\s+out\s+of\s+(\d+)", output, re.IGNORECASE)
    if m:
        survived = int(m.group(1))
        total = int(m.group(2))
        killed = total - survived
        return killed, survived, survivors

    # go-mutesting summary: "The mutation score is X.XX (Y/Z, A skipped)"
    score_m = re.search(r"mutation score is\s+[\d.]+\s+\((\d+)/(\d+)", output, re.IGNORECASE)
    if score_m:
        killed = int(score_m.group(1))
        total = int(score_m.group(2))
        survived = total - killed
        return killed, survived, survivors

    # go-mutesting per-mutation: lines with "PASS" (killed) or "FAIL" (survived)
    for line in output.splitlines():
        upper = line.upper()
        if "PASS" in upper and "mutation" in line.lower():
            killed += 1
        elif "FAIL" in upper and "mutation" in line.lower():
            survived += 1
            survivors.append(line.strip())

    return killed, survived, survivors
