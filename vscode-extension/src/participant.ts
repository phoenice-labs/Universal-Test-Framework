import * as vscode from "vscode";
import * as path from "path";
import { UtfMcpClient, McpToolResult } from "./mcpClient";

// Resolve UTF root from extension installation path
function resolveUtfRoot(context: vscode.ExtensionContext): string {
  // Extension lives inside vscode-extension/ which is a child of the UTF root
  return path.resolve(context.extensionPath, "..");
}

/** Map slash command names to test_type strings */
const TEST_TYPE_MAP: Record<string, string> = {
  unit: "unit",
  api: "api",
  integration: "integration",
  e2e: "e2e",
  security: "security",
  contract: "contract",
  performance: "performance",
};

/** Get source code from the active editor (or selection). */
function getActiveSourceCode(): string | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return undefined;
  const selection = editor.selection;
  if (!selection.isEmpty) {
    return editor.document.getText(selection);
  }
  return editor.document.getText();
}

/** Get the active file path. */
function getActiveFilePath(): string | undefined {
  return vscode.window.activeTextEditor?.document.fileName;
}

/** Format MCP tool result into Markdown for Copilot Chat. */
function formatResult(
  stream: vscode.ChatResponseStream,
  title: string,
  text: string
): void {
  stream.markdown(`## ${title}\n\n`);
  // If the result looks like JSON, render as code block
  const trimmed = text.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    stream.markdown("```json\n" + trimmed + "\n```\n");
  } else {
    stream.markdown(trimmed + "\n");
  }
}

/** Handle @utf /generate-tests [type] */
async function handleGenerateTests(
  subtype: string,
  request: vscode.ChatRequest,
  stream: vscode.ChatResponseStream,
  client: UtfMcpClient
): Promise<void> {
  const testType = TEST_TYPE_MAP[subtype] ?? "unit";
  const sourceCode = getActiveSourceCode();
  const filePath = getActiveFilePath();

  stream.markdown(`⚙️ **UTF**: Calling \`generate_tests\` (type: **${testType}**)…\n\n`);

  const args: Record<string, unknown> = { test_type: testType };
  if (sourceCode) args.source_code = sourceCode.slice(0, 8000); // cap to avoid token overflow
  if (filePath) args.file_path = filePath;
  // Pass any extra text from the user as requirements
  if (request.prompt.trim()) args.requirements_text = request.prompt.trim();

  const result = await client.callTool("generate_tests", args);
  const text = UtfMcpClient.extractText(result);

  formatResult(stream, `UTF — ${testType.toUpperCase()} Tests (8-Section Contract)`, text);
  stream.markdown("\n---\n💡 Tip: use `@utf /validate-contract` to validate an individual test, or `@utf /report` to generate the full HTML report.\n");
}

/** Handle @utf /validate-contract */
async function handleValidateContract(
  request: vscode.ChatRequest,
  stream: vscode.ChatResponseStream,
  client: UtfMcpClient
): Promise<void> {
  const content = getActiveSourceCode() ?? request.prompt.trim();
  if (!content) {
    stream.markdown("⚠️ Select a test in the editor (or paste it after the command) to validate.\n");
    return;
  }
  stream.markdown("⚙️ **UTF**: Validating test against 8-section contract…\n\n");
  const result = await client.callTool("validate_test_contract", { test_content: content });
  const text = UtfMcpClient.extractText(result);
  formatResult(stream, "UTF — Contract Validation Result", text);
}

/** Handle @utf /coverage-gaps */
async function handleCoverageGaps(
  stream: vscode.ChatResponseStream,
  client: UtfMcpClient
): Promise<void> {
  stream.markdown("⚙️ **UTF**: Analyzing coverage gaps…\n\n");
  const result = await client.callTool("analyze_coverage", { tests: [] });
  const text = UtfMcpClient.extractText(result);
  formatResult(stream, "UTF — Coverage Gap Analysis", text);
}

/** Handle @utf /traceability */
async function handleTraceability(
  stream: vscode.ChatResponseStream,
  client: UtfMcpClient
): Promise<void> {
  stream.markdown("⚙️ **UTF**: Building traceability matrix…\n\n");
  const result = await client.callTool("build_traceability_matrix", { tests: [] });
  const text = UtfMcpClient.extractText(result);
  formatResult(stream, "UTF — Requirements Traceability Matrix", text);
}

