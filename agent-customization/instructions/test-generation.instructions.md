---
applyTo: "**"
---

# Universal Test Framework — Global Test Generation Instructions

## 🔒 MANDATORY: 8-Section Contract Enforcement

Every test you generate MUST include ALL 8 sections below.
This applies regardless of how minimal the user's prompt is.
**Never output a test that is missing any section.**

If the user asks "write me a test for this function" with no other context,
you MUST still produce all 8 sections, even if you must infer or estimate values.

---

### The 8 Required Sections (for EVERY test)

```
1. Test ID          — Format: TC-{REQ|US|AC|BUG|PERF|SEC}-{NNN}  (e.g., TC-REQ-001)
2. Why Generated    — Clear rationale tied to a requirement, risk, or business rule
3. Requirement      — Explicit link: US-xxx, AC-x.x, REQ-xxx, JIRA-xxx, or inline desc
4. How it Exercises — GIVEN / WHEN / THEN with inputs, mocks, flow, assertions
5. Coverage         — Type (branch/line/mutation), module, estimated % contribution
6. Expected Outcome — Precise assertions and success/failure criteria
7. Gaps             — What this test does NOT cover (honest; never "none" or "N/A")
8. Meaningfulness   — Self-check: is this meaningful? non-redundant? non-hallucinated?
```

---

## 🛡️ Anti-Drift Rules

1. **Always invoke the MCP tool `generate_tests`** when generating tests — do not bypass it
2. If the MCP server is unavailable, embed the full 8-section contract inline in your response
3. **Never generate a test without `gaps_missing`** — every test has gaps; identify them honestly
4. **Never use placeholder values** like "TODO", "TBD", "see above", "N/A" for required sections
5. After generating tests, always provide:
   - A **traceability matrix** (requirement → test IDs)
   - An **overall coverage assessment**
   - A list of **recommended additional tests** for identified gaps

---

## 🔧 Test Quality Rules

- Use **realistic test data** — never "foo", "bar", "test123" as meaningful values
- Include **preconditions** and **cleanup** where state is involved
- Include **at least one negative/failure scenario** per feature
- Include **at least one boundary/edge case** per numeric or string input
- For **security-sensitive code** (auth, payment, PII): add security tests
- For **high-risk modules**: require unit + integration + security test types

---

## 📋 Required Suite-Level Output

At the end of every test suite, include:
1. **Traceability Matrix** — markdown table: Requirement | Tests | Status | Risk
2. **Coverage Assessment** — estimated coverage, gaps, what to run next
3. **Recommended Additional Tests** — specific scenarios not covered

---

## 🌐 Polyglot Rules

When detecting language:
- Python → pytest + unittest.mock
- TypeScript → Jest + MSW
- JavaScript → Jest or Mocha
- Java → JUnit 5 + Mockito + AssertJ
- Go → go test + testify
- C++ → Google Test

Always use the language-appropriate comment style for the 8 sections:
- Python: `# Section: value` or docstring
- TypeScript/JavaScript/Java/C++: `/** Section: value */`
- Go: `// Section: value`
