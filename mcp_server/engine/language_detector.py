"""
language_detector.py
Detects programming language and test framework from source code or file hints.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DetectionResult:
    language: str
    framework: str
    confidence: float          # 0.0–1.0
    detected_from: list[str]   # evidence list
    version_hint: Optional[str] = None


# Ordered by specificity — more specific patterns first
_LANGUAGE_SIGNATURES: list[dict] = [
    {
        "language": "python",
        "default_framework": "pytest",
        "extensions": [".py", ".pyw"],
        "shebang": r"^#!.*python",
        "imports": [r"\bimport\s+\w+", r"\bfrom\s+\w+\s+import\b"],
        "keywords": [r"\bdef\s+\w+\s*\(", r"\bclass\s+\w+[:\(]", r"\basync\s+def\b"],
        "test_indicators": [r"import pytest", r"def test_", r"@pytest\.fixture"],
        "framework_hints": {
            "pytest": [r"import pytest", r"@pytest\.", r"def test_"],
            "unittest": [r"import unittest", r"TestCase", r"self\.assert"],
        },
    },
    {
        "language": "typescript",
        "default_framework": "jest",
        "extensions": [".ts", ".tsx"],
        "shebang": None,
        "imports": [r"\bimport\s+.*\s+from\s+['\"]", r"import\s+type\s+"],
        "keywords": [r":\s*(string|number|boolean|void|any|unknown)\b", r"\binterface\s+\w+", r"\btype\s+\w+\s*="],
        "test_indicators": [r"import.*jest", r"describe\(", r"it\(|test\("],
        "framework_hints": {
            "jest": [r"import.*from.*@jest", r"jest\.mock", r"describe\(.*=>\s*\{"],
            "vitest": [r"import.*from.*vitest", r"vi\.mock"],
            "playwright": [r"import.*playwright", r"@playwright/test"],
        },
    },
    {
        "language": "javascript",
        "default_framework": "jest",
        "extensions": [".js", ".jsx", ".mjs", ".cjs"],
        "shebang": r"^#!.*node",
        "imports": [r"\brequire\s*\(", r"\bimport\s+.*\s+from\s+['\"]"],
        "keywords": [r"\bconst\s+\w+\s*=", r"\blet\s+\w+\s*=", r"\bfunction\s+\w+\s*\("],
        "test_indicators": [r"require.*jest", r"describe\(", r"it\(|test\("],
        "framework_hints": {
            "jest": [r"require\(['\"]jest", r"describe\(", r"expect\("],
            "mocha": [r"require\(['\"]mocha", r"describe\(.*function"],
            "jasmine": [r"require\(['\"]jasmine", r"jasmine\."],
        },
    },
    {
        "language": "java",
        "default_framework": "junit5",
        "extensions": [".java"],
        "shebang": None,
        "imports": [r"^import\s+[a-zA-Z]+\.[a-zA-Z]+", r"^package\s+[a-zA-Z]+"],
        "keywords": [r"\bpublic\s+class\b", r"\bprivate\s+\w+\s+\w+\s*[=;(]", r"\bvoid\s+\w+\s*\("],
        "test_indicators": [r"import org\.junit", r"@Test", r"@ExtendWith"],
        "framework_hints": {
            "junit5": [r"import org\.junit\.jupiter", r"@ExtendWith", r"@DisplayName"],
            "junit4": [r"import org\.junit\.Test", r"import org\.junit\.Before"],
            "testng": [r"import org\.testng", r"@Test\(groups"],
        },
    },
    {
        "language": "go",
        "default_framework": "go-test",
        "extensions": [".go"],
        "shebang": None,
        "imports": [r'^import\s+\(', r'^import\s+"'],
        "keywords": [r"\bfunc\s+\w+\s*\(", r"\bpackage\s+\w+", r":="],
        "test_indicators": [r'"testing"', r"func Test\w+\(t \*testing\.T\)", r"t\.Error"],
        "framework_hints": {
            "go-test": [r'"testing"', r"t\.\w+\("],
            "testify": [r"github\.com/stretchr/testify", r"assert\."],
        },
    },
    {
        "language": "cpp",
        "default_framework": "googletest",
        "extensions": [".cpp", ".cc", ".cxx", ".c++", ".h", ".hpp"],
        "shebang": None,
        "imports": [r"^#include\s+[<\"]"],
        "keywords": [r"\bstd::", r"\bclass\s+\w+\s*[:{]", r"int\s+main\s*\("],
        "test_indicators": [r"#include.*gtest", r"TEST\s*\(", r"EXPECT_EQ", r"ASSERT_EQ"],
        "framework_hints": {
            "googletest": [r"#include.*gtest/gtest", r"\bTEST_F?\s*\("],
            "catch2": [r"#include.*catch2", r"TEST_CASE\s*\("],
            "doctest": [r"#include.*doctest", r"TEST_CASE\s*\("],
        },
    },
]

_EXTENSION_MAP: dict[str, str] = {
    ext: sig["language"]
    for sig in _LANGUAGE_SIGNATURES
    for ext in sig["extensions"]
}


def detect_language_and_framework(
    source_code: Optional[str] = None,
    file_path: Optional[str] = None,
) -> DetectionResult:
    """
    Detect language and framework from source code content and/or file path.

    Combines extension-based detection with content-based heuristics.
    Returns a DetectionResult with confidence score and evidence list.
    """
    if not source_code and not file_path:
        return DetectionResult(
            language="unknown",
            framework="unknown",
            confidence=0.0,
            detected_from=["no input provided"],
        )

    evidence: list[str] = []
    scores: dict[str, float] = {}

    # --- Extension-based detection (fast path) ---
    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in _EXTENSION_MAP:
            lang = _EXTENSION_MAP[ext]
            scores[lang] = scores.get(lang, 0) + 0.5
            evidence.append(f"file extension '{ext}' → {lang}")

    # --- Content-based detection ---
    if source_code:
        lines = source_code[:5000]  # Only scan first 5000 chars for performance
        for sig in _LANGUAGE_SIGNATURES:
            lang = sig["language"]
            score = 0.0

            for pattern in sig.get("imports", []):
                if re.search(pattern, lines, re.MULTILINE):
                    score += 0.15
                    evidence.append(f"import pattern '{pattern[:30]}' → {lang}")
                    break

            for pattern in sig.get("keywords", []):
                if re.search(pattern, lines, re.MULTILINE):
                    score += 0.10
                    evidence.append(f"keyword pattern → {lang}")
                    break

            for pattern in sig.get("test_indicators", []):
                if re.search(pattern, lines, re.MULTILINE):
                    score += 0.25
                    evidence.append(f"test indicator '{pattern[:30]}' → {lang}")
                    break

            if shebang := sig.get("shebang"):
                if re.search(shebang, lines, re.MULTILINE):
                    score += 0.30
                    evidence.append(f"shebang → {lang}")

            if score > 0:
                scores[lang] = scores.get(lang, 0) + score

    if not scores:
        return DetectionResult(
            language="unknown",
            framework="unknown",
            confidence=0.0,
            detected_from=evidence or ["no recognizable patterns"],
        )

    # Pick highest-scoring language
    best_lang = max(scores, key=lambda k: scores[k])
    confidence = min(scores[best_lang], 1.0)

    # Detect framework within the chosen language
    framework = _detect_framework(best_lang, source_code or "")

    return DetectionResult(
        language=best_lang,
        framework=framework,
        confidence=confidence,
        detected_from=evidence,
    )


def _detect_framework(language: str, source_code: str) -> str:
    """Detect the test framework for a given language from source content."""
    sig = next((s for s in _LANGUAGE_SIGNATURES if s["language"] == language), None)
    if not sig:
        return "unknown"

    framework_hints: dict[str, list[str]] = sig.get("framework_hints", {})
    best_framework = sig["default_framework"]
    best_score = 0

    for fw, patterns in framework_hints.items():
        score = sum(1 for p in patterns if re.search(p, source_code, re.MULTILINE))
        if score > best_score:
            best_score = score
            best_framework = fw

    return best_framework