/** Handle @utf /report — generate HTML report and open it */
async function handleReport(
  stream: vscode.ChatResponseStream,
  client: UtfMcpClient,
  context: vscode.ExtensionContext
): Promise<void> {
  stream.markdown("⚙️ **UTF**: Generating contract compliance report…\n\n");
  const utfRoot = resolveUtfRoot(context);

  // Determine project dir from open workspace
  const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const args: Record<string, unknown> = {};
  if (workspaceDir) args.cwd = workspaceDir;

  const result = await client.callTool("generate_report", args);
  const text = UtfMcpClient.extractText(result);
  formatResult(stream, "UTF — Contract Compliance Report Generated", text);

  // Try to open the HTML report if path is mentioned in output
  const htmlMatch = text.match(/([A-Za-z]:[\\\/][^\s"']+\.html)/);
  if (htmlMatch) {
    const htmlPath = htmlMatch[1];
    stream.markdown(`\n📄 Opening report: \`${htmlPath}\`\n`);
    await vscode.commands.executeCommand(
      "simpleBrowser.show",
      vscode.Uri.file(htmlPath)
    );
  }
}

/** Handle @utf /status */
async function handleStatus(
  stream: vscode.ChatResponseStream,
  client: UtfMcpClient
): Promise<void> {
  stream.markdown("⚙️ **UTF**: Checking server status…\n\n");
  const result = await client.callTool("utf_health", {});
  const text = UtfMcpClient.extractText(result);
  formatResult(stream, "UTF — Server Status", text);
}

export function registerParticipant(
  context: vscode.ExtensionContext,
  client: UtfMcpClient
): void {
  const participant = vscode.chat.createChatParticipant(
    "utf",
    async (
      request: vscode.ChatRequest,
      _chatContext: vscode.ChatContext,
      stream: vscode.ChatResponseStream,
      _token: vscode.CancellationToken
    ) => {
      const cmd = request.command ?? "";
      const prompt = request.prompt.trim().toLowerCase();

      try {
        if (cmd === "generate-tests") {
          // Extract subtype from prompt: "e2e", "unit", etc.
          const subtype =
            Object.keys(TEST_TYPE_MAP).find((t) => prompt.includes(t)) ??
            prompt.split(/\s+/)[0] ??
            "unit";
          await handleGenerateTests(subtype, request, stream, client);
        } else if (cmd === "validate-contract") {
          await handleValidateContract(request, stream, client);
        } else if (cmd === "coverage-gaps") {
          await handleCoverageGaps(stream, client);
        } else if (cmd === "traceability") {
          await handleTraceability(stream, client);
        } else if (cmd === "report") {
          await handleReport(stream, client, context);
        } else if (cmd === "status") {
          await handleStatus(stream, client);
        } else {
          // No slash command — try to infer from natural language
          if (prompt.includes("generate") || prompt.includes("test")) {
            const subtype = Object.keys(TEST_TYPE_MAP).find((t) => prompt.includes(t)) ?? "unit";
            await handleGenerateTests(subtype, request, stream, client);
          } else if (prompt.includes("validate") || prompt.includes("contract")) {
            await handleValidateContract(request, stream, client);
          } else if (prompt.includes("gap") || prompt.includes("coverage")) {
            await handleCoverageGaps(stream, client);
          } else if (prompt.includes("traceability") || prompt.includes("matrix")) {
            await handleTraceability(stream, client);
          } else if (prompt.includes("report")) {
            await handleReport(stream, client, context);
          } else {
            // Default: show help
            stream.markdown(`## UTF — Universal Test Framework

**Available commands:**

| Command | What it does |
|---|---|
| \`@utf /generate-tests unit\` | Generate unit tests for the active file |
| \`@utf /generate-tests api\` | Generate API tests |
| \`@utf /generate-tests integration\` | Generate integration tests |
| \`@utf /generate-tests e2e\` | Generate E2E tests |
| \`@utf /generate-tests security\` | Generate security tests |
| \`@utf /generate-tests contract\` | Generate contract/CDC tests |
| \`@utf /generate-tests performance\` | Generate performance tests |
| \`@utf /validate-contract\` | Validate selected test against 8-section contract |
| \`@utf /coverage-gaps\` | Analyze what's not covered |
| \`@utf /traceability\` | Build requirements traceability matrix |
| \`@utf /report\` | Generate & open HTML contract report |
| \`@utf /status\` | Show UTF server health |

All tests must conform to the **8-section contract**: Test ID · Why Generated · Requirement Mapping · How it Exercises · Coverage Contribution · Expected Outcome · Gaps · Meaningfulness Check.
`);
          }
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        stream.markdown(`❌ **UTF Error**: ${msg}\n\nMake sure the UTF server is running. Run:\n\`\`\`\n.\\scripts\\install-vscode-mcp.ps1\n\`\`\`\n`);
      }
    }
  );

  participant.iconPath = new vscode.ThemeIcon("beaker");
  context.subscriptions.push(participant);
}
