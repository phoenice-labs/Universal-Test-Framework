# =============================================================================
# Universal Test Framework — VS Code Setup Script
# =============================================================================
# One-command setup: MCP registration + global instructions + project scaffold
# Supports: local-clone mode (Option B) AND uvx/PyPI mode (no clone needed)
#
# USAGE:
#   # Global setup (run once from UTF root):
#   .\scripts\install-vscode-mcp.ps1
#
#   # Per-project setup (run from inside a project directory):
#   .\scripts\install-vscode-mcp.ps1 -InitProject
#   .\scripts\install-vscode-mcp.ps1 -InitProject -ProjectDir "C:\my-project"
#
#   # Check current installation status:
#   .\scripts\install-vscode-mcp.ps1 -Status
#
#   # Force uvx mode even if local venv exists:
#   .\scripts\install-vscode-mcp.ps1 -UseUvx
#
#   # Uninstall:
#   .\scripts\install-vscode-mcp.ps1 -Uninstall
# =============================================================================

param(
    [string]$ServerName  = "utf",
    [switch]$InitProject,
    [string]$ProjectDir  = (Get-Location).Path,
    [switch]$Status,
    [switch]$Uninstall,
    [switch]$UseUvx       # Force uvx mode (skip local venv)
)

$ErrorActionPreference = "Stop"
$script:Errors = 0

# UTF root = parent of the scripts/ folder
$utfRoot = Split-Path -Parent $PSScriptRoot

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
function Write-Step  { param($msg) Write-Host "`n[$([char]0x25B6)] $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "  [XX] $msg" -ForegroundColor Red; $script:Errors++ }
function Write-Info  { param($msg) Write-Host "  ... $msg" -ForegroundColor Gray }

# Find VS Code's mcp.json (primary) with settings.json as legacy fallback
function Find-McpJsonPath {
    $candidates = @(
        "$env:APPDATA\Code\User\mcp.json",
        "$env:APPDATA\Code - Insiders\User\mcp.json"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    # Create it — VS Code will pick it up on restart
    $default = "$env:APPDATA\Code\User\mcp.json"
    New-Item -ItemType Directory -Force -Path (Split-Path $default) | Out-Null
    Set-Content -Path $default -Value '{"servers":{},"inputs":[]}' -Encoding UTF8
    return $default
}

# Find VS Code settings.json (for legacy mcp block cleanup only)
function Find-VsCodeSettings {
    $candidates = @(
        "$env:APPDATA\Code\User\settings.json",
        "$env:APPDATA\Code - Insiders\User\settings.json"
    )
    foreach ($p in $candidates) { if (Test-Path $p) { return $p } }
    return $null
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @{} }
    $content = Get-Content $Path -Raw -Encoding UTF8
    if (-not $content.Trim()) { return @{} }
    # Strip JSONC comments before parsing
    $stripped = $content -replace '//[^\r\n]*', ''
    try { return $stripped | ConvertFrom-Json -AsHashtable }
    catch { return @{} }
}

function Write-JsonFile {
    param([string]$Path, [hashtable]$Data)
    $json = $Data | ConvertTo-Json -Depth 15
    Set-Content -Path $Path -Value $json -Encoding UTF8
}

function Find-Python {
    $venvPy = Join-Path $utfRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) { return $venvPy }
    $sysPy = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    if ($sysPy) { return $sysPy }
    return "python"
}

function Find-Uvx {
    $uvx = (Get-Command uvx -ErrorAction SilentlyContinue)?.Source
    if ($uvx) { return $uvx }
    # Common install locations
    $candidates = @(
        "$env:USERPROFILE\.cargo\bin\uvx.exe",
        "$env:LOCALAPPDATA\uv\bin\uvx.exe",
        "$env:USERPROFILE\.local\bin\uvx"
    )
    foreach ($c in $candidates) { if (Test-Path $c -ErrorAction SilentlyContinue) { return $c } }
    return $null
}

