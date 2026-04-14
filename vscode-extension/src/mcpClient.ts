import * as cp from "child_process";
import * as path from "path";

export interface McpToolResult {
  content?: Array<{ type: string; text: string }>;
  error?: string;
  isError?: boolean;
}

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: unknown;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string };
}

/**
 * Lightweight MCP stdio client.
 * Spawns the UTF server subprocess, sends a single JSON-RPC tools/call request,
 * reads the response and shuts down. Stateless — one request per process.
 */
export class UtfMcpClient {
  private utfRoot: string;
  private pythonPath: string;
  private requestId = 1;

  constructor(utfRoot: string) {
    this.utfRoot = utfRoot;
    this.pythonPath = this.resolvePython();
  }

  /** Whether to use uvx instead of a local venv python. */
  private useUvx = false;

  private resolvePython(): string {
    const fs = require("fs");
    const { execSync } = require("child_process");

    // Prefer local .venv (fastest, no download)
    const venvPy = path.join(this.utfRoot, ".venv", "Scripts", "python.exe");
    if (fs.existsSync(venvPy)) return venvPy;

    // Unix venv fallback
    const venvPyUnix = path.join(this.utfRoot, ".venv", "bin", "python");
    if (fs.existsSync(venvPyUnix)) return venvPyUnix;

    // uvx fallback — zero-clone mode (uv must be on PATH)
    try {
      execSync("uvx --version", { encoding: "utf8", stdio: "pipe" });
      this.useUvx = true;
      return "uvx"; // launcher, not python
    } catch {
      // uvx not available
    }

    // Last resort: system python
    try {
      return execSync("where python", { encoding: "utf8" }).split("\n")[0].trim();
    } catch {
      return "python";
    }
  }

  /** Call a UTF MCP tool and return the parsed result. */
  async callTool(toolName: string, args: Record<string, unknown>): Promise<McpToolResult> {
    // Build spawn args: local venv python OR uvx zero-clone mode
    const spawnCmd = this.pythonPath;
    const spawnArgs = this.useUvx
      ? ["--from", "universal-test-framework", "utf-server", "--transport", "stdio"]
      : ["-m", "mcp_server.server", "--transport", "stdio"];
    const spawnCwd = this.useUvx ? process.cwd() : this.utfRoot;
    const spawnEnv = this.useUvx
      ? { ...process.env }
      : { ...process.env, PYTHONPATH: this.utfRoot };

    return new Promise((resolve, reject) => {
      const proc = cp.spawn(spawnCmd, spawnArgs, {
        cwd: spawnCwd,
        env: spawnEnv,
        stdio: ["pipe", "pipe", "pipe"],
      });

      let stdout = "";
      let stderr = "";
      const timeout = setTimeout(() => {
        proc.kill();
        reject(new Error("UTF MCP server timed out after 60s"));
      }, 60_000);

      proc.stdout.on("data", (chunk: Buffer) => {
        stdout += chunk.toString();
      });
      proc.stderr.on("data", (chunk: Buffer) => {
        stderr += chunk.toString();
      });

      proc.on("error", (err) => {
        clearTimeout(timeout);
        reject(new Error(`Failed to start UTF server: ${err.message}`));
      });

      // MCP stdio handshake: initialize → initialized → tools/call → exit
      proc.on("spawn", () => {
        const send = (msg: JsonRpcRequest | { jsonrpc: "2.0"; method: string; params: unknown }) => {
          const json = JSON.stringify(msg);
          proc.stdin.write(`Content-Length: ${Buffer.byteLength(json)}\r\n\r\n${json}`);
        };

        // Step 1: initialize
        send({
          jsonrpc: "2.0",
          id: this.requestId++,
          method: "initialize",
          params: {
            protocolVersion: "2024-11-05",
            capabilities: {},
            clientInfo: { name: "utf-vscode-extension", version: "0.1.0" },
          },
        });

        // Buffer and parse LSP-framed messages
        let buffer = "";
        const pendingMessages: JsonRpcResponse[] = [];
        let initialized = false;

        proc.stdout.removeAllListeners("data");
        proc.stdout.on("data", (chunk: Buffer) => {
          buffer += chunk.toString();
          // Parse Content-Length framed messages
          while (true) {
            const headerEnd = buffer.indexOf("\r\n\r\n");
            if (headerEnd === -1) break;
            const header = buffer.slice(0, headerEnd);
            const lengthMatch = header.match(/Content-Length:\s*(\d+)/i);
            if (!lengthMatch) { buffer = buffer.slice(headerEnd + 4); continue; }
            const length = parseInt(lengthMatch[1], 10);
            const bodyStart = headerEnd + 4;
            if (buffer.length < bodyStart + length) break;
            const body = buffer.slice(bodyStart, bodyStart + length);
            buffer = buffer.slice(bodyStart + length);
            try {
              const msg = JSON.parse(body) as JsonRpcResponse;
              pendingMessages.push(msg);
              handleMessage(msg);
            } catch {
              // non-JSON frame, skip
            }
          }
        });

        const handleMessage = (msg: JsonRpcResponse) => {
          // Response to initialize
          if (!initialized && msg.id === 1) {
            initialized = true;
            // Send initialized notification
            send({ jsonrpc: "2.0", method: "notifications/initialized", params: {} });
            // Step 2: send tools/call
            send({
              jsonrpc: "2.0",
              id: this.requestId++,
              method: "tools/call",
              params: { name: toolName, arguments: args },
            });
            return;
          }
          // Response to tools/call
          if (msg.id === 2) {
            clearTimeout(timeout);
            proc.stdin.end();
            proc.kill();
            if (msg.error) {
              resolve({ error: msg.error.message, isError: true });
            } else {
              resolve(msg.result as McpToolResult);
            }
          }
        };
      });
    });
  }

  /** Extract text content from a McpToolResult. */
  static extractText(result: McpToolResult): string {
    if (result.isError || result.error) return `Error: ${result.error}`;
    if (!result.content || result.content.length === 0) return "(no output)";
    return result.content
      .filter((c) => c.type === "text")
      .map((c) => c.text)
      .join("\n");
  }
}
