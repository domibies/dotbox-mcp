# dotbox-mcp

A Model Context Protocol (MCP) server that enables LLMs to execute .NET workloads in isolated Docker containers. Write C# code, build projects, host web APIs, and test across multiple .NET versions - all from within Claude Desktop.

Built with FastMCP (Python) and Docker SDK.

## What is dotbox-mcp?

**dotbox-mcp is a specialized tool for rapid .NET experimentation and prototyping** - not a replacement for full-fledged coding agents like Claude Code or Cursor.

**Use dotbox-mcp when you want to:**
- Quickly test a .NET feature or API
- Prototype a small Minimal API or console app
- Compare behavior across .NET versions (8, 9, 10)
- Execute snippets without setting up a local environment
- Experiment with NuGet packages in isolation

**Use Claude Code when you need:**
- Full codebase navigation and editing
- Multi-file projects with git integration
- Comprehensive testing and debugging
- Production-ready application development

**Security through isolation:** All .NET code runs in ephemeral Docker containers with resource limits, read-only filesystems (except `/workspace`), and automatic cleanup. Containers are destroyed after use, ensuring no persistent state or security risks.

![API Key Management Example](images/Built%20a%20Minimal%20API%20for%20API%20Key%20Mgmt.png)
*Example: Claude building a complete API Key Management service with CRUD endpoints, in-memory storage, and key validation - from prompt to running API in seconds.*

## Features

This MCP server is designed around **agent-centric workflows** - providing complete end-to-end tools rather than low-level Docker commands:

- **Quick C# Snippets**: Execute C# code instantly without project setup
- **Full Project Management**: Create, build, and run complete .NET projects (console apps, web APIs, class libraries)
- **Multi-Version Testing**: Compare code behavior across .NET 8, 9, and 10 RC2 in parallel
- **Web API Hosting**: Start web servers in containers with external port mapping for real HTTP testing
- **Resource Management**: Automatic container cleanup, timeout handling, and resource limits

Under the hood, it manages Alpine-based Docker images with .NET SDKs, handles build/execution orchestration, and formats output to stay within MCP's constraints.

## Quick Start

**Requirements:**
- macOS with Docker Desktop installed and running
- Claude Desktop

### Automatic Installation (Recommended)

Install with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/domibies/dotbox-mcp/main/scripts/install.sh | bash
```

**What the installer does:**
- Verifies Docker is installed and running
- Updates Claude Desktop config (preserves other MCP servers)
- Configures to use published Docker images from GHCR

### Manual Installation

If you prefer to install manually:

1. **Detect your docker GID:**
   ```bash
   stat -f %g /var/run/docker.sock
   ```

2. **Edit Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "dotbox-mcp": {
         "command": "docker",
         "args": [
           "run",
           "--rm",
           "-i",
           "--add-host",
           "host.docker.internal:host-gateway",
           "--user",
           "1000:YOUR_DOCKER_GID",
           "-v",
           "/var/run/docker.sock:/var/run/docker.sock",
           "ghcr.io/domibies/dotbox-mcp:latest"
         ]
       }
     }
   }
   ```

   Replace `YOUR_DOCKER_GID` with the number from step 1.

   **Note:** The `--add-host` flag enables the MCP server (running in a container) to access web APIs hosted in sandbox containers via the host machine's port mappings.

3. **Restart Claude Desktop**

### After Installation

1. Restart Claude Desktop
2. Try asking Claude: *"Execute this C# code: Console.WriteLine(DateTime.Now);"*

**Note:** First run will pull Docker images (~1GB total). This happens automatically when you first use the server.

### Troubleshooting

- **Docker must be running** - Start Docker Desktop before using Claude Desktop
- If you see connection errors, ensure Docker Desktop is running
- Check `~/Library/Application Support/Claude/claude_desktop_config.json` for configuration

## Example Prompts

**Note:** Request output display explicitly when you want to see formatted results.

```
Generate 10 fake Person records in C# using the Bogus library and run it.
Display the JSON output in an artifact so I can see it properly formatted.
```

```
Create a simple .NET 8 URL shortener API with in-memory storage. Include:
  - POST /api/shorten (takes long URL, returns short code)
  - GET /{shortCode} (redirects to original URL)
  - GET /api/stats/{shortCode} (shows click count)
Start it and give me the URLs to test.
```

```
Write and execute C# code using LINQ to group products by category and calculate average prices.
Show me the results in an artifact.
```

```
Generate 10 random pronounceable passwords of length 12 in C#.
Execute it and show me the output. Explain how you did it and show the code in an artifact.
```

---

## Development & Contributing

**Status:** 🚧 Still a work in progress. The server handles core workflows but tool signatures may change.

For contributors who want to modify the code or test unreleased features:

### Requirements

- Python 3.10+
- Docker Desktop
- uv (dependency manager)

### Setup

1. **Clone and install dependencies:**
   ```bash
   git clone https://github.com/domibies/dotbox-mcp.git
   cd dotbox-mcp
   uv sync
   ```

2. **Build Docker images:**
   ```bash
   cd docker
   ./build-images.sh
   ```

### Running in Claude Desktop (Development Mode)

Use the toggle script to switch between development modes:

**Option 1: Development with uv (recommended for code changes)**
```bash
# Configure Claude Desktop to run from source with uv
python3 scripts/toggle-claude-config.py dev

# Restart Claude Desktop
```

This mode:
- Runs server from source via uv
- Hot-reloads on code changes
- Uses local Docker images
- Best for TDD workflow

**Option 2: Development with Docker (test containerized setup)**
```bash
# Build all images (sandbox + server)
./scripts/build-docker-dev.sh

# Configure Claude Desktop to run in Docker
python3 scripts/toggle-claude-config.py docker

# Restart Claude Desktop
```

This mode:
- Runs server in container (closer to production)
- Tests Docker-in-Docker setup
- Uses local images tagged `:dev`
- Best for testing deployment issues

**Switch back to production:**
```bash
python3 scripts/toggle-claude-config.py production
```

All toggle operations preserve other MCP servers in your config.

### Testing

```bash
# Unit tests (fast, mocked Docker)
uv run pytest -v -m "not e2e"

# E2E tests (requires Docker running, pulls images as needed)
uv run pytest -v -m e2e

# With coverage
uv run pytest --cov=src --cov-report=term-missing -m "not e2e"
```

### Git Workflow

**Always work on feature branches:**
```bash
git checkout -b feature/your-feature
# Make changes, commit, push
git push -u origin feature/your-feature
# Create PR via GitHub
```

Never push directly to main - all changes go through PRs with CI validation.

## License

MIT
