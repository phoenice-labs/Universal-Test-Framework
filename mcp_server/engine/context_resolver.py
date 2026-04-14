"""
context_resolver.py
Merges source code, requirements, and detected metadata into a unified
TestGenerationContext used by the rule engine and template renderer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .language_detector import detect_language_and_framework, DetectionResult
from .framework_mapper import get_framework_mapping, FrameworkMapping


# Requirement ID patterns
_REQ_PATTERN = re.compile(
    r'\b(US|AC|REQ|JIRA|BUG|NFR|SEC)-[\w\-]+',
    re.IGNORECASE,
)

# Function/method signature extractors per language
_FUNCTION_EXTRACTORS: dict[str, str] = {
    "python": r"^(?:async\s+)?def\s+(\w+)\s*\(",
    "typescript": r"(?:(?:export\s+)?(?:async\s+)?function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?\()",
    "javascript": r"(?:(?:async\s+)?function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?\()",
    "java": r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\(",
    "go": r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(",
    "cpp": r"(?:\w+\s+)+(\w+)\s*\(",
}

# Class/struct extractors per language
_CLASS_EXTRACTORS: dict[str, str] = {
    "python": r"^class\s+(\w+)",
    "typescript": r"^(?:export\s+)?class\s+(\w+)",
    "javascript": r"^(?:export\s+)?class\s+(\w+)",
    "java": r"^(?:public|private|protected)?\s+(?:abstract\s+)?class\s+(\w+)",
    "go": r"^type\s+(\w+)\s+struct",
    "cpp": r"^(?:class|struct)\s+(\w+)",
}


@dataclass
class ExtractedRequirement:
    id: str
    raw_text: str
    req_type: str   # US | AC | REQ | JIRA | BUG | NFR | SEC


@dataclass
class ExtractedSymbol:
    name: str
    symbol_type: str   # function | class | method
    signature: str


@dataclass
class TestGenerationContext:
    # Input
    source_code: Optional[str]
    requirements_text: Optional[str]
    test_type: str              # unit | integration | api | e2e | contract | performance | security
    requested_language: Optional[str]
    requested_framework: Optional[str]

    # Detected
    detection: DetectionResult
    mapping: FrameworkMapping

    # Extracted
    requirements: list[ExtractedRequirement] = field(default_factory=list)
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    risk_level: str = "medium"

    # Derived
    has_source: bool = False
    has_requirements: bool = False
    module_name: str = "unknown_module"

    def __post_init__(self) -> None:
        self.has_source = bool(self.source_code and self.source_code.strip())
        self.has_requirements = bool(self.requirements_text and self.requirements_text.strip())


def resolve_context(
    source_code: Optional[str] = None,
    requirements_text: Optional[str] = None,
    test_type: str = "unit",
    language: Optional[str] = None,
    framework: Optional[str] = None,
    file_path: Optional[str] = None,
) -> TestGenerationContext:
    """
    Resolve all context needed for test generation.

    Detects language/framework, extracts requirements and code symbols,
    determines risk level, and returns a fully populated TestGenerationContext.
    """
    # Detect language and framework
    if language:
        # User explicitly specified — still auto-detect framework if not given
        from .language_detector import _LANGUAGE_SIGNATURES
        default_fw = next(
            (s["default_framework"] for s in _LANGUAGE_SIGNATURES if s["language"] == language.lower()),
            "unknown",
        )
        detection = DetectionResult(
            language=language.lower(),
            framework=framework or default_fw,
            confidence=1.0,
            detected_from=["user-specified"],
        )
    else:
        detection = detect_language_and_framework(
            source_code=source_code,
            file_path=file_path,
        )
        if framework:
            detection.framework = framework.lower()

    mapping = get_framework_mapping(detection.language, detection.framework)

    # Extract requirements from requirements text
    requirements: list[ExtractedRequirement] = []
    if requirements_text:
        for match in _REQ_PATTERN.finditer(requirements_text):
            raw = match.group(0)
            req_type = raw.split("-")[0].upper()
            # Capture surrounding sentence context for richer requirement_mapping
            ctx_start = max(0, match.start() - 30)
            ctx_end = min(len(requirements_text), match.end() + 80)
            surrounding = requirements_text[ctx_start:ctx_end].strip().replace("\n", " ")
            # Always trim surrounding to start at the matched ID so context
            # window pre-text (which may contain other IDs) is not included.
            id_upper = raw.upper()
            sur_upper = surrounding.upper()
            id_pos = sur_upper.find(id_upper)
            if id_pos > 0:
                surrounding = surrounding[id_pos:]
            # Deduplicate: strip leading ID repetition (e.g. "US-001: US-001: ..." → "US-001: ...")
            if surrounding.upper().startswith(id_upper + ": " + id_upper):
                surrounding = surrounding[len(id_upper) + 2:].strip()
            requirements.append(ExtractedRequirement(
                id=id_upper,
                raw_text=surrounding,
                req_type=req_type,
            ))

    # Extract symbols from source code
    symbols: list[ExtractedSymbol] = []
    if source_code:
        lang = detection.language
        func_pattern = _FUNCTION_EXTRACTORS.get(lang)
        class_pattern = _CLASS_EXTRACTORS.get(lang)

        if func_pattern:
            for match in re.finditer(func_pattern, source_code, re.MULTILINE):
                name = next((g for g in match.groups() if g), None)
                if name and not name.startswith("_"):  # skip private
                    symbols.append(ExtractedSymbol(
                        name=name,
                        symbol_type="function",
                        signature=match.group(0).strip(),
                    ))

        if class_pattern:
            for match in re.finditer(class_pattern, source_code, re.MULTILINE):
                name = match.group(1)
                if name:
                    symbols.append(ExtractedSymbol(
                        name=name,
                        symbol_type="class",
                        signature=match.group(0).strip(),
                    ))

    # Determine risk level based on symbols and requirements
    risk_level = _assess_risk(source_code or "", requirements_text or "", symbols)

    # Derive module name from first class or first function
    module_name = "unknown_module"
    if symbols:
        classes = [s for s in symbols if s.symbol_type == "class"]
        module_name = classes[0].name if classes else symbols[0].name

    return TestGenerationContext(
        source_code=source_code,
        requirements_text=requirements_text,
        test_type=test_type,
        requested_language=language,
        requested_framework=framework,
        detection=detection,
        mapping=mapping,
        requirements=requirements,
        symbols=symbols,
        risk_level=risk_level,
        module_name=module_name,
    )


# Risk keywords from traceability-rules.yaml
_HIGH_RISK_KEYWORDS = [
    "auth", "login", "password", "token", "secret", "encrypt", "decrypt",
    "payment", "billing", "charge", "pii", "sensitive", "credential",
    "permission", "role", "access_control", "jwt", "oauth", "session",
]
_MEDIUM_RISK_KEYWORDS = [
    "business", "calculate", "transform", "process", "validate", "api",
    "create", "update", "delete", "submit", "register", "checkout",
]


def _assess_risk(source_code: str, requirements_text: str, symbols: list[ExtractedSymbol]) -> str:
    """Assess risk level from keywords in source and requirements."""
    combined = (source_code + " " + requirements_text + " " + " ".join(s.name for s in symbols)).lower()

    for kw in _HIGH_RISK_KEYWORDS:
        if kw in combined:
            return "high"

    for kw in _MEDIUM_RISK_KEYWORDS:
        if kw in combined:
            return "medium"

    return "low"
