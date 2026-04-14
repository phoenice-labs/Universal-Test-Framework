"""
framework_mapper.py
Maps (language, framework) pairs to their rule files and template paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


RULES_ROOT = Path(__file__).parent.parent.parent / "rules"
TEMPLATES_ROOT = Path(__file__).parent.parent.parent / "templates"


@dataclass
class FrameworkMapping:
    language: str
    framework: str
    language_rule_path: Path
    framework_rule_path: Path
    template_dir: Path
    test_file_extension: str
    comment_style: str           # "hash" | "doubleslash" | "javadoc"
    is_supported: bool = True
    fallback_language: Optional[str] = None


# Language → default framework
LANGUAGE_DEFAULT_FRAMEWORKS: dict[str, str] = {
    "python": "pytest",
    "typescript": "jest",
    "javascript": "jest",
    "java": "junit5",
    "go": "go-test",
    "cpp": "googletest",
}

# Framework → rule file name
FRAMEWORK_RULE_FILES: dict[str, str] = {
    "pytest": "pytest.yaml",
    "unittest": "pytest.yaml",   # fallback to pytest rules
    "jest": "jest.yaml",
    "vitest": "jest.yaml",       # vitest is jest-compatible
    "mocha": "jest.yaml",
    "jasmine": "jest.yaml",
    "junit5": "junit.yaml",
    "junit4": "junit.yaml",
    "testng": "junit.yaml",
    "go-test": "go-test.yaml",
    "testify": "go-test.yaml",
    "googletest": None,           # No separate file — use language rules
    "catch2": None,
    "playwright": "playwright.yaml",
    "cypress": "playwright.yaml", # cypress rules are similar
    "k6": "k6.yaml",
    "locust": "k6.yaml",
    "gatling": "k6.yaml",
}

# Language → template directory
LANGUAGE_TEMPLATE_DIRS: dict[str, str] = {
    "python": "python",
    "typescript": "typescript",
    "javascript": "typescript",  # share TypeScript templates
    "java": "java",
    "go": "go",
    "cpp": "java",                 # C++ uses javadoc-style; closer to Java than Go
}

# Language → file extension for generated test files
LANGUAGE_TEST_EXTENSIONS: dict[str, str] = {
    "python": ".py",
    "typescript": ".test.ts",
    "javascript": ".test.js",
    "java": "Test.java",
    "go": "_test.go",
    "cpp": "_test.cpp",
}

# Language → comment style
LANGUAGE_COMMENT_STYLES: dict[str, str] = {
    "python": "hash",
    "typescript": "javadoc",
    "javascript": "javadoc",
    "java": "javadoc",
    "go": "doubleslash",
    "cpp": "javadoc",
}


def get_framework_mapping(language: str, framework: Optional[str] = None) -> FrameworkMapping:
    """
    Return the full FrameworkMapping for a given language and optional framework.
    Falls back to language defaults if framework is unknown.
    """
    lang = language.lower()
    fw = (framework or LANGUAGE_DEFAULT_FRAMEWORKS.get(lang, "unknown")).lower()

    # Resolve language rule path
    lang_rule_path = RULES_ROOT / "languages" / f"{lang}.yaml"
    if not lang_rule_path.exists():
        # Fallback: use python rules as baseline
        lang_rule_path = RULES_ROOT / "languages" / "python.yaml"
        is_supported = False
    else:
        is_supported = True

    # Resolve framework rule path
    fw_rule_file = FRAMEWORK_RULE_FILES.get(fw)
    if fw_rule_file:
        fw_rule_path = RULES_ROOT / "frameworks" / fw_rule_file
    else:
        # No dedicated framework file — point at language rules as proxy
        fw_rule_path = lang_rule_path

    # Resolve template dir
    tpl_dir_name = LANGUAGE_TEMPLATE_DIRS.get(lang, "python")
    tpl_dir = TEMPLATES_ROOT / tpl_dir_name

    return FrameworkMapping(
        language=lang,
        framework=fw,
        language_rule_path=lang_rule_path,
        framework_rule_path=fw_rule_path,
        template_dir=tpl_dir,
        test_file_extension=LANGUAGE_TEST_EXTENSIONS.get(lang, ".py"),
        comment_style=LANGUAGE_COMMENT_STYLES.get(lang, "hash"),
        is_supported=is_supported,
    )


def list_supported_languages() -> list[str]:
    """Return all languages with rule files."""
    return [p.stem for p in (RULES_ROOT / "languages").glob("*.yaml")]


def list_supported_frameworks() -> list[str]:
    """Return all frameworks with rule files."""
    return [p.stem for p in (RULES_ROOT / "frameworks").glob("*.yaml")]
