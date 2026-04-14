# Universal Test Framework (UTF)

> **Contract-driven test enforcement and reporting for LLM-generated code — via MCP, VS Code, Copilot CLI, Claude, Cursor, or Python SDK.**

UTF is an **MCP server and contract enforcement engine**. It does not replace your AI coding assistant — it gives every test your AI writes a mandatory quality gate, a structured audit trail, and a comprehensive compliance report.

[![PyPI version](https://img.shields.io/pypi/v/universal-test-framework)](https://pypi.org/project/universal-test-framework/)
[![Python](https://img.shields.io/pypi/pyversions/universal-test-framework)](https://pypi.org/project/universal-test-framework/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Why UTF? (Not Another Test Generator)

AI tools — GitHub Copilot, Claude, Cursor, Gemini — generate tests fast. The problem: **fast ≠ trustworthy**.

| Without UTF | With UTF |
|---|---|
| Tests exist but nobody knows *why* | Every test is linked to a requirement |
| "Covers everything" — nobody can prove it | Traceability matrix maps REQ → test |
| CI passes; real behavior untested | Gap analysis flags what is NOT covered |
| LLM wrote a test that asserts `True` | Meaningfulness check rejects trivial assertions |
| No history of what was tested | Persistent registry survives session restarts |
| Report shows pass/fail counts only | 8-section per-test detail cards in HTML report |

### UTF vs Markdown Instructions / Prompt Files

You may already use markdown files (`AGENTS.md`, `copilot-instructions.md`, `.cursorrules`) to guide your AI. UTF is complementary — not competing:

| Markdown instructions | UTF |
|---|---|
| Describe *how* to write tests | **Enforce** a contract on *every* test produced |
| Rely on LLM to follow instructions | Block tests that fail the contract at generation time |
| No verification after generation | Score each test 0–1 against 8 measurable criteria |
| No persistent state between sessions | SQLite registry persists all tests and results |
| No compliance report | HTML report with per-test 8-section detail cards |

Use markdown instructions to *shape* how your AI thinks. Use UTF to *verify* and *report on* what it produced.

---

## Key Features

- **13 MCP tools** — generate, validate, register, analyze, trace, execute, mutate, report, and query tests
- **6 languages** — Python, TypeScript, JavaScript, Java, Go, C++
- **7 test types** — unit, integration, API, E2E, contract, performance, security
- **8-section contract** — every test must pass all 8 sections or it is blocked (minimum score: 0.85)
- **3-segment test IDs** — `TC-{PRJ}-{MODULE}-{NNN}` and classic `TC-{MODULE}-{NNN}` both accepted
- **Five install modes** — `uvx` (zero-clone), local clone, Docker, GitHub MCP Registry, pip SDK
- **VS Code @utf** — chat participant with slash commands
- **CI/CD ready** — GitHub Actions, GitLab CI, pre-commit hooks
- **Per-project overrides** — YAML rules in `.utf/rules/` override global defaults

---

## Quick Start

### Setup Method Comparison

| # | Method | How Started | Registry Location | `@utf` Slash Cmds | Best For |
|---|--------|-------------|-------------------|-------------------|----------|
| **1** | **uvx (zero-install)** | `mcp.json` + uvx | `<workspace>/.utf/utf.db` | ❌ use natural language | Any developer with uv |
| **2** | **Local Clone** | `install-vscode-mcp.ps1` | `<workspace>/.utf/utf.db` | ✅ with extension | Contributing / customizing UTF |
| **3** | **Docker / HTTP** | `docker compose up` | Named volume or bind mount | ❌ use natural language | Team / remote / CI |
| **4** | **GitHub MCP Registry** | Auto via client | `<workspace>/.utf/utf.db` | ❌ use natural language | Discoverable via MCP marketplace |
| **5** | **pip + SDK** | Python import | Caller controls cwd | N/A | CI scripts / programmatic |

All methods (1, 2, 4) using `stdio` transport write the registry to **`${workspaceFolder}/.utf/utf.db`** — isolated per project and persistent across sessions.

---

### Method 1 — uvx (Zero-Install, Recommended)

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). No cloning, no venv.

Add to `%APPDATA%\Code\User\mcp.json` (Windows) or `~/.config/Code/User/mcp.json` (macOS/Linux):

```json
{
  "servers": {
    "utf": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "universal-test-framework", "utf-server", "--transport", "stdio"],
      "cwd": "${workspaceFolder}",
      "env": {
        "UTF_PROJECT_DIR": "${workspaceFolder}"
      }
    }
  }
}
```

> **Registry**: `.utf/utf.db` inside `${workspaceFolder}` — isolated per project, persistent across sessions.  
> **Reload VS Code** after editing `mcp.json`.

---

### Method 2 — Local Clone (VS Code + Copilot)

```powershell
git clone https://github.com/phoenice-labs/Universal-Test-Framework
cd Universal-Test-Framework

# Register MCP server, install @utf extension, copy global prompts
.\scripts\install-vscode-mcp.ps1

# Optionally scaffold a specific project
.\scripts\install-vscode-mcp.ps1 -InitProject -ProjectDir C:\my-project
```

Reload VS Code → open Copilot Chat → ask naturally: `generate e2e tests for my backend`.

The install script writes this entry to `mcp.json`:

```json
{
  "utf": {
    "type": "stdio",
    "command": "<python>",
    "args": ["-m", "mcp_server.server", "--transport", "stdio"],
    "cwd": "${workspaceFolder}",
    "env": { "PYTHONPATH": "<UTF_install_dir>" }
  }
}
```

> **Registry**: `${workspaceFolder}/.utf/utf.db` — isolated per project.  
> **`@utf` slash commands** are available after the VSIX extension is installed.

---

### Method 3 — Docker (Team / Remote)

```bash
# Start the UTF server
cd Universal-Test-Framework
docker compose -f docker/docker-compose.yml up -d

# MCP server available at http://localhost:8765/sse
```

Connect from VS Code by adding to `mcp.json`:

```json
{
  "servers": {
    "utf-remote": {
      "type": "sse",
      "url": "http://localhost:8765/sse"
    }
  }
}
```

> **Registry**: persisted in a named Docker volume (`utf_registry → /app/.utf/utf.db`).  
> For per-project isolation with Docker, use a bind-mount in `docker-compose.yml`:
> ```yaml
> volumes:
>   - /path/to/your/project/.utf:/app/.utf
> ```
> Because Docker uses HTTP/SSE transport (no `${workspaceFolder}` templating), pass `project_dir`
> explicitly in tool calls, or set `UTF_PROJECT_DIR` in the container environment.

**Per-project Docker workflow:**

```yaml
# docker-compose.override.yml
services:
  utf-server:
    volumes:
      - ./my-project/.utf:/app/.utf
    environment:
      UTF_PROJECT_DIR: /app
```

---

### Method 4 — GitHub MCP Registry

Once published, UTF is discoverable via the MCP marketplace. Clients that support `server.json` install it automatically. The generated `mcp.json` entry is equivalent to Method 1 (uvx).

> **Registry isolation**: The MCP registry schema does not support a `cwd` field at the registry level.  
> UTF resolves project isolation via (in priority order):
> 1. `project_dir` argument passed to each tool call
> 2. `UTF_PROJECT_DIR` environment variable
> 3. `Path.cwd()` fallback (server's working directory)
>
> For correct isolation, ensure the MCP client writes `"cwd": "${workspaceFolder}"` and
> `"UTF_PROJECT_DIR": "${workspaceFolder}"` in the generated entry (UTF's `mcp-gallery.json` does this).

---

### Method 5 — pip + Python SDK

```bash
pip install universal-test-framework
```

```python
from mcp_server.tools.generate_tests import generate_tests
from pathlib import Path

result = generate_tests(
    test_type="unit",
    source_code=open("src/auth.py").read(),
    project_dir=str(Path.cwd()),   # ← pass explicitly for correct registry isolation
)
print(result["suite_code"])
```

> **Registry**: `<project_dir>/.utf/utf.db` when `project_dir` is passed; falls back to `Path.cwd()`.

---


## MCP Tools Reference

| Tool | Description |
|------|-------------|
| `generate_tests` | Generate a complete test suite satisfying the 8-section contract |
| `validate_test_contract` | Validate any test (generated or hand-written) against the contract |
| `analyze_coverage` | Identify coverage gaps in an existing test suite |
| `build_traceability_matrix` | Build a requirements → tests traceability matrix |
| `suggest_test_types` | Recommend test types with rationale from source code |
| `detect_language_framework` | Auto-detect programming language and test framework |
| `import_test_results` | **Import JUnit XML** from any test run into the UTF registry |
| `query_registry` | Query the persistent per-project test registry |
| `run_tests` | Execute test files and return structured CI results |
| `run_mutation_tests` | Run mutation testing and return mutation score |
| `feedback_status` | Get gap analysis, coverage health, and trend report |
| `generate_report` | Generate HTML / JUnit / JSON contract compliance report |
| `health` | Server health check: version, uptime, tool count |

---

## The 8-Section Test Contract

Every test generated by UTF must satisfy all 8 sections. Tests that fail any hard section are **blocked** — returned in `blocked_tests`, never silently included.

| # | Section | What It Must Contain | Weight |
|---|---------|----------------------|--------|
| 1 | `test_id` | Unique ID: `TC-{TYPE}-{NNN}` (e.g. `TC-US-042`) | 10% |
| 2 | `why_generated` | Rationale tied to a requirement (≥50 chars) | 10% |
| 3 | `requirement_mapping` | At least one `US-`, `AC-`, `REQ-`, `JIRA-`, `BUG-`, or `NFR-` reference | 15% |
| 4 | `how_it_exercises` | GIVEN / WHEN / THEN with inputs, mocks, assertions (≥100 chars) | 20% |
| 5 | `coverage_contribution` | Coverage type + module + estimated % | 15% |
| 6 | `expected_outcome` | Precise return values, status codes, state changes (≥50 chars) | 15% |
| 7 | `gaps_missing` | Honest list of what this test does NOT cover (≥40 chars) | 10% |
| 8 | `meaningfulness_check` | Self-assessment: meaningful / redundant / hallucinated (≥50 chars) | 5% |

**Minimum passing score: 0.85.** Tests below this threshold are blocked regardless of individual section presence. "none" in gaps or vague rationale like "to test the function" are rejected.

---

## Supported Matrix

| Language | Frameworks | Test Types |
|----------|------------|------------|
| Python | pytest | unit, integration, api, e2e, security, performance |
| TypeScript | Jest, Vitest, Playwright | unit, integration, e2e, api |
| JavaScript | Jest, Vitest | unit, integration |
| Java | JUnit 5 + AssertJ, Maven | unit, integration, api |
| Go | go-test + testify | unit, integration, api |
| C++ | Google Test | unit |

---

## The UTF 3-Phase E2E Workflow

This is the **canonical flow** for using UTF with any AI CLI (Copilot, Claude, Cursor) or VS Code. Follow the phases in order — skipping Phase 1 registration means the report has no Per-Test Contract Detail cards.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 1 — CONTRACT GENERATION (LLM writes, UTF validates + registers) │
│                                                                         │
│  ① generate_tests (scaffold)                                           │
│  ② LLM writes real test methods — each with its own TC-ID and         │
│     8-section comment block (WHY / REQ / HOW / COV / OUT / GAP / MEAN)│
│  ③ validate_test_contract — score must be ≥ 0.85 per test             │
│  ④ register_contracts — parse test file, upsert status=generated rows  │
│  ⑤ generate_report — verify Per-Test Contract Detail cards appear      │
│                                                                         │
│  PHASE 2 — EXECUTION (pytest/jest/maven runs, results captured)        │
│                                                                         │
│  ⑥ pytest --junit-xml=utf-tests/reports/results.xml                   │
│  ⑦ import_test_results — upsert executed/failed rows                   │
│  ⑧ generate_report — now shows contract cards AND pass/fail status     │
│                                                                         │
│  PHASE 3 — HEALTH (ongoing coverage quality)                           │
│                                                                         │
│  ⑨ feedback_status — gap analysis, drift alerts, trend over 30 days   │
│  ⑩ Address gaps → add tests → back to Phase 1                         │
└─────────────────────────────────────────────────────────────────────────┘
```

> **Why register before running?**
> The UTF registry has two record types. `status=generated` records (created by `register_contracts`)
> drive the Per-Test Contract Detail cards in the HTML report. `status=executed/failed` records
> (created by `import_test_results`) drive the Execution Results table. Both must exist for a test
> to appear in both sections. Running pytest before registering means you get execution rows but
> no 8-section detail cards.

### Per-Method 8-Section Comment Block (mandatory)

Every test **METHOD** must have its own inline comment block — **not a class docstring**:

```python
def test_health_returns_200(self, live_backend):
    # ─── TC-FIQ-HLT-001 ──────────────────────────────────────────────────────
    # WHY_GENERATED: The /health endpoint is the primary liveness signal for
    #   load balancers and K8s probes. Non-200 = platform unavailable.
    # REQUIREMENT_MAPPING: REQ-E2E-001
    # HOW_IT_EXERCISES: GIVEN backend is running at http://localhost:8001
    #   WHEN GET /health is called THEN HTTP 200 is returned.
    # COVERAGE_CONTRIBUTION: Line coverage of health route; ~15% of health module
    # EXPECTED_OUTCOME: HTTP 200; elapsed < 500ms
    # GAPS_MISSING: Does not test health under load; no auth header tested
    # MEANINGFULNESS_CHECK: Meaningful — gateway test for all other tests
    # ─────────────────────────────────────────────────────────────────────────
    r = requests.get(f"{live_backend}/health", timeout=5)
    assert r.status_code == 200
```

Test ID formats accepted: `TC-HLT-001` (2-segment) or `TC-FIQ-HLT-001` (3-segment project-prefixed).

---

## Invoking UTF from AI CLIs

### GitHub Copilot CLI

UTF tools are called via **natural language** — no special syntax required:

```
# Phase 1 — Generate and register
generate e2e tests for backend/app/api/routes/
register contracts for utf-tests/test_myapp_e2e.py
utf report

# Phase 2 — After running pytest
import junit xml utf-tests/reports/results.xml
utf report

# Phase 3 — Health check
utf status
what are my coverage gaps?
build a traceability matrix
```

### Claude (claude.ai / Claude CLI / MCP client)

Claude supports MCP servers natively. With UTF added to your MCP config:

```
# Natural language triggers UTF MCP tools automatically
"Generate e2e tests for my FastAPI backend at backend/app/"
"Register contracts for utf-tests/test_myapp_e2e.py"
"Generate the UTF report"
"Show UTF status and gaps"
"Validate this test against the 8-section contract: [paste test]"
```

To add UTF to Claude's MCP config (`~/.config/claude/mcp.json` or equivalent):

```json
{
  "mcpServers": {
    "utf": {
      "command": "uvx",
      "args": ["--from", "universal-test-framework", "utf-server", "--transport", "stdio"],
      "env": { "UTF_PROJECT_DIR": "/path/to/your/project" }
    }
  }
}
```

### Cursor

In Cursor, add UTF as an MCP server in `.cursor/mcp.json` (project-level) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "utf": {
      "command": "uvx",
      "args": ["--from", "universal-test-framework", "utf-server", "--transport", "stdio"],
      "cwd": "${workspaceFolder}",
      "env": { "UTF_PROJECT_DIR": "${workspaceFolder}" }
    }
  }
}
```

Then ask Cursor naturally:
```
Generate unit tests for src/auth.py using UTF
UTF report
Register contracts for tests/test_api.py
```

### Any MCP-Compatible Client (Windsurf, Continue, etc.)

The MCP entry is identical regardless of client:

```json
{
  "utf": {
    "type": "stdio",
    "command": "uvx",
    "args": ["--from", "universal-test-framework", "utf-server", "--transport", "stdio"],
    "cwd": "${workspaceFolder}",
    "env": { "UTF_PROJECT_DIR": "${workspaceFolder}" }
  }
}
```

UTF uses natural language detection — the same prompts work across all MCP-compatible AI clients.

---

## GitHub Copilot CLI Usage

UTF is invoked via **natural language** in the GitHub Copilot CLI — there are no special slash commands or `@utf` syntax at the CLI prompt. Simply describe what you want and the MCP tools are called automatically.

### How to Invoke UTF from the CLI

```
# In the GitHub Copilot CLI terminal (gh copilot / copilot-cli)
generate unit tests for backend/app/routes/auth.py
generate e2e tests covering REQ-001 through REQ-024
register contracts for utf-tests/test_myapp_e2e.py
utf report
show utf status
validate this test against the 8-section contract
what are the coverage gaps?
suggest test types for my project
build a traceability matrix
```

### Full Command Reference (Natural Language → MCP Tool)

| What you say | UTF MCP tool invoked | What happens |
|---|---|---|
| `generate unit tests for <file>` | `generate_tests` | Scans source, infers requirements, produces 8-section test suite |
| `generate e2e tests` | `generate_tests` | E2E suite with happy path + negatives + edge cases |
| `generate api tests` | `generate_tests` | API contract tests with HTTP assertions |
| `generate security tests` | `generate_tests` | Auth, injection, and boundary security tests |
| `register contracts for <test_file.py>` | `register_contracts` | Parses test file, extracts per-method 8-section blocks, upserts generated rows |
| `validate this test` | `validate_test_contract` | Scores test 0–1 against all 8 contract sections |
| `utf status` / `show utf status` | `feedback_status` | Gap analysis, coverage health, trend report |
| `utf report` / `generate report` | `generate_report` | HTML + JUnit + JSON contract compliance report |
| `import junit xml <path>` | `import_test_results` | Register results from an existing pytest/Maven run |
| `coverage gaps` | `analyze_coverage` | Identifies uncovered symbols and missing test paths |
| `traceability matrix` | `build_traceability_matrix` | Requirements → tests coverage mapping |
| `suggest test types` | `suggest_test_types` | Recommends test types from source or requirements |
| `query registry` | `query_registry` | Lists registered tests for the current project |
| `run tests` | `run_tests` | Executes test files and records results in registry |
| `run mutation tests` | `run_mutation_tests` | Mutation score with killed/survived breakdown |
| `utf health` | `health` | Server uptime, version, tool count |

### Registry Persistence

The UTF SQLite registry persists **per-project** across all sessions:

```
your-project/
└── .utf/
    ├── utf.db          ← SQLite registry (persists between sessions)
    ├── utf-config.yaml ← Optional project overrides
    ├── rules/          ← Optional YAML rule overrides
    └── reports/
        ├── contract_YYYYMMDD_HHMMSS.html
        ├── contract_YYYYMMDD_HHMMSS.xml
        └── contract_YYYYMMDD_HHMMSS.json
```

Once tests are generated (`generate_tests`), they are registered in `.utf/utf.db`. Subsequent calls to `utf report`, `utf status`, and `query registry` read from this persistent store — **no re-generation required** between sessions.

### Providing Project Context

When the MCP server cannot infer your project root automatically, pass `project_dir` explicitly:

```
generate unit tests for src/auth.py in project C:/my-project
```

Or configure `"cwd": "${workspaceFolder}"` in your `mcp.json` (already set in the quickstart above) so the server always starts in the correct workspace.

---

## VS Code Copilot Chat Integration

After running `.\scripts\install-vscode-mcp.ps1` (Option 2) or adding the `uvx` MCP entry (Option 1):

> **Note:** The `@utf` prefix and `/slash-command` syntax only work if you have the **UTF VS Code Chat Participant** extension installed (included via Option 2). In **GitHub Copilot CLI** and standard **VS Code Copilot Chat** without the extension, use **natural language** — the MCP tools are invoked automatically. See [GitHub Copilot CLI Usage](#github-copilot-cli-usage) above.

### VS Code Chat Participant Slash Commands (extension required)

| Command | Effect |
|---------|--------|
| `@utf /generate-tests unit` | Unit tests for selected/active code |
| `@utf /generate-tests api` | API tests |
| `@utf /generate-tests integration` | Integration tests |
| `@utf /generate-tests e2e` | End-to-end tests |
| `@utf /generate-tests security` | Security / auth tests |
| `@utf /generate-tests performance` | Performance / load tests |
| `@utf /validate-contract` | Validate a test against the 8-section contract |
| `@utf /coverage-gaps` | Identify coverage gaps in the current suite |
| `@utf /traceability` | Build requirements → tests traceability matrix |
| `@utf /report` | Generate HTML contract compliance report |
| `@utf /status` | Server health and installation status |

### Natural Language (no extension required)

In standard VS Code Copilot Chat or GitHub Copilot CLI, just ask:

```
generate unit tests for this file
show utf status
utf report
what are my coverage gaps?
validate this test against the contract
```

UTF reads the open file, detects language and framework, infers requirements from function signatures, generates happy-path + negative + edge-case tests — all validated against the 8-section contract.

---

## Python SDK

Use UTF directly in scripts or CI pipelines without the MCP server:

```python
from mcp_server.tools.generate_tests import generate_tests
from mcp_server.tools.validate_contract import validate_test_contract

# Generate tests — UTF infers language, framework, and requirements
result = generate_tests(
    test_type="unit",
    source_code=open("src/auth.py").read(),
    requirements_text="US-101: Users must be authenticated before accessing dashboard",
)

print(result["suite_code"])          # Executable test file
print(result["traceability_matrix"]) # Requirements → tests mapping
print(result["gaps"])                # Identified coverage gaps

# Validate any existing test
validation = validate_test_contract(test_content=my_test_markdown)
print(f"Score: {validation['score']:.0%}  Valid: {validation['is_valid']}")
```

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/test-quality-gate.yml
name: UTF Contract Gate
on: [push, pull_request]
jobs:
  contract-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install universal-test-framework
      - name: Validate test contract
        run: |
          python - <<'EOF'
          from mcp_server.tools.validate_contract import validate_test_contract
          import glob, sys, pathlib

          failures = []
          for f in glob.glob("tests/**/*.py", recursive=True):
              content = pathlib.Path(f).read_text()
              result = validate_test_contract(test_content=content)
              if not result["is_valid"]:
                  failures.append(f"{f}: score {result['score']:.0%}")
          if failures:
              print("Contract failures:\n" + "\n".join(failures))
              sys.exit(1)
          print("All tests passed contract validation")
          EOF
```

---

## Per-Project Configuration

Create `.utf/rules/project-overrides.yaml` in your project root:

```yaml
# Raise minimum score for safety-critical code
contract:
  min_score: 0.90          # default: 0.85
  hard_block_below: 0.75

# Match your Jira project key
traceability:
  requirement_id_pattern: "^(PROJ-\\d+|AC-\\d+(\\.\\d+)?|NFR-\\d+)$"

# Tests generated per requirement per type
scenario_counts:
  happy_path: 1
  negative: 2
  boundary: 1
  edge_case: 1

# Coverage advisory thresholds (appear in report, do not block)
coverage:
  line_target: 85
  branch_target: 75
  mutation_score_target: 70
```

Rules are deep-merged: project overrides layer on top of UTF's global defaults. The 8-section contract structure itself cannot be overridden.

---

## Architecture

```
UTF MCP Server (stdio or HTTP/SSE)
│
├── mcp_server/server.py         — FastMCP entrypoint, 13 registered tools
│
├── mcp_server/engine/           — Core processing
│   ├── language_detector.py     — Detects language + framework from code/path
│   ├── rule_engine.py           — Loads and merges YAML rules
│   ├── contract_validator.py    — Enforces 8-section contract, scores tests
│   ├── template_renderer.py     — Jinja2 test file generation
│   ├── context_resolver.py      — Resolves project context for generation
│   └── framework_mapper.py      — Maps language → framework → test runner
│
├── mcp_server/tools/            — One module per MCP tool
├── mcp_server/registry/         — SQLite per-project test registry
├── mcp_server/execution/        — pytest, Vitest, Maven, go-test adapters
├── mcp_server/mutation/         — mutmut, Stryker, PIT, Gremlins adapters
├── mcp_server/reporting/        — HTML, JUnit XML, JSON report generation
├── mcp_server/feedback/         — CI listener, trend analysis, gap reopener
│
├── rules/                       — Global YAML rules (language, framework, type)
├── templates/                   — Jinja2 test templates per language/framework
├── agent-customization/         — VS Code copilot-instructions + prompt palette
└── vscode-extension/            — @utf VS Code Chat Participant (VSIX)
```

**Transport modes:**
- `stdio` — default, used by VS Code MCP client and `uvx`
- `HTTP/SSE` — for remote/team deployment (`--transport http --port 8765`)

**SQLite registry** resolves to `.utf/utf.db` relative to the **caller's project root** (the `cwd` in `mcp.json`, or the `project_dir` parameter passed to any tool). Each project has its own isolated registry — no shared state. The registry persists across all sessions until explicitly cleared.

---

## Installation Options Summary

| Method | Command | `cwd` / Registry Isolation | Requirements |
|--------|---------|---------------------------|--------------|
| **uvx** (zero-clone) | `uvx --from universal-test-framework utf-server` | `${workspaceFolder}` in `mcp.json` | [uv](https://docs.astral.sh/uv/) |
| **Local clone** | `.\scripts\install-vscode-mcp.ps1` | `${workspaceFolder}` auto-written | Git, Python 3.11+ |
| **Docker** | `docker compose up -d` | Named volume; bind-mount for per-project | Docker |
| **GitHub MCP Registry** | Auto via MCP client | `UTF_PROJECT_DIR` env var | uv (auto-installed) |
| **pip + SDK** | `pip install universal-test-framework` | Pass `project_dir` to each call | Python 3.11+ |

### Registry Isolation Rules

All setups resolve the SQLite registry path using the same priority chain:

```
1. project_dir argument (explicit per-tool call)
2. UTF_PROJECT_DIR environment variable
3. Path.cwd() at server start (fallback — avoid for multi-project use)
```

The recommended approach for all setups: set **both** `"cwd": "${workspaceFolder}"` **and**
`"env": { "UTF_PROJECT_DIR": "${workspaceFolder}" }` in your `mcp.json` entry.
This ensures registry isolation works even if a tool call omits `project_dir`.


## Security

- All MCP tool inputs are validated via Pydantic before processing
- No secrets, credentials, or PII are logged or stored
- The registry (`utf.db`) is local to each project and never transmitted
- Docker image runs as non-root user
- Rate limiting is enforced on the HTTP/SSE transport

---

## License

MIT — see [LICENSE](LICENSE)
