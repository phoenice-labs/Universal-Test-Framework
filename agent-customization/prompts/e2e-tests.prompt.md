---
mode: agent
description: Generate E2E tests following the Universal 8-section test contract
tools:
  - generate_tests
  - validate_test_contract
---

Generate comprehensive **E2E tests** for the described user journey.

## Context
- **User Journey / Feature:** ${selection}
- **Requirements:** _Paste user story / AC here_
- **Framework:** Playwright (default) — override if needed

## Instructions

Call `generate_tests` with:
- test_type: "e2e"
- requirements_text: the user journey description

## Required Scenarios
- Happy path (full journey success)
- Authentication failure (if auth involved)
- Form validation failure
- Error recovery

## E2E Best Practices (enforce always)
- Use `getByRole` / `getByLabel` / `getByTestId` — never CSS/XPath
- No hardcoded `sleep()` — use explicit waits
- Page Object Model for all page interactions
- Screenshot + video on failure
- No shared state between tests

## Output Format

All 8 contract sections. Include:
- User journey name
- Preconditions (user logged in? specific role?)
- Test data required
- Cleanup after test

Suite footer: journey coverage matrix + recommended additional journeys.
