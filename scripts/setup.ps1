# Universal Test Framework — Windows Setup Script
# Run from the Universal-Test-Framework directory:
#   .\scripts\setup.ps1

param(
    [switch]$SkipVenv,
    [switch]$InstallMcp,
    [string]$VenvPath = ".venv"
)

$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $PSScriptRoot

Write-Host "`n═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Universal Test Framework — Setup (Windows)" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════`n" -ForegroundColor Cyan

Set-Location $base

# ── Step 1: Python version check ─────────────────────────────────────────────
Write-Host "Step 1: Checking Python version..." -ForegroundColor Yellow
$pyVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python not found. Install Python 3.11+ from https://python.org"
    exit 1
}
Write-Host "  Found: $pyVersion" -ForegroundColor Green
$versionMatch = [regex]::Match($pyVersion, '(\d+)\.(\d+)')
$major = [int]$versionMatch.Groups[1].Value
$minor = [int]$versionMatch.Groups[2].Value
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
    Write-Error "Python 3.11+ required. Found: $pyVersion"
    exit 1
}

# ── Step 2: Create virtual environment ────────────────────────────────────────
if (-not $SkipVenv) {
    Write-Host "`nStep 2: Creating virtual environment at $VenvPath..." -ForegroundColor Yellow
    if (Test-Path $VenvPath) {
        Write-Host "  Virtual environment already exists — skipping creation." -ForegroundColor Gray
    } else {
        python -m venv $VenvPath
        Write-Host "  Created." -ForegroundColor Green
    }
    # Activate
    $activateScript = "$VenvPath\Scripts\Activate.ps1"
    if (Test-Path $activateScript) {
        & $activateScript
        Write-Host "  Activated: $VenvPath" -ForegroundColor Green
    }
} else {
    Write-Host "`nStep 2: Skipping venv creation (--SkipVenv)" -ForegroundColor Gray
}

# ── Step 3: Install dependencies ─────────────────────────────────────────────
Write-Host "`nStep 3: Installing dependencies from pyproject.toml..." -ForegroundColor Yellow
pip install -e ".[dev]" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed."
    exit 1
}
Write-Host "  Dependencies installed." -ForegroundColor Green

# ── Step 4: Validate YAML rules ───────────────────────────────────────────────
Write-Host "`nStep 4: Validating YAML rules..." -ForegroundColor Yellow
$yamlFiles = Get-ChildItem -Recurse -Filter "*.yaml" "$base\rules" | Select-Object -ExpandProperty FullName
$yamlErrors = 0
foreach ($f in $yamlFiles) {
    $result = python -c "import yaml; yaml.safe_load(open('$f', encoding='utf-8'))" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL: $(Split-Path $f -Leaf) — $result" -ForegroundColor Red
        $yamlErrors++
    }
}
if ($yamlErrors -gt 0) {
    Write-Error "$yamlErrors YAML file(s) invalid."
    exit 1
}
Write-Host "  All $($yamlFiles.Count) YAML rule files valid." -ForegroundColor Green

# ── Step 5: Validate Python syntax ────────────────────────────────────────────
Write-Host "`nStep 5: Validating Python syntax..." -ForegroundColor Yellow
$pyFiles = Get-ChildItem -Recurse -Filter "*.py" "$base\mcp-server" | Select-Object -ExpandProperty FullName
$pyErrors = 0
foreach ($f in $pyFiles) {
    $result = python -m py_compile $f 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL: $(Split-Path $f -Leaf) — $result" -ForegroundColor Red
        $pyErrors++
    }
}
if ($pyErrors -gt 0) {
    Write-Error "$pyErrors Python file(s) have syntax errors."
    exit 1
}
Write-Host "  All $($pyFiles.Count) Python files valid." -ForegroundColor Green

# ── Step 6: Install MCP server in VS Code (optional) ─────────────────────────
if ($InstallMcp) {
    Write-Host "`nStep 6: Registering MCP server in VS Code..." -ForegroundColor Yellow
    & "$PSScriptRoot\install-vscode-mcp.ps1"
} else {
    Write-Host "`nStep 6: To register MCP server in VS Code, run:" -ForegroundColor Yellow
    Write-Host "  .\scripts\install-vscode-mcp.ps1" -ForegroundColor White
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host "`n═══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ Setup complete!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Start local MCP server:    python -m mcp_server.server" -ForegroundColor White
Write-Host "  2. Register in VS Code:       .\scripts\install-vscode-mcp.ps1" -ForegroundColor White
Write-Host "  3. Docker (team/remote):      cd docker && docker-compose up -d" -ForegroundColor White
Write-Host ""
