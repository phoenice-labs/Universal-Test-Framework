from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from mcp_server.mutation.base import MutationAdapter, MutationResult


class StrykerAdapter(MutationAdapter):
    name = "stryker"
    supported_languages = ["javascript", "typescript"]

    def is_available(self, project_dir: str) -> bool:
        # Check local node_modules/.bin/stryker first, then global PATH
        local_bin = Path(project_dir) / "node_modules" / ".bin" / "stryker"
        if local_bin.exists():
            return True
        return shutil.which("stryker") is not None

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
                adapter="stryker",
                mutation_score=0.0,
                killed=0,
                survived=0,
                total=0,
                timeout_mutants=0,
                error_mutants=0,
                duration_seconds=0.0,
                output="stryker not available",
                report_path=None,
                passed_threshold=False,
                blocked=False,
            )

        report_file = str(Path(project_dir) / "stryker-report.json")
        start = time.monotonic()

        try:
            result = subprocess.run(
                [
                    "npx", "stryker", "run",
                    "--reporters", "json",
                    "--jsonReporter.fileName", "stryker-report.json",
                ],
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
                adapter="stryker",
                mutation_score=0.0,
                killed=0,
                survived=0,
                total=0,
                timeout_mutants=0,
                error_mutants=0,
                duration_seconds=elapsed,
                output=f"stryker run timed out after {timeout}s",
                report_path=None,
                passed_threshold=False,
                blocked=False,
            )
        except Exception as e:
            elapsed = round(time.monotonic() - start, 2)
            return MutationResult(
                adapter="stryker",
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

        # Parse JSON report
        killed = survived = total = timeouts = errors = 0
        score = 0.0
        survivors: list[str] = []
        actual_report_path: str | None = None

        if Path(report_file).exists():
            actual_report_path = report_file
            try:
                with open(report_file, encoding="utf-8") as f:
                    data = json.load(f)
                metrics = data.get("metrics", data)
                raw_score = metrics.get("mutationScore", 0.0)
                score = round(raw_score / 100.0, 3) if raw_score > 1 else round(float(raw_score), 3)
                killed = int(metrics.get("killed", 0))
                survived = int(metrics.get("survived", 0))
                total = int(metrics.get("totalMutants", killed + survived))
                timeouts = int(metrics.get("timeout", 0))
                errors = int(metrics.get("compileErrors", 0) + metrics.get("runtimeErrors", 0))

                # Collect surviving mutant descriptions
                for mutant in data.get("files", {}).values():
                    for m in mutant.get("mutants", []):
                        if m.get("status") == "Survived":
                            loc = m.get("location", {})
                            survivors.append(
                                f"{m.get('mutatorName', 'Unknown')} at "
                                f"line {loc.get('start', {}).get('line', '?')}: {m.get('description', '')}"
                            )
            except Exception as parse_err:
                raw_output += f"\n[JSON parse error: {parse_err}]"

        passed = score >= minimum_score
        blocked = score < block_below

        return MutationResult(
            adapter="stryker",
            mutation_score=score,
            killed=killed,
            survived=survived,
            total=total,
            timeout_mutants=timeouts,
            error_mutants=errors,
            duration_seconds=elapsed,
            output=raw_output,
            report_path=actual_report_path,
            passed_threshold=passed,
            blocked=blocked,
            surviving_mutants=survivors,
        )
