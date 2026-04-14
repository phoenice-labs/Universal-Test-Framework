---
mode: agent
description: Generate unit tests following the Universal 8-section test contract
tools:
  - generate_tests
  - validate_test_contract
  - analyze_coverage
---

Generate comprehensive **unit tests** for the provided code.

## Context
- **Code under test:** ${selection}
- **Requirements (if any):** _Paste user story / AC / Jira ticket here_
- **Language:** _auto-detected_
- **Framework:** _auto-detected_

## Instructions

Call `generate_tests` with:
- test_type: "unit"
- source_code: the code above
- requirements_text: any requirements provided

Then call `validate_test_contract` and `analyze_coverage` on the output.

## Required Output

For each test, include ALL 8 sections:

### TC-REQ-NNN — {test_name}

| Section | Content |
|---------|---------|
| **Test ID** | TC-REQ-NNN |
| **Why Generated** | {rationale tied to requirement/risk} |
| **Requirement** | {US-xxx / AC-x.x / inline description} |
| **How it Exercises** | GIVEN {state} WHEN {action} THEN {assertion} |
| **Coverage** | Branch coverage for {function}; {X}% of module |
| **Expected Outcome** | {precise assertion} |
| **Gaps** | {honest list of what this test does NOT cover} |
| **Meaningfulness** | Meaningful — {justification}. No hallucination: {evidence} |

Then the **executable test code**.

## Suite Footer (mandatory)

### Traceability Matrix
| Requirement | Tests | Status | Risk |
|---|---|---|---|

### Coverage Assessment
- Estimated coverage: X%
- Gaps identified: ...
- Tools to run: `pytest --cov=... --cov-report=html`

### Recommended Additional Tests
1. {test scenario not yet covered}
