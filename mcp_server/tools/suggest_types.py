"""
suggest_types.py — MCP Tool: suggest_test_types
Analyzes source code and requirements to suggest which test types to apply.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..engine.language_detector import detect_language_and_framework


_TEST_TYPE_SIGNALS: dict[str, list[str]] = {
    "unit": [
        "function", "def ", "method", "class", "calculate", "parse", "transform",
        "validate", "convert", "format", "compute", "util", "helper",
    ],
    "integration": [
        "database", "repository", "service", "dao", "orm", "query", "transaction",
        "message queue", "kafka", "rabbitmq", "redis", "cache", "storage",
    ],
    "api": [
        "endpoint", "route", "controller", "handler", "http", "rest", "graphql",
        "grpc", "request", "response", "api", "swagger", "openapi",
    ],
    "e2e": [
        "user journey", "login flow", "checkout", "registration", "onboarding",
        "browser", "page", "ui", "frontend", "react", "vue", "angular",
    ],
    "contract": [
        "provider", "consumer", "pact", "contract", "microservice", "service boundary",
        "api contract", "interface", "integration contract",
    ],
    "performance": [
        "performance", "latency", "throughput", "load", "stress", "sla",
        "response time", "nfr", "scalability", "concurrent",
    ],
    "security": [
        "auth", "authentication", "authorization", "password", "token", "jwt",
        "permission", "role", "access control", "pii", "sensitive", "encrypt",
        "sql injection", "xss", "csrf", "owasp",
    ],
}

_TEST_TYPE_DESCRIPTIONS: dict[str, str] = {
    "unit": "Test individual functions/methods in isolation",
    "integration": "Test component interactions (service + DB, service + queue)",
    "api": "Test HTTP endpoints for contract, auth, and error handling",
    "e2e": "Test complete user journeys through the UI",
    "contract": "Test service-to-service interface contracts (CDC)",
    "performance": "Validate SLA compliance under load",
    "security": "Verify resistance to OWASP Top 10 attacks",
}

_RISK_TYPES: dict[str, list[str]] = {
    "security": ["auth", "payment", "pii", "password", "token", "secret", "encrypt"],
    "performance": ["nfr", "sla", "latency", "throughput", "high load"],
    "contract": ["microservice", "provider", "consumer", "pact", "api contract"],
}


def suggest_test_types(
    source_code: Optional[str] = None,
    requirements_text: Optional[str] = None,
) -> dict[str, Any]:
    """
    Suggest which test types to apply based on source code and requirements.

    Returns:
        recommended_types with rationale, detection info, risk flags
    """
    if not source_code and not requirements_text:
        return {
            "error": "Provide at least source_code or requirements_text",
            "recommended_types": [],
        }

    combined = ((source_code or "") + " " + (requirements_text or "")).lower()

    # Detect language
    detection = detect_language_and_framework(source_code=source_code)

    # Score each test type
    scores: dict[str, int] = {}
    rationale: dict[str, list[str]] = {}

    for test_type, signals in _TEST_TYPE_SIGNALS.items():
        matched = [s for s in signals if s.lower() in combined]
        if matched:
            scores[test_type] = len(matched)
            rationale[test_type] = matched[:3]  # top 3 matching signals

    # Unit tests are always recommended if source code is present
    if source_code:
        scores["unit"] = scores.get("unit", 0) + 5
        rationale.setdefault("unit", []).append("source code provided")

    # Sort by score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    recommended: list[dict[str, Any]] = []
    for test_type, score in ranked:
        recommended.append({
            "test_type": test_type,
            "priority": "high" if score >= 4 else "medium" if score >= 2 else "low",
            "score": score,
            "description": _TEST_TYPE_DESCRIPTIONS[test_type],
            "rationale": rationale.get(test_type, []),
        })

    # Risk flags
    risk_flags: list[str] = []
    for risk_type, keywords in _RISK_TYPES.items():
        if any(kw in combined for kw in keywords):
            risk_flags.append(
                f"⚠️ {risk_type.upper()} signals detected — {risk_type} tests are strongly recommended"
            )

    # Minimum baseline recommendation
    if not recommended:
        recommended = [
            {
                "test_type": "unit",
                "priority": "high",
                "score": 1,
                "description": _TEST_TYPE_DESCRIPTIONS["unit"],
                "rationale": ["default baseline recommendation"],
            }
        ]

    return {
        "recommended_types": recommended,
        "high_priority_types": [r["test_type"] for r in recommended if r["priority"] == "high"],
        "risk_flags": risk_flags,
        "detected_language": detection.language,
        "detected_framework": detection.framework,
        "detection_confidence": detection.detection_confidence if hasattr(detection, "detection_confidence") else detection.confidence,
        "total_types_recommended": len(recommended),
    }
