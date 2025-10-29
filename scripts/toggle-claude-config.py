#!/usr/bin/env python3
"""Toggle Claude Desktop config between dev (uv) and docker modes."""

import json
import sys
from pathlib import Path

# Paths
CONFIG_PATH = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
PROJECT_DIR = Path(__file__).parent.parent.resolve()

# Config templates
DEV_CONFIG = {
    "command": "uv",
    "args": [
        "--directory",
        str(PROJECT_DIR),
        "run",
        "python",
        "-m",
        "src.server"
    ],
    "env": {
        "DOTBOX_SANDBOX_REGISTRY": "local"
    }
}

def get_docker_config():
    """Get Docker config with dynamic docker GID."""
    import grp
    try:
        docker_gid = grp.getgrnam('docker').gr_gid
    except KeyError:
        # Fallback to root if docker group not found
        docker_gid = 0

    return {
        "command": "docker",
        "args": [
            "run",
            "--rm",
            "-i",
            "--user",
            f"1000:{docker_gid}",
            "-v",
            "/var/run/docker.sock:/var/run/docker.sock",
            "-e",
            "DOTBOX_SANDBOX_REGISTRY=local",
            "dotbox-mcp:dev"
        ]
    }

def load_config():
    """Load existing config or create empty one."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)

    # Create directory if needed
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    return {"mcpServers": {}}

def save_config(config):
    """Save config with pretty formatting."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def detect_mode(config):
    """Detect current mode."""
    dotbox = config.get("mcpServers", {}).get("dotbox-mcp", {})
    if not dotbox:
        return "none"

    command = dotbox.get("command", "")
    if command == "docker":
        return "docker"
    elif command == "uv":
        return "dev"
    return "unknown"

def main():
    # Parse args
    if len(sys.argv) > 2:
        print("Usage: toggle-claude-config.py [dev|docker]")
        print("  dev    - Use uv-based local development")
        print("  docker - Use Docker-based testing")
        print("  (no arg) - Toggle between modes")
        sys.exit(1)

    # Load config
    config = load_config()
    current_mode = detect_mode(config)

    # Determine target mode
    if len(sys.argv) == 2:
        target_mode = sys.argv[1]
        if target_mode not in ["dev", "docker"]:
            print(f"Error: Invalid mode '{target_mode}'")
            sys.exit(1)
    else:
        # Auto-toggle
        target_mode = "docker" if current_mode == "dev" else "dev"

    # Apply new config
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    if target_mode == "dev":
        config["mcpServers"]["dotbox-mcp"] = DEV_CONFIG
        print("✓ Switched to DEV mode (uv-based)")
        print(f"  Path: {PROJECT_DIR}")
        print("  Uses: Local sandbox images")
    else:
        config["mcpServers"]["dotbox-mcp"] = get_docker_config()
        print("✓ Switched to DOCKER mode")
        print("  Image: dotbox-mcp:dev")
        print("  Uses: Local sandbox images")
        print()
        print("Build images with: ./scripts/build-docker-dev.sh")

    # Save
    save_config(config)

    # Show other servers if any
    other_servers = [k for k in config["mcpServers"].keys() if k != "dotbox-mcp"]
    if other_servers:
        print()
        print(f"Preserved {len(other_servers)} other MCP server(s): {', '.join(other_servers)}")

    print()
    print("⚠  Restart Claude Desktop to apply changes")

if __name__ == "__main__":
    main()
