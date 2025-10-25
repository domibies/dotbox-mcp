# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**dotbox-mcp** is a Model Context Protocol (MCP) server that manages Docker containers running .NET workloads. It enables LLMs to execute C# code, test different .NET versions (8, 9, 10 RC2), host HTTP endpoints, and manage container lifecycles.

- **Language**: Python (using FastMCP framework)
- **Transport**: stdio (for local Claude Desktop integration)
- **Container Management**: Docker SDK for Python

## Core Architecture

The server is designed around **agent-centric workflows** rather than low-level Docker commands. Tools provide complete end-to-end functionality for common tasks.

### Key Design Principles

1. **Workflow-Complete Tools**: Each tool handles a complete workflow (e.g., `execute_csharp_snippet` handles container creation, execution, and cleanup)
2. **Context Optimization**: Default to concise output (first 50 lines) with optional full detail via `detail_level` parameter
3. **Actionable Errors**: Enhanced error messages include specific suggestions (e.g., missing packages, port conflicts)
4. **Human-Readable Naming**: Containers use descriptive names like "dotnet8-webapi-abc123" not raw IDs

### Development Principles

**CRITICAL: These principles MUST be followed strictly**

1. **Test-Driven Development (TDD)**:
   - Write tests FIRST, then implementation
   - All tests must pass before committing
   - **NEVER commit code with failing tests** - this is a hard rule
   - Red → Green → Refactor cycle

2. **Code Quality**:
   - All code must pass ruff linting (no warnings)
   - All code must pass mypy strict type checking
   - Maintain high test coverage (>90% for new code)
   - Follow DRY principles - no code duplication

3. **Commit Standards**:
   - Use conventional commit format (feat:, fix:, docs:, etc.)
   - Only commit when all tests pass
   - One logical change per commit
   - Include test changes with implementation changes

4. **Testing Standards**:
   - Unit tests for all components
   - Integration tests for end-to-end workflows
   - Mock external dependencies (Docker, HTTP calls)
   - Test both success and failure paths

### Core Workflows

1. **Quick Snippet Testing**: Execute C# code without project setup
2. **Project Development**: Create, build, run complete .NET projects
3. **Version Comparison**: Run code across multiple .NET versions in parallel
4. **Web Endpoint Hosting**: Host APIs and expose accessible URLs
5. **Package Testing**: Test NuGet packages with sample code

## Project Structure

```
dotbox_mcp/
├── src/
│   ├── server.py              # Main MCP server with FastMCP
│   ├── docker_manager.py      # Docker container management
│   ├── project_manager.py     # .NET project file management
│   ├── executor.py            # Build & execution logic
│   ├── formatter.py           # Output formatting (25k char limit)
│   ├── error_enhancer.py      # Error message enhancement
│   └── models.py              # Pydantic input/output models
├── docker/
│   ├── dotnet-8.dockerfile
│   ├── dotnet-9.dockerfile
│   ├── dotnet-10-rc2.dockerfile
│   └── build-images.sh
├── tests/
│   ├── test_executor.py
│   ├── test_project_manager.py
│   └── test_integration.py
└── examples/                   # Usage examples
```

## Tool Implementation Pattern

All MCP tools follow this structure:

```python
# Input validation with Pydantic
class ExecuteSnippetInput(BaseModel):
    code: str = Field(..., description="C# code to execute")
    dotnet_version: DotNetVersion = Field(default="8")
    detail_level: DetailLevel = Field(default="concise")

# Tool implementation
@mcp.tool()
async def dotnet_execute_snippet(input: ExecuteSnippetInput) -> str:
    """Execute a C# code snippet quickly without project setup."""
    # Returns JSON string with standardized format
```

### Standardized Response Format

```python
# Success
{
    "status": "success",
    "data": {...},
    "metadata": {
        "execution_time_ms": 1234,
        "container_id": "...",
        "dotnet_version": "8.0.0"
    }
}

# Error
{
    "status": "error",
    "error": {
        "type": "BuildError",
        "message": "...",
        "suggestions": ["...", "..."]
    }
}
```

