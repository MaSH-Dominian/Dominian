#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Dominian MCP Server — Installation Script
# ──────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Dominian MCP Server — Installer${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""

# ── Step 1: Check Python ────────────────────────────────────
echo -e "${YELLOW}[1/5] Checking Python...${NC}"
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo -e "${RED}Error: Python 3.10+ not found. Install Python first.${NC}"
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Using Python $PY_VERSION at: $(which $PYTHON)"

# ── Step 2: Install MCP SDK ────────────────────────────────
echo ""
echo -e "${YELLOW}[2/5] Installing MCP SDK...${NC}"
$PYTHON -m pip install --quiet "mcp>=1.0.0"

# ── Step 3: Install optional dependencies ──────────────────
echo ""
echo -e "${YELLOW}[3/5] Installing optional dependencies...${NC}"

# Community detection (Louvain)
$PYTHON -m pip install --quiet networkx python-louvain 2>/dev/null && \
    echo "  ✓ networkx + python-louvain (community detection)" || \
    echo "  ⚠ Skipping community detection deps (pip install networkx python-louvain)"

# Tree-sitter (optional, for deep parsing)
$PYTHON -m pip install --quiet tree-sitter 2>/dev/null && \
    echo "  ✓ tree-sitter (deep parsing)" || \
    echo "  ⚠ Skipping tree-sitter (optional — Dominian falls back to regex parsing)"

# ── Step 4: Verify Dominian source files ───────────────────
echo ""
echo -e "${YELLOW}[4/5] Verifying Dominian source files...${NC}"

REQUIRED_FILES=("database.py" "formatter.py")
OPTIONAL_FILES=("adaptive_scanner.py" "engine.py" "tree_sitter_parser.py")

ALL_OK=true
for f in "${REQUIRED_FILES[@]}"; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        echo "  ✓ $f"
    else
        echo -e "  ${RED}✗ $f NOT FOUND (required)${NC}"
        ALL_OK=false
    fi
done

for f in "${OPTIONAL_FILES[@]}"; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        echo "  ✓ $f"
    else
        echo -e "  ${YELLOW}⚠ $f not found (optional — some features disabled)${NC}"
    fi
done

if [ "$ALL_OK" = false ]; then
    echo ""
    echo -e "${RED}Error: Required files missing. Copy database.py and formatter.py to:${NC}"
    echo -e "${RED}  $SCRIPT_DIR/${NC}"
    exit 1
fi

# ── Step 5: Test import ────────────────────────────────────
echo ""
echo -e "${YELLOW}[5/5] Testing imports...${NC}"

$PYTHON -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from database import GraphDatabase
from formatter import format_minimal
from mcp.server.fastmcp import FastMCP
print('  ✓ All imports successful')
" 2>/dev/null && echo -e "${GREEN}  ✓ MCP server ready${NC}" || \
    echo -e "${RED}  ✗ Import test failed — check dependencies${NC}"

# ── Done ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "To start the MCP server:"
echo "  $PYTHON $SCRIPT_DIR/server.py"
echo ""
echo "For MCP client config (Claude Desktop), add to claude_desktop_config.json:"
echo ""
cat << 'JSONEOF'
{
  "mcpServers": {
    "dominian": {
      "command": "python",
      "args": ["PATH_TO/dominian-mcp/server.py"],
      "env": {
        "DOMINIAN_DB": ".dominian/agentgraph.db",
        "DOMINIAN_ROOT": "."
      }
    }
  }
}
JSONEOF
echo ""
echo "Replace PATH_TO with the actual path to dominian-mcp/"
