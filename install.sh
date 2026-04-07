#!/bin/bash
set -e

echo ""
echo "============================================"
echo "  Memory MCP Server - One-Line Installer"
echo "============================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check for uv
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}uv not found. Installing...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo -e "${GREEN}uv installed.${NC}"
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing dependencies..."
cd "$SCRIPT_DIR"
uv sync

echo ""
echo "Running auto-setup..."
uv run memory-mcp-setup

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "Restart Claude Code and you're ready to go."
echo ""
echo "Quick start:"
echo "  memory_init_project('my-project', 'My Project')"
echo "  memory_session_start('my-project')"
echo ""
