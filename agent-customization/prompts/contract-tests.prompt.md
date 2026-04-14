---
mode: agent
description: Generate contract tests following the Universal 8-section test contract
tools:
  - generate_tests
  - validate_test_contract
---

Generate **consumer-driven contract tests** (Pact) for the described service interaction.

## Context
- **Consumer service:** _Name of consuming service_
- **Provider service:** _Name of providing service_
- **Interaction:** ${selection}
- **Requirements:** _Contract requirements / NFR_

## Instructions

Call `generate_tests` with:
- test_type: "contract"
- requirements_text: the interaction description

## Required Scenarios
- Happy path consumer interaction
- Error response contract
- Optional field omission (provider drops optional field)
- Extra field tolerance (provider adds new field)

## Pact Rules (enforce always)
- Consumer writes the contract — not the provider
- Use Pact matchers (like, eachLike, term) — not exact matching
- Publish pact to broker after consumer tests pass
- Provider must implement all provider states

## Output Format

All 8 contract sections. Include:
- consumer_name, provider_name
- interaction_description
- provider_state
- pact_specification_version
- Publish command

Suite footer: contract coverage (% of interactions verified) + recommendations.
