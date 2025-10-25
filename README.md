# dotbox-mcp

**Work in Progress** 🚧

A Model Context Protocol (MCP) server that manages Docker containers for executing .NET workloads. Enables LLMs to run C# code, test different .NET versions (8, 9, 10 RC2), and manage containerized development environments.

Built with FastMCP (Python) and Docker SDK.

## Status

Currently implementing core functionality using TDD principles. The project is not yet ready for production use.

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