## Security & Resource Management

### Container Isolation
- Resource limits (CPU, memory) enforced via Docker
- Read-only filesystem except `/workspace`
- Non-root user inside containers
- Auto-cleanup after 1 hour idle timeout

### Resource Limits
- Max 5 concurrent containers
- Max 10 projects per session
- 30 second default execution timeout
- No Docker socket access from containers

## Docker Image Management

Three base images (Alpine-based for minimal size):
- `dotnet-sandbox:8` - .NET 8 SDK
- `dotnet-sandbox:9` - .NET 9 SDK
- `dotnet-sandbox:10-rc2` - .NET 10 RC2 SDK

Build all images:
```bash
cd docker && ./build-images.sh
```

## Development Workflow

### Setup
```bash
# Install dependencies (uv)
uv sync

# Build Docker images
cd docker && ./build-images.sh
```

### Testing
```bash
# Run unit tests
uv run pytest tests/

# Run integration tests (requires Docker)
uv run pytest tests/test_integration.py

# Run with coverage
uv run pytest --cov=src tests/
```

### Running the Server
```bash
# Standard MCP stdio server
uv run python -m src.server

# With debug logging
DEBUG=1 uv run python -m src.server
```

## Core Components

### DockerContainerManager (`docker_manager.py`)
- `create_container()` - Create/start container with mounted volume
- `execute_command()` - Execute command in container, return (stdout, stderr, exit_code)
- `stop_container()` - Stop and remove container
- `list_containers()` - List all active sandbox containers

### ProjectManager (`project_manager.py`)
- `create_project_workspace()` - Create project directory structure
- `add_file()` - Add/update files in project
- `get_project_path()` - Get absolute path to project
- `cleanup_project()` - Remove project directory

### DotNetExecutor (`executor.py`)
- `build_project()` - Build .NET project, return parsed results
- `run_snippet()` - Execute C# code snippet with top-level statements
- `host_web_app()` - Start web app in container

### OutputFormatter (`formatter.py`)
- Enforces 25,000 character MCP limit
- Supports `detail_level`: "concise" (first 50 lines) or "full"
- Parses MSBuild output into structured errors

### ErrorEnhancer (`error_enhancer.py`)
- Parses common C# compiler errors (CS0246, CS0103, etc.)
- Adds actionable suggestions (missing using directives, package references)

## Error Handling Categories

1. **User Input Errors**: Clear validation messages via Pydantic
2. **Build Errors**: Parse MSBuild output, add suggestions
3. **Runtime Errors**: Capture exceptions, timeouts, OOM
4. **Infrastructure Errors**: Docker unavailable, port conflicts, disk space
5. **Resource Limits**: Too many containers, quota exceeded

## Implementation Priorities

### MVP (Priority 1)
- `dotnet_execute_snippet` - Quick C# testing
- `dotnet_create_project` - Project setup
- `dotnet_build_project` - Build functionality
- `dotnet_run_project` - Console execution
- `dotnet_cleanup_all` - Resource cleanup

### Phase 2
- `dotnet_host_api` - Web API hosting
- `dotnet_test_endpoint` - HTTP endpoint testing
- `dotnet_list_containers` - Container visibility
- `dotnet_stop_container` - Individual cleanup

### Phase 3
- `dotnet_add_file` - File manipulation
- `dotnet_add_package` - NuGet package management
- `dotnet_get_project_files` - Project inspection
- `dotnet_read_file` - File reading

## Testing Strategy

### Unit Tests
- Mock Docker operations
- Test Pydantic validation
- Test error parsing and enhancement

### Integration Tests
- Full workflows: create → build → run → cleanup
- Error scenarios (build failures, timeouts)
- Concurrent operations
- Cleanup mechanisms

### Manual Testing Scenarios
1. Execute "Hello World" snippet
2. Create web API and test endpoint
3. Test with invalid code (verify helpful errors)
4. Test concurrent executions
5. Verify cleanup after timeout
6. Compare output across .NET versions