function Find-CodeCmd {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd",
        "$env:ProgramFiles\Microsoft VS Code\bin\code.cmd",
        "code.cmd"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c -ErrorAction SilentlyContinue) { return $c }
        if (Get-Command $c -ErrorAction SilentlyContinue) { return $c }
    }
    return $null
}

# Clean up legacy mcp block from settings.json (VS Code moved it to mcp.json)
function Remove-LegacyMcpFromSettings {
    param([string]$ServerName)
    $settingsFile = Find-VsCodeSettings
    if (-not $settingsFile) { return }
    $settings = Read-JsonFile $settingsFile
    if ($settings.ContainsKey("mcp") -and
        $settings["mcp"] -is [hashtable] -and
        $settings["mcp"].ContainsKey("servers") -and
        $settings["mcp"]["servers"] -is [hashtable] -and
        $settings["mcp"]["servers"].ContainsKey($ServerName)) {
        $settings["mcp"]["servers"].Remove($ServerName)
        # Remove empty mcp.servers block
        if ($settings["mcp"]["servers"].Count -eq 0) {
            $settings["mcp"].Remove("servers")
        }
        if ($settings["mcp"].Count -eq 0) {
            $settings.Remove("mcp")
        }
        Write-JsonFile $settingsFile $settings
        Write-Info "Removed legacy 'mcp' block from settings.json (now managed via mcp.json)"
    }
}

# --------------------------------------------------------------------------
# STATUS mode
# --------------------------------------------------------------------------
if ($Status) {
    Write-Host "`n=== UTF Installation Status ===" -ForegroundColor Cyan

    $mcpFile = Find-McpJsonPath
    $mcpData = Read-JsonFile $mcpFile
    $hasMcpJson = $mcpData.ContainsKey("servers") -and $mcpData["servers"] -is [hashtable] -and $mcpData["servers"].ContainsKey($ServerName)

    $settingsFile = Find-VsCodeSettings
    $hasLegacy = $false
    if ($settingsFile) {
        $s = Read-JsonFile $settingsFile
        $hasLegacy = $s.ContainsKey("mcp") -and $s["mcp"] -is [hashtable] -and
                     $s["mcp"].ContainsKey("servers") -and $s["mcp"]["servers"] -is [hashtable] -and
                     $s["mcp"]["servers"].ContainsKey($ServerName)
    }

    $globalPromptsDir = "$env:APPDATA\Code\User\prompts"
    $hasInstructions  = Test-Path "$globalPromptsDir\utf-instructions.instructions.md"
    $promptCount      = (Get-ChildItem "$globalPromptsDir\utf-*.prompt.md" -ErrorAction SilentlyContinue).Count
    $hasVenv          = Test-Path (Join-Path $utfRoot ".venv\Scripts\python.exe")
    $hasUvx           = $null -ne (Find-Uvx)
    $projInstructions = Test-Path (Join-Path $ProjectDir ".github\copilot-instructions.md")
    $hasExt           = (Get-ChildItem "$env:USERPROFILE\.vscode\extensions" -Filter "utf.*" -ErrorAction SilentlyContinue).Count -gt 0

    $mcpMode = if ($hasMcpJson) {
        $cmd = $mcpData["servers"][$ServerName]["command"]
        if ($cmd -match "uvx") { "uvx (PyPI)" } else { "local venv" }
    } else { "NOT registered" }

    Write-Host "  MCP registered (mcp.json)             : $(if ($hasMcpJson) {'YES — ' + $mcpMode} else {'NO'})" -ForegroundColor $(if ($hasMcpJson) {'Green'} else {'Red'})
    Write-Host "  Legacy mcp block in settings.json     : $(if ($hasLegacy) {'YES (run -Uninstall to clean)'} else {'NO (clean)'})" -ForegroundColor $(if ($hasLegacy) {'Yellow'} else {'Green'})
    Write-Host "  Global instructions (.instructions.md): $(if ($hasInstructions) {'YES'} else {'NO'})" -ForegroundColor $(if ($hasInstructions) {'Green'} else {'Red'})
    $expectedPrompts = (Get-ChildItem (Join-Path $utfRoot "agent-customization\prompts") -Filter "*.prompt.md" -ErrorAction SilentlyContinue).Count
    Write-Host "  Prompt files copied ($promptCount / $expectedPrompts)         : $(if ($promptCount -eq $expectedPrompts) {'YES'} else {'PARTIAL ' + $promptCount + '/' + $expectedPrompts})" -ForegroundColor $(if ($promptCount -eq $expectedPrompts) {'Green'} else {'Yellow'})
    Write-Host "  @utf VS Code extension installed      : $(if ($hasExt) {'YES'} else {'NO'})" -ForegroundColor $(if ($hasExt) {'Green'} else {'Yellow'})
    Write-Host "  Python venv present                   : $(if ($hasVenv) {'YES'} else {'NO'})" -ForegroundColor $(if ($hasVenv) {'Green'} else {'Yellow'})
    Write-Host "  uvx available (PyPI/no-clone mode)    : $(if ($hasUvx) {'YES'} else {'NO (install uv from https://docs.astral.sh/uv)'})" -ForegroundColor $(if ($hasUvx) {'Green'} else {'Yellow'})
    Write-Host "  Project copilot-instructions.md       : $(if ($projInstructions) {'YES'} else {'NO (run -InitProject)'})" -ForegroundColor $(if ($projInstructions) {'Green'} else {'Yellow'})
    Write-Host ""
    exit 0
}

