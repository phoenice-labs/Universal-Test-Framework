from __future__ import annotations

import glob
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from mcp_server.mutation.base import MutationAdapter, MutationResult


class PITAdapter(MutationAdapter):
    name = "pit"
    supported_languages = ["java"]

    def is_available(self, project_dir: str) -> bool:
        pd = Path(project_dir)
        # Detect pitest via pom.xml mentioning pitest or build.gradle
        pom = pd / "pom.xml"
        if pom.exists():
            content = pom.read_text(encoding="utf-8", errors="replace")
            if "pitest" in content.lower():
                return True
        gradle = pd / "build.gradle"
        if gradle.exists():
            content = gradle.read_text(encoding="utf-8", errors="replace")
            if "pitest" in content.lower():
                return True
        gradle_kts = pd / "build.gradle.kts"
        if gradle_kts.exists():
            content = gradle_kts.read_text(encoding="utf-8", errors="replace")
            if "pitest" in content.lower():
                return True
        return False

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
                adapter="pit",
                mutation_score=0.0,
                killed=0,
                survived=0,
                total=0,
                timeout_mutants=0,
                error_mutants=0,
                duration_seconds=0.0,
                output="PIT (pitest) not available in this project",
                report_path=None,
                passed_threshold=False,
                blocked=False,
            )

        pd = Path(project_dir)
        start = time.monotonic()

        # Derive class names from file paths for targeting
        target_class = _file_to_class(source_file)
        target_test = _file_to_class(test_file)

        use_gradle = (pd / "build.gradle").exists() or (pd / "build.gradle.kts").exists()

        if use_gradle:
            cmd = ["./gradlew", "pitest"]
        else:
            cmd = [
                "mvn",
                "org.pitest:pitest-maven:mutationCoverage",
                f"-DtargetClasses={target_class}",
                f"-DtargetTests={target_test}",
                "-DoutputFormats=XML",
            ]

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
                adapter="pit",
                mutation_score=0.0,
                killed=0,
                survived=0,
                total=0,
                timeout_mutants=0,
                error_mutants=0,
                duration_seconds=elapsed,
                output=f"PIT run timed out after {timeout}s",
                report_path=None,
                passed_threshold=False,
                blocked=False,
            )
        except Exception as e:
            elapsed = round(time.monotonic() - start, 2)
            return MutationResult(
                adapter="pit",
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

        # Find XML report
        killed = survived = total = timeouts = errors = 0
        score = 0.0
        survivors: list[str] = []
        report_path: str | None = None

        xml_pattern = str(pd / "target" / "pit-reports" / "*" / "mutations.xml")
        xml_files = sorted(glob.glob(xml_pattern))
        if not xml_files:
            # Gradle may put it elsewhere
            xml_pattern2 = str(pd / "build" / "reports" / "pitest" / "mutations.xml")
            xml_files = glob.glob(xml_pattern2)

        if xml_files:
            report_path = xml_files[-1]  # most recent
            killed, survived, timeouts, errors, survivors = _parse_pit_xml(report_path)
            total = killed + survived + timeouts + errors
            score = self._calc_score(killed, total)

        passed = score >= minimum_score
        blocked_flag = score < block_below

        return MutationResult(
            adapter="pit",
            mutation_score=score,
            killed=killed,
            survived=survived,
            total=total,
            timeout_mutants=timeouts,
            error_mutants=errors,
            duration_seconds=elapsed,
            output=raw_output,
            report_path=report_path,
            passed_threshold=passed,
            blocked=blocked_flag,
            surviving_mutants=survivors,
        )


def _file_to_class(file_path: str) -> str:
    """Convert a Java file path to a class glob for pitest targeting."""
    p = Path(file_path)
    stem = p.stem
    # Return wildcard glob suitable for pitest -DtargetClasses
    return f"*{stem}*"


def _parse_pit_xml(xml_path: str) -> tuple[int, int, int, int, list[str]]:
    """Parse PIT mutations.xml into (killed, survived, timeouts, errors, survivors)."""
    killed = survived = timeouts = errors = 0
    survivors: list[str] = []

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for mutation in root.findall(".//mutation"):
            detected = mutation.get("detected", "false").lower() == "true"
            status = mutation.get("status", "").upper()
            if detected:
                killed += 1
            elif status == "SURVIVED":
                survived += 1
                # Build survivor description
                mut_class = mutation.findtext("mutatedClass", "")
                method = mutation.findtext("mutatedMethod", "")
                line = mutation.findtext("lineNumber", "?")
                mutator = mutation.findtext("mutator", "")
                survivors.append(f"{mutator} in {mut_class}.{method}() line {line}")
            elif status == "TIMED_OUT":
                timeouts += 1
            elif status in ("COMPILE_ERROR", "RUN_ERROR", "NO_COVERAGE"):
                errors += 1
            else:
                # Count non-detected as survived fallback
                survived += 1
    except Exception:
        pass

    return killed, survived, timeouts, errors, survivors
