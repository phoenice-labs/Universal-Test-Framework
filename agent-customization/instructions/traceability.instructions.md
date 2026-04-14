---
applyTo: "**"
---

# Universal Test Framework — Traceability Instructions

## Traceability is Non-Negotiable

Every test MUST be linked to at least one requirement.
If no requirement ID is provided, create a placeholder requirement and note it explicitly.

---

## Requirement ID Formats

| Type | Format | Example |
|------|--------|---------|
| User Story | US-NNN | US-042 |
| Acceptance Criteria | AC-N.N | AC-2.1 |
| Formal Requirement | REQ-NNN | REQ-007 |
| Jira Ticket | JIRA-NNNN | JIRA-1234 |
| Bug/Defect | BUG-NNN | BUG-567 |
| Non-Functional | NFR-NNN | NFR-001 |
| Security Control | SEC-NN | SEC-01 |

---

## Traceability Matrix Format

Always output a traceability matrix at the end of a test suite:

```markdown
## Traceability Matrix

| Requirement | Description | Test IDs | Status | Risk | Gaps |
|-------------|-------------|----------|--------|------|------|
| US-001 | User registration | TC-US-001, TC-US-002 | ✅ covered | 🟡 medium | No email verification test |
| AC-2.1 | Email validation | TC-US-003 | ⚠️ partial | 🟡 medium | International email formats not tested |
| SEC-01 | Auth bypass | TC-SEC-001, TC-SEC-002 | ✅ covered | 🔴 high | MFA bypass not tested |
```

Status icons: ✅ covered | ⚠️ partially covered | ❌ not covered
Risk icons: 🔴 high | 🟡 medium | 🟢 low

---

## Orphan Test Rule

No test may exist without a requirement link.
If you generate a test with no requirement, mark it:
- `requirement_mapping: "INFERRED — no requirement provided; add REQ-xxx"`
- Flag it in the traceability matrix as `⚠️ orphan`

---

## Coverage Assessment Format

```markdown
## Coverage Assessment

- Requirements covered: N/M (X%)
- High-risk requirements: all covered ✅ / N uncovered ❌
- Test types applied: unit, integration, ...
- Estimated line coverage: ~X%
- Estimated branch coverage: ~X%
- Run to measure: `pytest --cov=module --cov-report=html`

## Recommended Additional Tests
1. [TC-REQ-NNN] — {scenario} — covers {requirement} — priority: high
2. ...
```
