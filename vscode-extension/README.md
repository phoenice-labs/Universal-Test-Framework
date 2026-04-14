# Universal Test Framework — VS Code Extension

> The `@utf` Copilot Chat Participant — Option C in the UTF production distribution.

## What this extension does

Adds a `@utf` participant to VS Code Copilot Chat that routes slash commands directly to the UTF MCP server:

| Command | Effect |
|---|---|
| `@utf /generate-tests unit` | Generate unit tests for the active file |
| `@utf /generate-tests api` | Generate API tests |
| `@utf /generate-tests e2e` | Generate E2E tests |
| `@utf /generate-tests security` | Generate security tests |
| `@utf /validate-contract` | Validate selected test against the 8-section contract |
| `@utf /coverage-gaps` | Analyze coverage gaps |
| `@utf /traceability` | Build requirements traceability matrix |
| `@utf /report` | Generate & open HTML contract report |
| `@utf /status` | Show UTF server health |

## Prerequisites

Run the global installer first:
```powershell
cd C:\path\to\Universal-Test-Framework
.\scripts\install-vscode-mcp.ps1
```

## Building

```powershell
cd vscode-extension
npm install
npm run compile
vsce package
# → universal-test-framework-0.1.0.vsix
```

## Installing

```powershell
code --install-extension universal-test-framework-0.1.0.vsix
```

Or: VS Code → Extensions → `...` → Install from VSIX.

## How it works

1. Extension activates and creates a `@utf` Chat Participant
2. On each command, it spawns the UTF Python server as a subprocess (stdio MCP)
3. Sends a JSON-RPC `tools/call` request with the appropriate tool name and arguments
4. Formats the response as Markdown in the Copilot Chat window
5. For `/report`, automatically opens the HTML file in VS Code SimpleBrowser
