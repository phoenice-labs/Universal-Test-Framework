---
mode: agent
description: Generate performance tests following the Universal 8-section test contract
tools:
  - generate_tests
  - validate_test_contract
---

Generate **performance tests** (k6) for the described endpoint/feature.

## Context
- **Target endpoint / feature:** ${selection}
- **SLA requirements:** _Paste NFR / performance requirements here_
- **Expected load:** _e.g., 1000 concurrent users_

## Instructions

Call `generate_tests` with:
- test_type: "performance"
- requirements_text: SLA requirements and load specs

## Required Scenarios
- Smoke test (1 VU, baseline validation)
- Average load test (normal traffic)
- Stress test (find breaking point)
- Spike test (sudden traffic burst)

## Required Metrics (always collect)
- p50, p95, p99 response times (ms)
- Throughput (req/s)
- Error rate (%)
- CPU + memory utilization

## SLA Defaults (use if not specified)
- p95 < 500ms | p99 < 1000ms | error rate < 1%

## Output Format

All 8 contract sections. Include:
- scenario_type (smoke/average/stress/spike/soak)
- VUs and duration
- thresholds configuration
- SLA source reference (NFR-xxx)
- k6 executable code

Suite footer: SLA compliance matrix + baseline comparison + recommendations.