# --------------------------------------------------------------------------
# UNINSTALL mode
# --------------------------------------------------------------------------
if ($Uninstall) {
    Write-Step "Uninstalling UTF from VS Code..."

    # Remove from mcp.json
    $mcpFile = Find-McpJsonPath
    $mcpData = Read-JsonFile $mcpFile
    if ($mcpData.ContainsKey("servers") -and $mcpData["servers"] -is [hashtable] -and $mcpData["servers"].ContainsKey($ServerName)) {
        $mcpData["servers"].Remove($ServerName)
        Write-JsonFile $mcpFile $mcpData
        Write-Ok "Removed '$ServerName' from mcp.json"
    } else {
        Write-Warn "'$ServerName' was not in mcp.json"
    }

    # Remove legacy from settings.json
    Remove-LegacyMcpFromSettings $ServerName

    # Remove global prompt/instruction files
    $globalPromptsDir = "$env:APPDATA\Code\User\prompts"
    Remove-Item "$globalPromptsDir\utf-instructions.instructions.md" -ErrorAction SilentlyContinue
    Remove-Item "$globalPromptsDir\utf-*.prompt.md"                  -ErrorAction SilentlyContinue
    Remove-Item "$globalPromptsDir\utf-*.instructions.md"            -ErrorAction SilentlyContinue
    Remove-Item "$globalPromptsDir\utf-*.agent.md"                   -ErrorAction SilentlyContinue
    Write-Ok "Removed global prompt/instruction files"

    Write-Host "`nUninstall complete. Reload VS Code to apply." -ForegroundColor Yellow
    exit 0
}

# ==========================================================================
# MAIN INSTALL
# ==========================================================================
Write-Host @"

  ╔══════════════════════════════════════════════════════════════╗
  ║        Universal Test Framework — VS Code Setup              ║
  ╚══════════════════════════════════════════════════════════════╝
"@ -ForegroundColor Cyan

# --------------------------------------------------------------------------
# STEP 1: Resolve Python / uvx — pick best launch mode
# --------------------------------------------------------------------------
Write-Step "Step 1/6: Resolve launch mode (uvx or local venv)"

$uvxPath   = Find-Uvx
$venvPy    = Join-Path $utfRoot ".venv\Scripts\python.exe"
$useUvxMode = $UseUvx -or ($uvxPath -and -not (Test-Path $venvPy))

