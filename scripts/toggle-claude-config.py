#!/usr/bin/env python3
"""Toggle Claude Desktop config between dev, docker, and production modes."""

import json
import sys
from pathlib import Path

# Paths
CONFIG_PATH = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
PROJECT_DIR = Path(__file__).parent.parent.resolve()

def get_dev_config():
    """Get dev config with full uv path."""
    import shutil
    uv_path = shutil.which("uv")
    if not uv_path:
        raise RuntimeError("uv not found in PATH. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh")

    return {
        "command": uv_path,
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
            "--add-host",
            "host.docker.internal:host-gateway",
            "--user",
            f"1000:{docker_gid}",
            "-v",
            "/var/run/docker.sock:/var/run/docker.sock",
            "-e",
            "DOTBOX_SANDBOX_REGISTRY=local",
            "dotbox-mcp:dev"
        ]
    }

def get_production_config():
    """Get production config using GHCR published images."""
    import grp
    try:
        docker_gid = grp.getgrnam('docker').gr_gid
    except KeyError:
        docker_gid = 0

    return {
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
            "/var/run/docker.sock:/var/run/docker.sock",
            "ghcr.io/domibies/dotbox-mcp:latest"
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
        # Check if it's local dev or production GHCR
        args = dotbox.get("args", [])
        image = args[-1] if args else ""
        if "ghcr.io" in image:
            return "production"
        else:
            return "docker"
    elif "uv" in command:
        return "dev"
    return "unknown"

def main():
    # Parse args
    if len(sys.argv) > 2:
        print("Usage: toggle-claude-config.py [dev|docker|production]")
        print("  dev        - Use uv-based local development")
        print("  docker     - Use Docker-based testing (local images)")
        print("  production - Use published GHCR images")
        print("  (no arg)   - Toggle between modes")
        sys.exit(1)

    # Load config
    config = load_config()
    current_mode = detect_mode(config)

    # Determine target mode
    if len(sys.argv) == 2:
        target_mode = sys.argv[1]
        if target_mode not in ["dev", "docker", "production"]:
            print(f"Error: Invalid mode '{target_mode}'")
            sys.exit(1)
    else:
        # Auto-toggle between dev and docker (not production)
        target_mode = "docker" if current_mode == "dev" else "dev"

    # Apply new config
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    if target_mode == "dev":
        config["mcpServers"]["dotbox-mcp"] = get_dev_config()
        print("✓ Switched to DEV mode (uv-based)")
        print(f"  Server: Local source via uv")
        print(f"  Path: {PROJECT_DIR}")
        print("  Sandbox: Local Docker images (dotnet-sandbox:8/9/10-rc2)")
    elif target_mode == "docker":
        config["mcpServers"]["dotbox-mcp"] = get_docker_config()
        print("✓ Switched to DOCKER mode")
        print("  Server: Local Docker image (dotbox-mcp:dev)")
        print("  Sandbox: Local Docker images (dotnet-sandbox:8/9/10-rc2)")
        print()
        print("Build images with: ./scripts/build-docker-dev.sh")
    else:  # production
        config["mcpServers"]["dotbox-mcp"] = get_production_config()
        print("✓ Switched to PRODUCTION mode")
        print("  Server: ghcr.io/domibies/dotbox-mcp:latest")
        print("  Sandbox: ghcr.io/domibies/dotbox-mcp/dotnet-sandbox:8/9/10-rc2")

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
