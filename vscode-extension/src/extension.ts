import * as vscode from "vscode";
import * as path from "path";
import { UtfMcpClient } from "./mcpClient";
import { registerParticipant } from "./participant";

let client: UtfMcpClient | undefined;

export function activate(context: vscode.ExtensionContext): void {
  // UTF root = parent of the vscode-extension directory
  const utfRoot = path.resolve(context.extensionPath, "..");
  client = new UtfMcpClient(utfRoot);

  // Register the @utf chat participant
  registerParticipant(context, client);

  // Register palette commands
  context.subscriptions.push(
    vscode.commands.registerCommand("utf.generateTests", async () => {
      const types = ["unit", "api", "integration", "e2e", "security", "contract", "performance"];
      const picked = await vscode.window.showQuickPick(types, {
        placeHolder: "Select test type to generate",
      });
      if (!picked) return;
      // Open Copilot Chat with a pre-filled prompt
      await vscode.commands.executeCommand(
        "workbench.panel.chat.view.copilot.focus"
      );
      await vscode.commands.executeCommand(
        "vscode.editorChat.start",
        { message: `@utf /generate-tests ${picked}` }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("utf.openReport", async () => {
      if (!client) return;
      const workspaceDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      // Try common report paths
      const candidates = [
        workspaceDir ? path.join(workspaceDir, "utf-tests", "reports", "auto_report.html") : null,
        workspaceDir ? path.join(workspaceDir, "utf-tests", "reports", "last_contract_report.html") : null,
        path.join(utfRoot, "agent-customization", "dogfood_html_report", "contract_report.html"),
      ].filter(Boolean) as string[];

      let reportPath: string | undefined;
      for (const candidate of candidates) {
        if (require("fs").existsSync(candidate)) {
          reportPath = candidate;
          break;
        }
      }

      if (reportPath) {
        await vscode.commands.executeCommand("simpleBrowser.show", vscode.Uri.file(reportPath));
      } else {
        // Generate a fresh one
        vscode.window.showInformationMessage("Generating UTF report…");
        const result = await client.callTool("generate_report", {
          cwd: workspaceDir ?? utfRoot,
        });
        const text = UtfMcpClient.extractText(result);
        const match = text.match(/([A-Za-z]:[\\\/][^\s"']+\.html)/);
        if (match) {
          await vscode.commands.executeCommand("simpleBrowser.show", vscode.Uri.file(match[1]));
        } else {
          vscode.window.showWarningMessage("UTF: Could not locate HTML report. " + text.slice(0, 100));
        }
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("utf.showStatus", async () => {
      if (!client) return;
      const result = await client.callTool("utf_health", {});
      const text = UtfMcpClient.extractText(result);
      vscode.window.showInformationMessage(`UTF Status: ${text.slice(0, 120)}`);
    })
  );

  // Status bar item
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBar.text = "$(beaker) UTF";
  statusBar.tooltip = "Universal Test Framework — click to open report";
  statusBar.command = "utf.openReport";
  statusBar.show();
  context.subscriptions.push(statusBar);
}

export function deactivate(): void {
  client = undefined;
}