if ($useUvxMode -and $uvxPath) {
    Write-Ok "uvx found: $uvxPath — will use PyPI/uvx mode (no local clone required)"
    $launchMode = "uvx"
    $pythonPath = $uvxPath  # used for health check only
} else {
    # Local venv mode (Option B original behaviour)
    $pythonPath = Find-Python
    Write-Info "Python: $pythonPath"
    $launchMode = "local"

    if (-not (Test-Path $venvPy)) {
        Write-Info "Creating virtual environment..."
        try {
            & python -m venv (Join-Path $utfRoot ".venv") 2>&1 | Out-Null
            & $venvPy -m pip install -e $utfRoot --quiet 2>&1 | Out-Null
            $pythonPath = $venvPy
            Write-Ok "Virtual environment created and UTF installed"
        } catch {
            Write-Warn "Could not create venv — using system Python: $pythonPath"
        }
    } else {
        $pythonPath = $venvPy
        Write-Ok "Local venv found: $venvPy"
        try {
            & $pythonPath -m pip install -e $utfRoot --quiet 2>&1 | Out-Null
            Write-Ok "Dependencies up-to-date"
        } catch {
            Write-Warn "pip install had warnings (non-fatal)"
        }
    }

    # Offer to also install uv if missing (non-blocking)
    if (-not $uvxPath) {
        Write-Info "Tip: install 'uv' for zero-clone uvx mode → https://docs.astral.sh/uv/getting-started/installation/"
    }
}

# --------------------------------------------------------------------------
# STEP 2: Write MCP entry to mcp.json (primary); clean legacy settings.json
# --------------------------------------------------------------------------
Write-Step "Step 2/6: Register MCP server in mcp.json"

$mcpFile = Find-McpJsonPath
Write-Info "mcp.json: $mcpFile"
$mcpData = Read-JsonFile $mcpFile

if (-not $mcpData.ContainsKey("servers"))  { $mcpData["servers"] = @{} }
if (-not $mcpData.ContainsKey("inputs"))   { $mcpData["inputs"]  = @() }

if ($launchMode -eq "uvx") {
    # uvx mode: no hardcoded paths — works on any machine with uv installed
    # cwd = ${workspaceFolder} ensures the SQLite registry lands in the
    # developer's own project under <project>/.utf/utf.db (not the UTF install dir).
    $mcpEntry = @{
        type        = "stdio"
        command     = $uvxPath
        args        = @("--from", "universal-test-framework", "utf-server", "--transport", "stdio")
        cwd         = '${workspaceFolder}'
        description = "Universal Test Framework — polyglot test generation with 8-section contract (uvx/PyPI)"
    }
    Write-Info "Mode: uvx — command: uvx --from universal-test-framework utf-server --transport stdio"
} else {
    # Local venv mode: use absolute path + PYTHONPATH.
    # cwd = ${workspaceFolder} so the SQLite registry and reports land in the
    # developer's project under <project>/.utf/, not the UTF install directory.
    $mcpEntry = @{
        type        = "stdio"
        command     = $pythonPath
        args        = @("-m", "mcp_server.server", "--transport", "stdio")
        cwd         = '${workspaceFolder}'
        description = "Universal Test Framework — polyglot test generation with 8-section contract"
        env         = @{
            PYTHONPATH               = $utfRoot
            FASTMCP_SHOW_SERVER_BANNER = "0"
        }
    }
    Write-Info "Mode: local venv — cwd: `${workspaceFolder} (registry isolated per project)"
}

$mcpData["servers"][$ServerName] = $mcpEntry
Write-JsonFile $mcpFile $mcpData
Write-Ok "MCP server '$ServerName' registered in mcp.json"

# Clean up any legacy mcp block from settings.json
Remove-LegacyMcpFromSettings $ServerName

