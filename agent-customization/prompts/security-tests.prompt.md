---
mode: agent
description: Generate security tests following the Universal 8-section test contract
tools:
  - generate_tests
  - validate_test_contract
---

Generate **security tests** for the described feature/endpoint.

## Context
- **Feature / endpoint under test:** ${selection}
- **Security requirements:** _Paste SEC-xxx / compliance requirements here_

## Instructions

Call `generate_tests` with:
- test_type: "security"
- source_code or requirements_text as available

## OWASP Top 10 Checklist (cover all applicable)
- [ ] A01 Broken Access Control — IDOR, privilege escalation
- [ ] A02 Cryptographic Failures — plaintext secrets, weak TLS
- [ ] A03 Injection — SQL, NoSQL, command, XSS, prompt injection
- [ ] A04 Insecure Design — rate limiting, account lockout
- [ ] A05 Security Misconfiguration — default creds, security headers
- [ ] A06 Vulnerable Components — dependency CVE scan
- [ ] A07 Authentication Failures — JWT tampering, session fixation
- [ ] A08 Data Integrity — unsigned deserialization
- [ ] A09 Logging Failures — sensitive data in logs, log injection
- [ ] A10 SSRF — internal network access via URL input

## For AI/LLM Features (add if applicable)
- [ ] LLM01 Prompt Injection
- [ ] LLM02 Insecure Output Handling
- [ ] LLM06 Sensitive Information Disclosure

## Output Format

All 8 contract sections. Include:
- owasp_category (e.g., A03:2021 Injection)
- cwe_id (e.g., CWE-89)
- attack_vector (specific payload/technique)
- risk_level (Critical/High/Medium/Low)
- remediation_if_fails

Suite footer: OWASP coverage matrix + risk heatmap + recommendations.
