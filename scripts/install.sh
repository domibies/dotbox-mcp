#!/bin/bash
set -e -u -o pipefail

# dotbox-mcp installer for macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/domibies/dotbox-mcp/main/scripts/install.sh | bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "dotbox-mcp installer for macOS"
echo ""

# 1. Check macOS
if [ "$(uname -s)" != "Darwin" ]; then
    echo -e "${RED}❌ This installer is for macOS only${NC}"
    echo ""
    echo "For Linux (unofficial): See README.md for manual setup"
    exit 1
fi

# 2. Detect Python3 (robust multi-location check)
PYTHON=""
if command -v python3 &> /dev/null; then
    PYTHON="python3"
elif [ -x /usr/bin/python3 ]; then
    PYTHON="/usr/bin/python3"
elif command -v python &> /dev/null; then
    PYTHON="python"
else
    echo -e "${RED}❌ Python 3 not found${NC}"
    echo "Python 3 should be pre-installed on macOS 12.3+"
    echo "If missing, install Xcode Command Line Tools:"
    echo "  xcode-select --install"
    exit 1
fi

# Verify Python 3.6+
if ! $PYTHON -c "import sys; sys.exit(0 if sys.version_info >= (3,6) else 1)" 2>/dev/null; then
    echo -e "${RED}❌ Python 3.6+ required${NC}"
    exit 1
fi

# 3. Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not installed${NC}"
    echo ""
    echo "Install Docker Desktop:"
    echo "  https://docs.docker.com/desktop/install/mac-install/"
    echo ""
    echo "Or via Homebrew:"
    echo "  brew install --cask docker"
    echo ""
    echo "After installing Docker Desktop, start it and re-run this installer."
    exit 1
fi

if ! docker ps &> /dev/null; then
    echo -e "${RED}❌ Docker not running${NC}"
    echo "Start Docker Desktop from Applications or:"
    echo "  open -a Docker"
    echo ""
    echo "After Docker starts, re-run this installer."
    exit 1
fi

echo -e "${GREEN}✓${NC} Docker running"

# 4. Claude Desktop config path (macOS)
CONFIG_PATH="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

# 5. Resolve Docker socket path (handles symlinks on macOS)
if [ -L /var/run/docker.sock ]; then
    # Symlink - resolve to real path
    DOCKER_SOCK_PATH=$(readlink /var/run/docker.sock)
    # Handle relative symlinks
    if [[ "$DOCKER_SOCK_PATH" != /* ]]; then
        DOCKER_SOCK_PATH="/var/run/$DOCKER_SOCK_PATH"
    fi
else
    DOCKER_SOCK_PATH="/var/run/docker.sock"
fi

# Docker GID: On macOS use root (0) since there's no docker group
# Inside the container, the mounted socket will be root:root
DOCKER_GID=0

# 6. Check if already installed (idempotency)
if [ -r "$CONFIG_PATH" ]; then
    export CHECK_CONFIG_PATH="$CONFIG_PATH"
    if "$PYTHON" - <<'PYEOF'
import json, sys, os, io
p = os.environ['CHECK_CONFIG_PATH']
try:
    with io.open(p, 'r', encoding='utf-8-sig') as f:  # strip BOM if present
        config = json.load(f)
    mcp = config.get("mcpServers") or {}
    if not isinstance(mcp, dict):
        print("mcpServers not a dict; treating as not installed", file=sys.stderr)
        sys.exit(1)
    sys.exit(0 if "dotbox-mcp" in mcp else 1)
except FileNotFoundError:
    print("config missing at check time", file=sys.stderr); sys.exit(1)
except PermissionError:
    print("config not readable (permissions)", file=sys.stderr); sys.exit(1)
except json.JSONDecodeError as e:
    print(f"invalid JSON: {e}", file=sys.stderr); sys.exit(1)
except Exception as e:
    print(f"unexpected error: {e}", file=sys.stderr); sys.exit(1)
PYEOF
    then
        if [ "${1:-}" != "--force" ]; then
            echo -e "${YELLOW}✓${NC} dotbox-mcp already installed"
            echo ""
            read -p "Do you want to reinstall and update the configuration? (y/N): " -n 1 -r </dev/tty
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "Installation cancelled. To reinstall later, run with --force flag."
                exit 0
            fi
        fi
        echo "Reinstalling..."
    fi
fi

# 7. Backup existing config
mkdir -p "$(dirname "$CONFIG_PATH")"
if [ -f "$CONFIG_PATH" ]; then
    BACKUP_PATH="$CONFIG_PATH.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$CONFIG_PATH" "$BACKUP_PATH"
    echo -e "${GREEN}✓${NC} Backed up config to: $(basename "$BACKUP_PATH")"
fi

# 8. Update config using Python (preserves other MCPs)
echo "Updating Claude Desktop config..."
export CONFIG_PATH
export DOCKER_GID
export DOCKER_SOCK_PATH
$PYTHON - <<'EOF'
import json
import os
import sys

config_path = os.environ['CONFIG_PATH']
docker_gid = os.environ['DOCKER_GID']
docker_sock_path = os.environ['DOCKER_SOCK_PATH']

# Load or create config
if os.path.exists(config_path):
    try:
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in {config_path}", file=sys.stderr)
        sys.exit(1)
else:
    config = {}

# Ensure mcpServers exists
if "mcpServers" not in config:
    config["mcpServers"] = {}

# Add/update dotbox-mcp entry only
config["mcpServers"]["dotbox-mcp"] = {
    "command": "docker",
    "args": [
        "run",
        "--rm",
        "-i",
        "--add-host",
        "host.docker.internal:host-gateway",
        "--user",
        f"1000:{docker_gid}",
        "-v",
        f"{docker_sock_path}:/var/run/docker.sock",
        "ghcr.io/domibies/dotbox-mcp:latest"
    ]
}

# Write atomically
import tempfile
fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(config_path), text=True)
try:
    with os.fdopen(fd, 'w') as f:
        json.dump(config, f, indent=2)
    os.rename(temp_path, config_path)
except Exception as e:
    try:
        os.unlink(temp_path)
    except:
        pass
    print(f"Error writing config: {e}", file=sys.stderr)
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to update config${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Config updated"

# 9. Show security notice
echo ""
echo -e "${YELLOW}⚠️  Security Notice:${NC}"
echo "  Docker socket access grants root-equivalent privileges."
echo "  dotbox-mcp creates isolated .NET containers for code execution."
echo "  Review code: https://github.com/domibies/dotbox-mcp"
echo ""

# 10. Success message
echo -e "${GREEN}✓ dotbox-mcp installed successfully!${NC}"
echo ""
echo "Next steps:"
echo "  1. Restart Claude Desktop"
echo "  2. Try: 'Execute this C# code: Console.WriteLine(DateTime.Now);'"
echo ""
echo "Note: First run will pull Docker images (~1GB total)"
echo ""
