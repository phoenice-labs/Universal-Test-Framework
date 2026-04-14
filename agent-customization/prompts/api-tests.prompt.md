---
mode: agent
description: Generate API tests following the Universal 8-section test contract
tools:
  - generate_tests
  - validate_test_contract
  - analyze_coverage
---

Generate comprehensive **API tests** for the provided endpoint/spec.

## Context
- **Endpoint / OpenAPI spec:** ${selection}
- **Requirements:** _Paste ticket / AC here_
- **Auth mechanism:** _JWT / API key / OAuth_

## Instructions

Call `generate_tests` with:
- test_type: "api"
- source_code or requirements_text as available

## Required Scenarios (always include ALL)
- ✅ Happy path (200/201)
- ❌ Missing required field (400/422)
- 🔒 Unauthenticated (401)
- 🚫 Unauthorized role (403)
- 🔍 Not found (404)
- 💥 Server error handling (500)

## Security Checks (always include)
- No sensitive data in error responses
- Security headers present
- No stack traces in 4xx/5xx

## Output Format

All 8 contract sections + executable test code.
Include: endpoint URL, HTTP method, request headers, request body schema, response schema.

Suite footer: traceability matrix + coverage (endpoint coverage %) + recommended tests.