# --------------------------------------------------------------------------
# STEP 3: Copy global Copilot instructions + prompt palette
# --------------------------------------------------------------------------
Write-Step "Step 3/6: Install global Copilot instructions & prompt palette"
$globalPromptsDir = "$env:APPDATA\Code\User\prompts"
New-Item -ItemType Directory -Force -Path $globalPromptsDir | Out-Null

$srcInstructions = Join-Path $utfRoot "agent-customization\copilot-instructions.md"
$dstInstructions = Join-Path $globalPromptsDir "utf-instructions.instructions.md"
if (Test-Path $srcInstructions) {
    Copy-Item $srcInstructions $dstInstructions -Force
    Write-Ok "Global instructions → $dstInstructions"
} else {
    Write-Fail "Source not found: $srcInstructions"
}

$srcInstrDir = Join-Path $utfRoot "agent-customization\instructions"
if (Test-Path $srcInstrDir) {
    foreach ($f in Get-ChildItem $srcInstrDir -Filter "*.instructions.md") {
        Copy-Item $f.FullName (Join-Path $globalPromptsDir "utf-$($f.Name)") -Force
        Write-Info "  Instructions: $($f.Name)"
    }
}

$srcPromptsDir = Join-Path $utfRoot "agent-customization\prompts"
$promptsCopied = 0
if (Test-Path $srcPromptsDir) {
    foreach ($f in Get-ChildItem $srcPromptsDir -Filter "*.prompt.md") {
        Copy-Item $f.FullName (Join-Path $globalPromptsDir "utf-$($f.Name)") -Force
        Write-Info "  Prompt: $($f.Name)"
        $promptsCopied++
    }
}
Write-Ok "$promptsCopied prompt files installed (VS Code prompt palette)"

$srcAgent = Join-Path $utfRoot "agent-customization\agents\test-architect.agent.md"
if (Test-Path $srcAgent) {
    Copy-Item $srcAgent (Join-Path $globalPromptsDir "utf-test-architect.agent.md") -Force
    Write-Ok "Agent: test-architect.agent.md"
}

# --------------------------------------------------------------------------
# STEP 4: Install @utf VS Code Chat Participant extension (Option C)
# --------------------------------------------------------------------------
Write-Step "Step 4/6: Install @utf VS Code Chat Participant extension"
$vsixPath = Join-Path $utfRoot "vscode-extension\universal-test-framework-0.1.0.vsix"
$codeCmd  = Find-CodeCmd

if (-not (Test-Path $vsixPath)) {
    Write-Info "VSIX not found — building from source..."
    $extDir = Join-Path $utfRoot "vscode-extension"
    try {
        Push-Location $extDir
        npm install --silent 2>&1 | Out-Null
        npm run compile 2>&1 | Out-Null
        vsce package --no-dependencies --allow-missing-repository 2>&1 | Out-Null
        Pop-Location
        if (Test-Path $vsixPath) { Write-Ok "VSIX built: $vsixPath" }
        else { Write-Warn "VSIX build produced no output — skipping extension install" }
    } catch {
        if (Test-Path variable:global:StackTrace) { Pop-Location }
        Write-Warn "VSIX build failed: $_ (extension install skipped)"
    }
}

if ((Test-Path $vsixPath) -and $codeCmd) {
    try {
        $installOut = & $codeCmd --install-extension $vsixPath 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "@utf extension installed — use '@utf /generate-tests e2e' in Copilot Chat"
        } else {
            Write-Warn "Extension install returned exit code $LASTEXITCODE : $installOut"
        }
    } catch {
        Write-Warn "Extension install failed: $_ — manual: code --install-extension $vsixPath"
    }
} elseif (-not $codeCmd) {
    Write-Warn "VS Code CLI not found — install manually: code --install-extension $vsixPath"
} else {
    Write-Warn "VSIX not available — skipping extension install"
}

