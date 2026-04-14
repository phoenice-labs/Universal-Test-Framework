---
mode: agent
description: Generate integration tests following the Universal 8-section test contract
tools:
  - generate_tests
  - validate_test_contract
  - analyze_coverage
---

Generate comprehensive **integration tests** for the provided code/requirements.

## Context
- **Code / Service under test:** ${selection}
- **Requirements:** _Paste user story / AC / ticket here_
- **Components involved:** _List: service + DB, service + queue, etc._

## Instructions

Call `generate_tests` with:
- test_type: "integration"
- source_code: the code above
- requirements_text: any requirements provided

## Required Scenarios (always include)
- Happy path (all components working together)
- Downstream failure propagation
- Data persistence and retrieval
- Transaction rollback on partial failure
- Timeout/slow dependency handling

## Output Format

For each test, all 8 sections + executable code + traceability matrix at the end.

Document in each test:
- Which components are real vs mocked
- Cleanup/rollback strategy
- Seed data required
- TestContainers used (if any)
