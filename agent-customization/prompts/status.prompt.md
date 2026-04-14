---
mode: agent
description: Check Universal Test Framework MCP server health and installation status
tools:
  - health
---

Call the `health` tool and return a formatted status report.

## Output Format

### UTF MCP Server Status

| Field | Value |
|-------|-------|
| **Status** | {status} |
| **Version** | {version} |
| **Uptime** | {uptime_s}s |
| **Registered Tools** | {tools} |

> ✅ UTF MCP server is running and ready.
