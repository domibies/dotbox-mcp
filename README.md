# dotbox-mcp

**Work in Progress** 🚧

A Model Context Protocol (MCP) server that enables LLMs to execute .NET workloads in isolated Docker containers. Think of it as a secure sandbox where Claude can write C# code, build projects, host web APIs, and test across multiple .NET versions - all without affecting your local environment.

Built with FastMCP (Python) and Docker SDK.

## What It Does (Sneak Peek)

This MCP server is designed around **agent-centric workflows** - providing complete end-to-end tools rather than low-level Docker commands:

- **Quick C# Snippets**: Execute C# code instantly without project setup
- **Full Project Management**: Create, build, and run complete .NET projects (console apps, web APIs, class libraries)
- **Multi-Version Testing**: Compare code behavior across .NET 8, 9, and 10 RC2 in parallel
- **Web API Hosting**: Start web servers in containers with external port mapping for real HTTP testing
- **Resource Management**: Automatic container cleanup, timeout handling, and resource limits

Under the hood, it manages Alpine-based Docker images with .NET SDKs, handles build/execution orchestration, and formats output to stay within MCP's constraints.

## Status

Currently implementing core functionality using strict TDD principles (unit tests → implementation → E2E validation). The server handles basic workflows but is actively evolving based on real-world usage feedback.

**Latest:** Port mapping and web API hosting tools are functional. Working on enhanced examples and documentation based on Claude Desktop integration testing.

Not yet ready for production use - API signatures may change.

## Requirements

- Python 3.10+
- Docker
- uv (dependency manager)

## Running Locally (Development)

To run this WIP version from the development folder:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/dotbox-mcp.git
   cd dotbox-mcp
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Build Docker images:**
   ```bash
   cd docker
   ./build-images.sh
   cd ..
   ```

4. **Find the absolute path to uv:**
   ```bash
   which uv
   ```

   **Note:** Claude Desktop doesn't inherit your shell's PATH on macOS/Linux. GUI applications get a minimal system PATH that doesn't include tools installed via Homebrew, cargo, asdf, etc. You must use the absolute path.

5. **Configure Claude Desktop:**

   Add to your `claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "dotbox-mcp": {
         "command": "/absolute/path/to/uv",
         "args": [
           "--directory",
           "/absolute/path/to/dotbox-mcp",
           "run",
           "python",
           "-m",
           "src.server"
         ]
       }
     }
   }
   ```

   Replace `/absolute/path/to/uv` with the output from `which uv` (e.g., `/Users/you/.cargo/bin/uv` or `/Users/you/.asdf/shims/uv`).

6. **Restart Claude Desktop** to load the MCP server.

## License

MIT