# --------------------------------------------------------------------------
# STEP 5: Project scaffold (optional, -InitProject flag)
# --------------------------------------------------------------------------
Write-Step "Step 5/6: Project scaffold"
if ($InitProject) {
    Write-Info "Initializing UTF in: $ProjectDir"
    $githubDir = Join-Path $ProjectDir ".github"
    New-Item -ItemType Directory -Force -Path $githubDir | Out-Null

    $projectInstructionsDst = Join-Path $githubDir "copilot-instructions.md"
    $projectName = Split-Path $ProjectDir -Leaf

    $projectInstructions = @"
---
applyTo: "**"
---

# UTF Project Instructions — $projectName

> Auto-generated by UTF install-vscode-mcp.ps1. Edit to add project-specific context.

## Project Context

- **Project:** $projectName
- **UTF tests output:** ``utf-tests/``
- **Reports:** ``utf-tests/reports/``
- **Registry:** ``utf-tests/.utf/utf.db`` (local SQLite, per-project, not committed)

## Universal Test Framework — Active

The UTF MCP server is registered globally. In every Copilot session:

1. When asked to generate tests, call ``generate_tests`` (UTF MCP tool)
2. Validate each test with ``validate_test_contract`` — minimum score 0.75
3. Build traceability with ``build_traceability_matrix``
4. Generate the contract report with ``generate_report``

## 8-Section Test Contract (Required for every test)

| # | Section | Requirement |
|---|---------|-------------|
| 1 | Test ID | TC-{TYPE}-{NNN} |
| 2 | Why Generated | Requirement-linked rationale |
| 3 | Requirement Mapping | REQ-xxx / AC-x.x / US-xxx (infer if not given) |
| 4 | How it Exercises | GIVEN / WHEN / THEN |
| 5 | Coverage Contribution | branch/line/mutation % |
| 6 | Expected Outcome | Precise assertions |
| 7 | Gaps | What this test does NOT cover |
| 8 | Meaningfulness Check | Not hallucinated, not redundant |

## Zero-Overhead Discovery Rule

If developer provides minimal context, the LLM must:
1. Read source files to discover routes, functions, components
2. Infer REQ-xxx / AC-x.x identifiers from the code
3. Generate: 1 happy path + 2 negative paths + 1 edge case per endpoint/component
4. Never ask the developer for requirement IDs — infer them

## UTF Copilot Commands (use in Copilot Chat)

| Say this... | UTF does this |
|---|---|
| "generate unit tests" | Calls generate_tests(test_type="unit") |
| "generate API tests" | Calls generate_tests(test_type="api") |
| "generate E2E tests" | Calls generate_tests(test_type="e2e") |
| "validate this test" | Calls validate_test_contract |
| "show traceability matrix" | Calls build_traceability_matrix |
| "what's not covered?" | Calls analyze_coverage |
| "generate UTF report" | Calls generate_report |
"@
    Set-Content -Path $projectInstructionsDst -Value $projectInstructions -Encoding UTF8
    Write-Ok "Project instructions → $projectInstructionsDst"

    # Create utf-tests/ scaffold
    $utfTestsDir = Join-Path $ProjectDir "utf-tests"
    foreach ($d in @(
        $utfTestsDir,
        "$utfTestsDir\backend", "$utfTestsDir\frontend", "$utfTestsDir\e2e",
        "$utfTestsDir\generated", "$utfTestsDir\reports"
    )) {
        if (-not (Test-Path $d)) {
            New-Item -ItemType Directory -Force -Path $d | Out-Null
            Write-Info "  Created: $d"
        }
    }
    Write-Ok "utf-tests/ folder scaffold created"

    # Add .utf/utf.db to .gitignore
    $gitignorePath = Join-Path $ProjectDir ".gitignore"
    if (Test-Path $gitignorePath) {
        $gi = Get-Content $gitignorePath -Raw
        if ($gi -notmatch "\.utf/utf\.db") {
            Add-Content -Path $gitignorePath -Value "`n# UTF local registry`n.utf/utf.db`n.utf/reports/"
            Write-Info "Added .utf/utf.db to .gitignore"
        }
    }
} else {
    Write-Info "Skipped (pass -InitProject to scaffold a project directory)"
    Write-Info "Example: .\scripts\install-vscode-mcp.ps1 -InitProject -ProjectDir C:\my-project"
}

