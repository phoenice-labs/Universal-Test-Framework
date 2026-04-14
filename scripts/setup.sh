#!/usr/bin/env bash
# Universal Test Framework — Unix/macOS Setup Script
# Usage: ./scripts/setup.sh [--skip-venv] [--install-mcp]

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${VENV_PATH:-.venv}"
SKIP_VENV=false
INSTALL_MCP=false

for arg in "$@"; do
    case "$arg" in
        --skip-venv) SKIP_VENV=true ;;
        --install-mcp) INSTALL_MCP=true ;;
    esac
done

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Universal Test Framework — Setup (Unix/macOS)"
echo "═══════════════════════════════════════════════════════"
echo ""

cd "$BASE_DIR"

# Step 1: Python version check
echo "Step 1: Checking Python version..."
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.11+ from https://python.org"
    exit 1
fi
PY_VERSION=$(python3 --version)
echo "  Found: $PY_VERSION"
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "ERROR: Python 3.11+ required. Found: $PY_VERSION"
    exit 1
fi
echo "  ✓ Python version OK"

# Step 2: Virtual environment
if [ "$SKIP_VENV" = false ]; then
    echo ""
    echo "Step 2: Creating virtual environment at $VENV_PATH..."
    if [ -d "$VENV_PATH" ]; then
        echo "  Virtual environment already exists — skipping."
    else
        python3 -m venv "$VENV_PATH"
        echo "  Created: $VENV_PATH"
    fi
    source "$VENV_PATH/bin/activate"
    echo "  ✓ Activated: $VENV_PATH"
else
    echo ""
    echo "Step 2: Skipping venv (--skip-venv)"
fi

# Step 3: Install dependencies
echo ""
echo "Step 3: Installing dependencies..."
pip install -e ".[dev]" --quiet
echo "  ✓ Dependencies installed"

# Step 4: Validate YAML rules
echo ""
echo "Step 4: Validating YAML rules..."
YAML_ERRORS=0
while IFS= read -r -d '' f; do
    if ! python3 -c "import yaml; yaml.safe_load(open('$f', encoding='utf-8'))" 2>/dev/null; then
        echo "  FAIL: $(basename "$f")"
        YAML_ERRORS=$((YAML_ERRORS + 1))
    fi
done < <(find "$BASE_DIR/rules" -name "*.yaml" -print0)
if [ "$YAML_ERRORS" -gt 0 ]; then
    echo "ERROR: $YAML_ERRORS YAML file(s) invalid."
    exit 1
fi
echo "  ✓ All YAML rules valid"

# Step 5: Validate Python syntax
echo ""
echo "Step 5: Validating Python syntax..."
PY_ERRORS=0
while IFS= read -r -d '' f; do
    if ! python3 -m py_compile "$f" 2>/dev/null; then
        echo "  FAIL: $(basename "$f")"
        PY_ERRORS=$((PY_ERRORS + 1))
    fi
done < <(find "$BASE_DIR/mcp-server" -name "*.py" -print0)
if [ "$PY_ERRORS" -gt 0 ]; then
    echo "ERROR: $PY_ERRORS Python file(s) have syntax errors."
    exit 1
fi
echo "  ✓ All Python files valid"

# Step 6: MCP registration
if [ "$INSTALL_MCP" = true ]; then
    echo ""
    echo "Step 6: Registering MCP server in VS Code settings..."
    UTF_SERVER_PATH="$(which utf-server 2>/dev/null || echo "python3 -m mcp_server.server")"
    VSCODE_SETTINGS="$HOME/.config/Code/User/settings.json"
    if [ ! -f "$VSCODE_SETTINGS" ]; then
        VSCODE_SETTINGS="$HOME/Library/Application Support/Code/User/settings.json"
    fi
    echo "  VS Code settings: $VSCODE_SETTINGS"
    echo "  Add this to your mcp.servers config:"
    echo '  "utf": { "command": "utf-server", "args": [], "type": "stdio" }'
else
    echo ""
    echo "Step 6: To register MCP server in VS Code, run:"
    echo "  ./scripts/setup.sh --install-mcp"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ Setup complete!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Start local MCP server:  python3 -m mcp_server.server"
echo "  2. Docker (team):           cd docker && docker compose up -d"
echo ""