# --------------------------------------------------------------------------
# STEP 6: Health check
# --------------------------------------------------------------------------
Write-Step "Step 6/6: UTF server health check"
try {
    if ($launchMode -eq "uvx") {
        # For uvx mode, check if the package is available via uvx
        $uvxCheck = & $uvxPath --from universal-test-framework utf-server --help 2>&1
        if ($LASTEXITCODE -eq 0 -or $uvxCheck -match "transport") {
            Write-Ok "Health check PASSED — uvx mode ready (universal-test-framework package accessible)"
        } else {
            Write-Warn "uvx check: package not yet on PyPI — will work after 'pip publish'. Local venv fallback active."
        }
    } else {
        $healthScript = @"
import sys, json
sys.path.insert(0, r'$utfRoot')
try:
    from mcp_server.server import health
    result = health()
    print(json.dumps(result) if isinstance(result, dict) else str(result))
except Exception as e:
    print(json.dumps({'status': 'error', 'message': str(e)}))
"@
        $result = & $pythonPath -c $healthScript 2>&1
        if ($result -match '"status"') {
            $parsed = $result | ConvertFrom-Json
            if ($parsed.status -eq "ok") {
                Write-Ok "Health check PASSED — status: ok, version: $($parsed.version), tools: $($parsed.tools)"
            } else {
                Write-Warn "Health check returned: $result"
            }
        } else {
            Write-Warn "Health check output: $result"
        }
    }
} catch {
    Write-Warn "Health check skipped: $_"
}

# ==========================================================================
# SUMMARY
# ==========================================================================
Write-Host @"

  ╔══════════════════════════════════════════════════════════════╗
  ║                    Installation Summary                      ║
  ╚══════════════════════════════════════════════════════════════╝
"@ -ForegroundColor $(if ($script:Errors -eq 0) { 'Green' } else { 'Yellow' })

Write-Host "  UTF Root     : $utfRoot" -ForegroundColor White
Write-Host "  Launch mode  : $launchMode$(if ($launchMode -eq 'uvx') {' (PyPI — no hardcoded paths)'} else {' (local venv)'})" -ForegroundColor White
Write-Host "  mcp.json     : $mcpFile" -ForegroundColor White
Write-Host "  SQLite cwd   : `${workspaceFolder}/.utf/utf.db (auto, per-project)" -ForegroundColor White
Write-Host "  Prompts dir  : $env:APPDATA\Code\User\prompts\" -ForegroundColor White
if ($InitProject) {
    Write-Host "  Project      : $ProjectDir" -ForegroundColor White
}
Write-Host ""

if ($script:Errors -eq 0) {
    Write-Host "  ✅ All steps completed successfully!" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  $($script:Errors) step(s) had errors — review output above" -ForegroundColor Yellow
}

Write-Host @"

  NEXT STEPS:
  ─────────────────────────────────────────────────────────────
  1. Reload VS Code (Ctrl+Shift+P → "Reload Window")
  2. Open Copilot Chat (Ctrl+Shift+I)
  3. Type @ and verify 'utf' appears in the participant list
  4. Try: @utf /generate-tests unit
     or ask: "generate backend tests using UTF"

  TO SCAFFOLD A NEW PROJECT:
  ─────────────────────────────────────────────────────────────
  cd C:\my-new-project
  $PSScriptRoot\install-vscode-mcp.ps1 -InitProject

  TO CHECK STATUS:
  ─────────────────────────────────────────────────────────────
  $PSScriptRoot\install-vscode-mcp.ps1 -Status

  TO UNINSTALL:
  ─────────────────────────────────────────────────────────────
  $PSScriptRoot\install-vscode-mcp.ps1 -Uninstall
"@ -ForegroundColor Gray

