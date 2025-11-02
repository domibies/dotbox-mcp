"""FastMCP server for .NET code execution in Docker containers."""

import asyncio
import sys
from typing import Any

import httpx
from docker.errors import DockerException
from mcp.server import Server
from mcp.types import TextContent, Tool, ToolAnnotations
from pydantic import ValidationError

from src.docker_manager import DockerContainerManager
from src.executor import DotNetExecutor
from src.formatter import OutputFormatter
from src.models import (
    DetailLevel,
    ExecuteCommandInput,
    ExecuteSnippetInput,
    GetLogsInput,
    KillProcessInput,
    ListContainersInput,
    ListFilesInput,
    ReadFileInput,
    ResponseFormat,
    RunBackgroundInput,
    StartContainerInput,
    StopContainerInput,
    TestEndpointInput,
    WriteFileInput,
)

# Initialize MCP server
server = Server("dotbox-mcp")

# Initialize components (will be created on first use)
docker_manager: DockerContainerManager | None = None
executor: DotNetExecutor | None = None
formatter: OutputFormatter | None = None


def _initialize_components() -> tuple[DockerContainerManager, DotNetExecutor, OutputFormatter]:
    """Initialize Docker manager, executor, and formatter.

    Returns:
        Tuple of (docker_manager, executor, formatter)

    Raises:
        DockerException: If Docker is not available
    """
    global docker_manager, executor, formatter

    if docker_manager is None:
        docker_manager = DockerContainerManager()

    if executor is None:
        executor = DotNetExecutor(docker_manager=docker_manager)

    if formatter is None:
        formatter = OutputFormatter()

    return docker_manager, executor, formatter


def _get_response_format(arguments: dict[str, Any]) -> ResponseFormat:
    """Extract response_format from arguments, defaulting to MARKDOWN."""
    format_str = arguments.get("response_format", "markdown")
    try:
        return ResponseFormat(format_str)
    except ValueError:
        return ResponseFormat.MARKDOWN


def _format_error_response(
    error_message: str,
    error_details: str,
    suggestions: list[str] | None = None,
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Format an error response in the requested format."""
    fmt = OutputFormatter()

    if response_format == ResponseFormat.MARKDOWN:
        response = f"# Error ✗\n\n**{error_message}**\n\n"
        if error_details:
            response += f"## Details\n\n```\n{error_details}\n```\n\n"
        if suggestions:
            response += "## Suggestions\n\n"
            for suggestion in suggestions:
                response += f"- {suggestion}\n"
        return response
    else:  # JSON format
        error_dict: dict[str, Any] = {
            "type": "Error",
            "message": error_message,
            "details": error_details,
        }
        if suggestions:
            error_dict["suggestions"] = suggestions

        return fmt.format_json_response(
            status="error",
            error=error_dict,
        )


@server.list_tools()  # type: ignore[misc, no-untyped-call]
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    # Perform lazy cleanup on every tool invocation
    if docker_manager is not None:
        docker_manager._lazy_cleanup(idle_timeout_minutes=30)

    return [
        Tool(
            name="dotnet_execute_snippet",
            description="""Execute a C# code snippet in an isolated Docker container.

Creates a temporary .NET project, builds it, executes the code, and returns output.
Container is automatically cleaned up after execution.

**When to use:**
- Quick C# code testing and prototyping
- Testing NuGet packages across .NET versions
- Comparing behavior across .NET 8, 9, and 10 RC2

**When NOT to use:**
- Multi-file projects (use dotbox-mcp:dotnet_start_container + dotbox-mcp:dotnet_write_file workflow)
- Web servers/APIs (use project workflow with dotbox-mcp:dotnet_run_background)
- Persistent containers (use dotbox-mcp:dotnet_start_container)

**NuGet packages:** Search web for recent API examples before implementing package-based functionality.

**Note:** Show code snippets inline to users before tool calls (UI collapses tool output).
**Note:** When presenting results, summarize output relevant to the user's question.

**Features:**
- Supports .NET 8, 9, 10 RC2
- Auto NuGet package resolution (fetches latest stable from NuGet API)
- Compilation error parsing with actionable suggestions
- Resource limits and timeouts

**Package specification:**
- Latest version: `"Newtonsoft.Json"`
- Specific version: `"Newtonsoft.Json@13.0.3"`

**Code format examples:**
- Top-level: `Console.WriteLine("Hello");`
- Full program: `class Program { static void Main() { ... } }`
- With using: `using System.Linq; var result = Enumerable.Range(1, 10).Sum();`

**Returns:**
- Success: JSON with `{status: "success", data: {output, exit_code, dotnet_version}}`
- Error: JSON with `{status: "error", error: {type, message, details, suggestions}}`
            """,
            inputSchema=ExecuteSnippetInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="dotnet_start_container",
            description="""Start a persistent Docker container for a .NET project.

Creates and starts a long-running container for multi-step operations. Files live inside container only (no volume mounting).

**When to use:**
- Multi-file .NET projects requiring multiple operations
- Building and running projects in separate steps
- Hosting web APIs or long-running services
- Preserving state between operations

**When NOT to use:**
- One-shot code execution (use dotbox-mcp:dotnet_execute_snippet)
- Quick code testing without project structure

**Note:** Inform users when starting containers (e.g., "Starting .NET 9 container...").

**Zero-config usage:**
- Auto-generates project_id: `dotnet{version}-proj-{random}` (e.g., `dotnet8-proj-a1b2c3`)
- Simply call with .NET version or no parameters

**Container capabilities:**
- Includes git, jq, sqlite3, tree for advanced workflows
- Use dotbox-mcp:dotnet_execute_command() to run these tools

**Port mapping (optional):**
- Format: `{"container_port": host_port}` (e.g., `{"5000": 8080}`)
- Container port: Where your .NET app listens inside container
- Host port: Where you access it on localhost (use 0 for auto-assign)
- App must explicitly listen on container port (configure in appsettings.json or --urls flag)
- Use dotbox-mcp:dotnet_list_containers() to see actual assigned ports

**Container lifecycle:**
- Auto-cleanup after 30 minutes idle
- Use dotbox-mcp:dotnet_stop_container to manually stop
- Idempotent: Returns existing container if called with same project_id

**Common workflows:**
- Web API: Start with ports → dotnet new webapi → configure port → run background
- Console: Start without ports → dotnet new console → run directly

**Returns:**
- container_id: Docker container ID
- project_id: Project identifier (auto-generated or provided)
- status: "running"
            """,
            inputSchema=StartContainerInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="dotnet_stop_container",
            description="""Stop and remove a persistent Docker container.

Stop a running container and remove it. Container state and files are lost permanently.

**When to use:**
- After completing all operations
- To free resources immediately
- To restart with fresh state

**When NOT to use:**
- Between build and run operations
- During active development

**Behavior:**
- Idempotent (no error if already stopped)
- Auto-cleanup after 30 minutes idle (explicit stopping optional)
- All container files lost (ephemeral storage)

**Returns:** Success status, project_id, message
            """,
            inputSchema=StopContainerInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="dotnet_write_file",
            description="""Write a file to a persistent container.

Create or update files in a running container for project development.

**When to use:**
- Configuration files (appsettings.json, etc.)
- Custom source files after project creation
- Non-standard project scenarios
- Educational examples

**File editing:** This is the ONLY way to edit files - tools like str_replace are not available. Write the complete new file content.

**When NOT to use:**
- One-shot code execution (use dotbox-mcp:dotnet_execute_snippet)
- Standard project creation (prefer `dotnet new` via dotbox-mcp:dotnet_execute_command)
- When container doesn't exist (start container first)

**NuGet packages:** Search web for recent API examples before implementing package-based functionality.

**Note:** Show code snippets inline before tool calls (UI collapses tool output).

**Prefer dotnet CLI for standard projects:**
- Use `dotnet new webapi` instead of manually creating .csproj files
- Use `dotnet add package` instead of editing project files
- CLI ensures correct project structure

**Security:**
- Paths must be within /workspace/ directory
- Directory traversal (..) blocked
- Max file size: 100KB

**Returns:** Success message or error
            """,
            inputSchema=WriteFileInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="dotnet_read_file",
            description="""Read a file from a persistent container.

Read text file contents from a running container (source code, logs, output files).

**When to use:**
- Reading source code, logs, or output files
- Verifying file contents after writing
- Debugging project structure

**When NOT to use:**
- When container doesn't exist
- For binary files (text only)

**Security:** Paths must be within /workspace/, directory traversal blocked

**Returns:** File content as text or error
            """,
            inputSchema=ReadFileInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="dotnet_list_files",
            description="""List files in a container directory.

Explore directory contents in a running container (non-recursive).

**When to use:**
- Exploring project structure
- Verifying files were created
- Finding build artifacts

**When NOT to use:**
- When container doesn't exist
- For recursive listing (lists immediate children only)

**Security:** Paths must be within /workspace/, directory traversal blocked
**Default:** Lists /workspace if no path specified

**Returns:** List of file/directory names or empty list
            """,
            inputSchema=ListFilesInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="dotnet_execute_command",
            description="""Execute a command in a persistent container.

Run .NET CLI commands, shell commands, or container utilities in a running container.

**When to use:**
- Building .NET projects
- Running .NET applications
- Package management (dotnet add package)
- Debugging with shell commands

**When NOT to use:**
- One-shot code execution (use dotbox-mcp:dotnet_execute_snippet)
- When container doesn't exist
- For file read/write operations (use dedicated tools)

**Common commands:**
- Project creation: `dotnet new webapi -n MyApi -o /workspace/MyApi`
- Build: `dotnet build /workspace/MyApp`
- Run: `dotnet run --project /workspace/MyApp`
- Add package: `dotnet add /workspace/MyApi package Newtonsoft.Json`
- Test: `dotnet test /workspace/MyApp`

**Container utilities:**
- git, jq, sqlite3, tree available for advanced workflows

**Port access note:**
- Commands run INSIDE container → use CONTAINER port (e.g., 5000)
- dotbox-mcp:dotnet_test_endpoint runs OUTSIDE → use HOST port (e.g., 8080)

**Timeout:**
- Default: 30 seconds
- Range: 1-300 seconds
- Adjust for long builds

**Note:** When presenting results, summarize output relevant to the user's question.

**Returns:**
- stdout, stderr, exit_code (0 = success)
            """,
            inputSchema=ExecuteCommandInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="dotnet_run_background",
            description="""Run a long-running process in background (e.g., web server).

Start processes like web APIs that need to keep running while you perform other operations.

**When to use:**
- Starting web APIs or web applications
- Running background services
- Any continuously running process

**After starting, always provide:**
- Base API URL (e.g., http://localhost:8080)
- Swagger UI URL if available (e.g., http://localhost:8080/swagger)
- Format each URL on its own line for clickability

**When NOT to use:**
- Short-lived commands (use dotbox-mcp:dotnet_execute_command)
- One-shot code execution (use dotbox-mcp:dotnet_execute_snippet)

**Background execution:**
- Process runs in background using nohup
- Tool returns immediately after wait_for_ready period (default 5s)
- Use dotbox-mcp:dotnet_get_logs to check process output

**Common workflow:**
1. Start container with ports
2. Create project and configure listening port
3. Run in background
4. Test endpoint with dotbox-mcp:dotnet_test_endpoint
5. Check dotbox-mcp:dotnet_get_logs if needed

**Returns:** Success message with process confirmation
            """,
            inputSchema=RunBackgroundInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="dotnet_test_endpoint",
            description="""Test HTTP endpoints by making requests.

Make HTTP requests to test web APIs and endpoints from the host machine.

**When to use:**
- Testing web API endpoints
- Verifying server is responding
- Testing different HTTP methods
- Checking API responses

**Present results concisely** - summarize status and key response data, don't dump full HTTP details unless debugging.

**When NOT to use:**
- Executing C# code (use dotbox-mcp:dotnet_execute_snippet)
- Checking if process is running (use dotbox-mcp:dotnet_get_logs)

**Features:**
- Supports GET, POST, PUT, DELETE, PATCH
- Custom headers and request body
- Auto localhost→host.docker.internal translation when MCP server runs in container

**URL handling:**
- Use localhost with HOST port (e.g., `http://localhost:8080/health`)
- Port matches HOST port from dotbox-mcp:dotnet_start_container, not container port

**Returns:** HTTP status code, headers, and response body
            """,
            inputSchema=TestEndpointInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="dotnet_get_logs",
            description="""Retrieve container logs for debugging.

Get stdout/stderr logs from container to debug processes and see output.

**When to use:**
- Debugging background processes
- Checking web server startup
- Troubleshooting errors

**When NOT to use:**
- Reading file contents (use dotbox-mcp:dotnet_read_file)
- Short-lived command output (use dotbox-mcp:dotnet_execute_command)

**Log sources:** All stdout/stderr, dotnet run output, application logs, errors

**Parameters:**
- tail: Lines from end (default 50, max 1000)
- since: Last N seconds (optional)

**Note:** When presenting results, summarize output relevant to the user's question.

**Returns:** Container logs as text
            """,
            inputSchema=GetLogsInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="dotnet_kill_process",
            description="""Kill background processes in a container.

Stop long-running background processes (like web servers) without stopping the container.

**Use cases:**
- Stop web server to make code changes
- Iterative development: run → test → kill → modify → run
- Kill stuck processes

**Why not dotbox-mcp:dotnet_stop_container:**
- Keeps container and files intact
- Faster than recreating
- Preserves state

**Parameters:**
- process_pattern (optional): Specific pattern (e.g., "dotnet run --project MyApi")
- If omitted: Kills ALL dotnet processes

**Returns:** Success message or "no processes found"
            """,
            inputSchema=KillProcessInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,  # Kills processes
                idempotentHint=False,  # Different processes may be running each time
                openWorldHint=False,
            ),
        ),
        Tool(
            name="dotnet_list_containers",
            description="""List all active containers managed by this MCP server.

Discover running containers, their ports, and status.

**When to use:**
- Finding forgotten project_ids
- Checking port mappings
- Resource monitoring (5 container limit)
- Debugging port access issues

**Information provided:**
- project_id: Identifier for other tools
- container_id: Docker container ID
- name: Human-readable name
- status: Container status
- ports: Port mappings (e.g., {"5000/tcp": "8080"})

**No parameters required:** Lists ALL managed containers

**Returns:** List of containers with details
            """,
            inputSchema=ListContainersInput.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=True,  # Read-only operation
                destructiveHint=False,
                idempotentHint=True,  # Same containers will be listed each time
                openWorldHint=False,  # Closed world - only lists managed containers
            ),
        ),
    ]


@server.call_tool()  # type: ignore[misc]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle MCP tool calls."""
    if name == "dotnet_execute_snippet":
        return await execute_snippet(arguments)
    elif name == "dotnet_start_container":
        return await start_container(arguments)
    elif name == "dotnet_stop_container":
        return await stop_container(arguments)
    elif name == "dotnet_write_file":
        return await write_file(arguments)
    elif name == "dotnet_read_file":
        return await read_file(arguments)
    elif name == "dotnet_list_files":
        return await list_files(arguments)
    elif name == "dotnet_execute_command":
        return await execute_command(arguments)
    elif name == "dotnet_run_background":
        return await run_background(arguments)
    elif name == "dotnet_test_endpoint":
        return await test_endpoint(arguments)
    elif name == "dotnet_get_logs":
        return await get_logs(arguments)
    elif name == "dotnet_kill_process":
        return await kill_process(arguments)
    elif name == "dotnet_list_containers":
        return await list_containers(arguments)

    raise ValueError(f"Unknown tool: {name}")


def _running_in_container() -> bool:
    """Detect if the MCP server is running inside a Docker container.

    Returns:
        True if running in container, False otherwise
    """
    import os

    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")


def _translate_localhost_url(url: str) -> str:
    """Translate localhost URLs to host.docker.internal when running in container.

    This enables the MCP server (running in a container) to access sandbox containers
    whose ports are mapped to the host machine.

    Args:
        url: Original URL (may contain localhost or 127.0.0.1)

    Returns:
        Translated URL with host.docker.internal if running in container
    """
    if _running_in_container():
        url = url.replace("localhost", "host.docker.internal")
        url = url.replace("127.0.0.1", "host.docker.internal")
    return url


async def execute_snippet(arguments: dict[str, Any]) -> list[TextContent]:
    """Execute C# code snippet.

    Args:
        arguments: Tool arguments matching ExecuteSnippetInput schema

    Returns:
        List with single TextContent containing JSON response
    """
    try:
        # Validate input
        input_data = ExecuteSnippetInput(**arguments)

        # Initialize components
        _, exec_instance, fmt = _initialize_components()

        # Execute snippet
        result = await exec_instance.run_snippet(
            code=input_data.code,
            dotnet_version=input_data.dotnet_version,
            packages=input_data.packages,
            timeout=30,
        )

        # Format response based on requested format
        if result["success"]:
            # Success case
            if input_data.response_format == ResponseFormat.MARKDOWN:
                response = fmt.format_execution_result_markdown(
                    status="success",
                    stdout=result["stdout"],
                    stderr=result["stderr"],
                    exit_code=result["exit_code"],
                    dotnet_version=input_data.dotnet_version.value,
                    execution_time_ms=result.get("execution_time_ms", 0),
                    detail_level=input_data.detail_level,
                )
            else:  # JSON format
                output = result["stdout"] if result["stdout"] else result["stderr"]
                response = fmt.format_json_response(
                    status="success",
                    data={
                        "output": output,
                        "exit_code": result["exit_code"],
                        "dotnet_version": input_data.dotnet_version.value,
                        "code": input_data.code,
                    },
                    metadata={
                        "container_id": result.get("container_id", ""),
                    },
                )

        else:
            # Build or execution error
            if input_data.response_format == ResponseFormat.MARKDOWN:
                # Format build errors in Markdown
                if result["build_errors"]:
                    response = fmt.format_build_error_markdown(
                        errors=result["build_errors"],
                        suggestions=result.get("suggestions", []),
                        dotnet_version=input_data.dotnet_version.value,
                        execution_time_ms=result.get("execution_time_ms", 0),
                    )
                else:
                    # Runtime execution error
                    response = fmt.format_execution_result_markdown(
                        status="error",
                        stdout=result["stdout"],
                        stderr=result["stderr"],
                        exit_code=result["exit_code"],
                        dotnet_version=input_data.dotnet_version.value,
                        execution_time_ms=result.get("execution_time_ms", 0),
                        detail_level=input_data.detail_level,
                    )
            else:  # JSON format
                error_output = fmt.format_execution_output(
                    stdout=result["stdout"],
                    stderr=result["stderr"],
                    exit_code=result["exit_code"],
                    detail_level=DetailLevel.FULL,  # Always show full errors
                )

                response = fmt.format_json_response(
                    status="error",
                    error={
                        "type": "BuildError" if result["build_errors"] else "ExecutionError",
                        "message": "Build failed"
                        if result["build_errors"]
                        else "Code execution failed",
                        "details": error_output,
                        "build_errors": result["build_errors"] if result["build_errors"] else [],
                    },
                    data={
                        "code": input_data.code,
                        "exit_code": result["exit_code"],
                        "dotnet_version": input_data.dotnet_version.value,
                    },
                )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        # Input validation error
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        # Docker not available
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker is not available",
            error_details=str(e),
            suggestions=[
                "Ensure Docker is installed and running",
                "Check Docker socket permissions",
                "Verify Docker images are built (run docker/build-images.sh)",
            ],
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        # Unexpected error
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="An unexpected error occurred",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def start_container(arguments: dict[str, Any]) -> list[TextContent]:
    """Start a persistent Docker container for a project.

    Args:
        arguments: Tool arguments matching StartContainerInput schema

    Returns:
        List with single TextContent containing response
    """
    try:
        # Validate input
        input_data = StartContainerInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Check if container already exists for this project (project_id is now guaranteed to exist after validation)
        existing_container = mgr.get_container_by_project_id(input_data.project_id)  # type: ignore[arg-type]
        if existing_container:
            # Get port information
            port_info = {}
            containers = mgr.list_containers()
            for container in containers:
                if container.container_id == existing_container:
                    port_info = container.ports
                    break

            # Format response based on requested format
            if input_data.response_format == ResponseFormat.MARKDOWN:
                # Build URLs if ports are mapped
                urls = []
                if port_info:
                    for _container_port, host_port in port_info.items():
                        urls.append(f"http://localhost:{host_port}")

                response = fmt.format_container_info_markdown(
                    project_id=input_data.project_id,  # type: ignore[arg-type]
                    container_id=existing_container,
                    dotnet_version=input_data.dotnet_version.value,
                    ports=port_info if port_info else None,  # type: ignore[arg-type]
                    urls=urls if urls else None,
                    status="already_running",
                )
            else:
                data: dict[str, Any] = {
                    "container_id": existing_container,
                    "project_id": input_data.project_id,
                    "message": "Container already running",
                }
                if port_info:
                    data["ports"] = port_info
                response = fmt.format_json_response(
                    status="success",
                    data=data,
                )
            return [TextContent(type="text", text=response)]

        # Create new container (no volume mounting - files live in container only)
        container_id = mgr.create_container(
            dotnet_version=input_data.dotnet_version.value,
            project_id=input_data.project_id,  # type: ignore[arg-type]
            port_mapping=input_data.ports,
        )

        # Get port information if ports were mapped
        port_info = {}
        if input_data.ports:
            # Get actual mapped ports from container
            containers = mgr.list_containers()
            for container in containers:
                if container.container_id == container_id:
                    port_info = container.ports
                    break

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            # Build URLs if ports are mapped
            urls = []
            if port_info:
                for _container_port, host_port in port_info.items():
                    urls.append(f"http://localhost:{host_port}")

            response = fmt.format_container_info_markdown(
                project_id=input_data.project_id,  # type: ignore[arg-type]
                container_id=container_id,
                dotnet_version=input_data.dotnet_version.value,
                ports=port_info if port_info else None,  # type: ignore[arg-type]
                urls=urls if urls else None,
                status="success",
            )
        else:  # JSON format
            response_data: dict[str, Any] = {
                "container_id": container_id,
                "project_id": input_data.project_id,
                "dotnet_version": input_data.dotnet_version.value,
            }
            if port_info:
                response_data["ports"] = port_info

            response = fmt.format_json_response(
                status="success",
                data=response_data,
            )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        # Input validation error
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        # Check if this is a port conflict error (must check before generic Docker error)
        response_format = _get_response_format(arguments)
        error_msg = str(e).lower()
        is_port_conflict = any(
            phrase in error_msg
            for phrase in [
                "address already in use",
                "bind: address already in use",
                "port is already allocated",
                "failed to set up container networking",
            ]
        )

        if is_port_conflict and hasattr(input_data, "ports") and input_data.ports:
            # Port conflict - provide actionable suggestions to LLM
            # Build auto-assign example
            auto_ports = ", ".join(f"'{cp}': 0" for cp in input_data.ports.keys())

            error_response = _format_error_response(
                error_message="Port conflict: One or more requested ports are already in use",
                error_details=str(e),
                suggestions=[
                    f"Use auto-assigned ports instead: dotnet_start_container(project_id='{input_data.project_id}', ports={{{auto_ports}}})",
                    "Check which containers are using the port: dotnet_list_containers()",
                    "Stop the conflicting container if no longer needed",
                    "Use different host ports that are not occupied",
                ],
                response_format=response_format,
            )
        else:
            # Generic Docker error (daemon not running, image not found, etc.)
            error_response = _format_error_response(
                error_message="Docker error",
                error_details=str(e),
                suggestions=[
                    "Ensure Docker is installed and running",
                    "Check Docker socket permissions",
                    "Verify Docker images are built (run docker/build-images.sh)",
                ],
                response_format=response_format,
            )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        # Other unexpected error
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to start container",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def stop_container(arguments: dict[str, Any]) -> list[TextContent]:
    """Stop and remove a Docker container.

    Args:
        arguments: Tool arguments matching StopContainerInput schema

    Returns:
        List with single TextContent containing response
    """
    try:
        # Validate input
        input_data = StopContainerInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Find container by project ID
        container_id = mgr.get_container_by_project_id(input_data.project_id)

        if not container_id:
            if input_data.response_format == ResponseFormat.MARKDOWN:
                response = f"# Container Status ✓\n\n**Project:** {input_data.project_id}\n\nNo running container found for this project."
            else:
                response = fmt.format_json_response(
                    status="success",
                    data={
                        "project_id": input_data.project_id,
                        "message": "No running container found",
                    },
                )
            return [TextContent(type="text", text=response)]

        # Stop the container
        mgr.stop_container(container_id)

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            response = fmt.format_container_info_markdown(
                project_id=input_data.project_id,
                container_id=container_id,
                status="success",
                message="Container stopped and removed successfully.",
            )
        else:
            response = fmt.format_json_response(
                status="success",
                data={
                    "project_id": input_data.project_id,
                    "container_id": container_id,
                    "message": "Container stopped and removed",
                },
            )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        # Input validation error
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        # Docker not available
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker is not available",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        # Unexpected error
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to stop container",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def write_file(arguments: dict[str, Any]) -> list[TextContent]:
    """Write a file to a container.

    Args:
        arguments: Tool arguments matching WriteFileInput schema

    Returns:
        List with single TextContent containing response
    """
    try:
        # Validate input
        input_data = WriteFileInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Find container by project ID
        container_id = mgr.get_container_by_project_id(input_data.project_id)

        if not container_id:
            response = fmt.format_human_readable_response(
                status="error",
                error_message=f"No running container found for project '{input_data.project_id}'",
                error_details="Start a container first with dotnet_start_container",
            )
            return [TextContent(type="text", text=response)]

        # Write file to container
        mgr.write_file(
            container_id=container_id,
            dest_path=input_data.path,
            content=input_data.content,
        )

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            response = f"# File Written ✓\n\n**Project:** {input_data.project_id}\n**Path:** `{input_data.path}`\n\nFile written successfully."
        else:
            response = fmt.format_json_response(
                status="success",
                data={
                    "project_id": input_data.project_id,
                    "container_id": container_id,
                    "path": input_data.path,
                    "message": "File written successfully",
                },
            )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker operation failed",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to write file",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def read_file(arguments: dict[str, Any]) -> list[TextContent]:
    """Read a file from a container.

    Args:
        arguments: Tool arguments matching ReadFileInput schema

    Returns:
        List with single TextContent containing file content or error
    """
    try:
        # Validate input
        input_data = ReadFileInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Find container by project ID
        container_id = mgr.get_container_by_project_id(input_data.project_id)

        if not container_id:
            response = fmt.format_human_readable_response(
                status="error",
                error_message=f"No running container found for project '{input_data.project_id}'",
                error_details="Start a container first with dotnet_start_container",
            )
            return [TextContent(type="text", text=response)]

        # Read file from container
        try:
            content_bytes = mgr.read_file(
                container_id=container_id,
                path=input_data.path,
            )
            content = content_bytes.decode("utf-8")

            # Format response based on requested format
            if input_data.response_format == ResponseFormat.MARKDOWN:
                # Determine language for syntax highlighting
                lang = ""
                if input_data.path.endswith(".cs"):
                    lang = "csharp"
                elif input_data.path.endswith(".json"):
                    lang = "json"
                elif input_data.path.endswith(".xml"):
                    lang = "xml"

                response = f"# File Content ✓\n\n**Project:** {input_data.project_id}\n**Path:** `{input_data.path}`\n\n```{lang}\n{content}\n```"
            else:
                response = fmt.format_human_readable_response(
                    status="success",
                    output=content,
                    project_id=input_data.project_id,
                )

            return [TextContent(type="text", text=response)]

        except FileNotFoundError:
            response_format = _get_response_format(arguments)
            error_response = _format_error_response(
                error_message=f"File not found: {input_data.path}",
                error_details="Check the path and try again",
                response_format=response_format,
            )
            return [TextContent(type="text", text=error_response)]

    except ValidationError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker operation failed",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to read file",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def list_files(arguments: dict[str, Any]) -> list[TextContent]:
    """List files in a container directory.

    Args:
        arguments: Tool arguments matching ListFilesInput schema

    Returns:
        List with single TextContent containing file list or error
    """
    try:
        # Validate input
        input_data = ListFilesInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Find container by project ID
        container_id = mgr.get_container_by_project_id(input_data.project_id)

        if not container_id:
            response = fmt.format_human_readable_response(
                status="error",
                error_message=f"No running container found for project '{input_data.project_id}'",
                error_details="Start a container first with dotnet_start_container",
            )
            return [TextContent(type="text", text=response)]

        # List files in directory
        files = mgr.list_files(
            container_id=container_id,
            path=input_data.path,
        )

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            if not files:
                file_list = "*Directory is empty or does not exist*"
            else:
                file_list = "\n".join(f"- `{f}`" for f in files)

            response = f"# Directory Contents ✓\n\n**Project:** {input_data.project_id}\n**Path:** `{input_data.path}`\n\n{file_list}"
        else:
            response = fmt.format_json_response(
                status="success",
                data={
                    "project_id": input_data.project_id,
                    "path": input_data.path,
                    "files": files,
                    "count": len(files),
                },
            )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker operation failed",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to list files",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def execute_command(arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a command in a container.

    Args:
        arguments: Tool arguments matching ExecuteCommandInput schema

    Returns:
        List with single TextContent containing command output or error
    """
    try:
        # Validate input
        input_data = ExecuteCommandInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Find container by project ID
        container_id = mgr.get_container_by_project_id(input_data.project_id)

        if not container_id:
            response = fmt.format_human_readable_response(
                status="error",
                error_message=f"No running container found for project '{input_data.project_id}'",
                error_details="Start a container first with dotnet_start_container",
            )
            return [TextContent(type="text", text=response)]

        # Execute command
        stdout, stderr, exit_code = mgr.execute_command(
            container_id=container_id,
            command=input_data.command,
            timeout=input_data.timeout,
        )

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            symbol = "✓" if exit_code == 0 else "✗"
            title = "Command Executed" if exit_code == 0 else "Command Failed"

            sections = [f"# {title} {symbol}", ""]
            sections.append(f"**Project:** {input_data.project_id}")
            sections.append(f"**Command:** `{' '.join(input_data.command)}`")
            sections.append(f"**Exit Code:** {exit_code}")
            sections.append("")

            if stdout:
                sections.append("## Output")
                sections.append("")
                sections.append(f"```\n{stdout}\n```")
                sections.append("")

            if stderr:
                sections.append("## Error Output")
                sections.append("")
                sections.append(f"```\n{stderr}\n```")

            response = "\n".join(sections)
        else:
            # JSON format
            data = {
                "command": input_data.command,
                "exit_code": exit_code,
                "project_id": input_data.project_id,
                "container_id": container_id,
            }
            if stdout:
                data["stdout"] = stdout
            if stderr:
                data["stderr"] = stderr

            if exit_code == 0:
                response = fmt.format_json_response(
                    status="success",
                    data=data,
                )
            else:
                response = fmt.format_json_response(
                    status="error",
                    error={
                        "type": "CommandExecutionError",
                        "message": f"Command failed with exit code {exit_code}",
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                    },
                    metadata={"project_id": input_data.project_id, "container_id": container_id},
                )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker operation failed",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to execute command",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def run_background(arguments: dict[str, Any]) -> list[TextContent]:
    """Run a command in background (long-running process).

    Args:
        arguments: Tool arguments matching RunBackgroundInput schema

    Returns:
        List with single TextContent containing response
    """
    try:
        # Validate input
        input_data = RunBackgroundInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Find container by project ID
        container_id = mgr.get_container_by_project_id(input_data.project_id)

        if not container_id:
            response = fmt.format_human_readable_response(
                status="error",
                error_message=f"No running container found for project '{input_data.project_id}'",
                error_details="Start a container first with dotnet_start_container",
            )
            return [TextContent(type="text", text=response)]

        # Build background command using nohup and shell backgrounding
        # Output redirected to container stdout/stderr (accessible via logs)
        command_str = " ".join(input_data.command)
        bg_command = ["sh", "-c", f"nohup {command_str} </dev/null >/proc/1/fd/1 2>/proc/1/fd/2 &"]

        # Execute background command
        stdout, stderr, exit_code = mgr.execute_command(
            container_id=container_id,
            command=bg_command,
            timeout=5,
        )

        # Wait for process to start
        if input_data.wait_for_ready > 0:
            import asyncio

            await asyncio.sleep(input_data.wait_for_ready)

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            message = f"Process started: `{' '.join(input_data.command)}`\n\nWaited {input_data.wait_for_ready}s for startup. Use `dotnet_get_logs` to check output."
            response = fmt.format_container_info_markdown(
                project_id=input_data.project_id,
                container_id=container_id,
                status="success",
                message=message,
            )
        else:  # JSON format
            response = fmt.format_json_response(
                status="success",
                data={
                    "project_id": input_data.project_id,
                    "container_id": container_id,
                    "command": input_data.command,
                    "wait_for_ready": input_data.wait_for_ready,
                    "message": "Process started in background",
                },
            )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker operation failed",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to run background process",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def test_endpoint(arguments: dict[str, Any]) -> list[TextContent]:
    """Test an HTTP endpoint.

    Args:
        arguments: Tool arguments matching TestEndpointInput schema

    Returns:
        List with single TextContent containing response
    """
    try:
        # Validate input
        input_data = TestEndpointInput(**arguments)

        # Initialize formatter
        _, _, fmt = _initialize_components()

        # Translate localhost → host.docker.internal when MCP server runs in container
        # This allows the MCP container to access sandbox containers via host ports
        url = _translate_localhost_url(input_data.url)

        # Make HTTP request using httpx
        import time

        start_time = time.time()

        async with httpx.AsyncClient(timeout=input_data.timeout) as client:
            # Make request with explicit arguments for type safety
            # Only pass headers if not empty (httpx handles None differently than {})
            headers = input_data.headers if input_data.headers else None

            if input_data.body and input_data.method in ["POST", "PUT", "PATCH"]:
                response = await client.request(
                    input_data.method,
                    url,
                    headers=headers,
                    content=input_data.body,
                )
            else:
                response = await client.request(
                    input_data.method,
                    url,
                    headers=headers,
                )

        response_time_ms = int((time.time() - start_time) * 1000)

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            result = fmt.format_endpoint_response_markdown(
                method=input_data.method,
                url=input_data.url,
                status_code=response.status_code,
                response_body=response.text,
                response_headers=dict(response.headers),
                response_time_ms=response_time_ms,
                detail_level=input_data.detail_level,
            )
        else:  # JSON format
            result = fmt.format_json_response(
                status="success" if 200 <= response.status_code < 400 else "error",
                data={
                    "method": input_data.method,
                    "url": input_data.url,
                    "status_code": response.status_code,
                    "response_body": response.text,
                    "response_headers": dict(response.headers),
                    "response_time_ms": response_time_ms,
                },
            )

        return [TextContent(type="text", text=result)]

    except ValidationError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except httpx.TimeoutException:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message=f"Request timed out after {input_data.timeout} seconds",
            error_details=f"Could not connect to {input_data.url}",
            suggestions=[
                "Check if the server is running",
                "Verify the port mapping is correct",
                "Use dotnet_get_logs to check server startup",
                "Increase timeout if server is slow to start",
            ],
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except httpx.ConnectError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Connection refused",
            error_details=str(e),
            suggestions=[
                "Check if the server is running: dotnet_get_logs",
                "Verify the URL and port are correct",
                "Ensure port mapping was configured: dotnet_start_container(ports={...})",
                "Wait a bit longer for server to start",
            ],
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="HTTP request failed",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def get_logs(arguments: dict[str, Any]) -> list[TextContent]:
    """Get container logs.

    Args:
        arguments: Tool arguments matching GetLogsInput schema

    Returns:
        List with single TextContent containing logs
    """
    try:
        # Validate input
        input_data = GetLogsInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Find container by project ID
        container_id = mgr.get_container_by_project_id(input_data.project_id)

        if not container_id:
            response = fmt.format_human_readable_response(
                status="error",
                error_message=f"No running container found for project '{input_data.project_id}'",
                error_details="Start a container first with dotnet_start_container",
            )
            return [TextContent(type="text", text=response)]

        # Get logs from container
        logs = mgr.get_container_logs(
            container_id=container_id,
            tail=input_data.tail,
            since=input_data.since,
        )

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            response = fmt.format_logs_markdown(
                project_id=input_data.project_id,
                logs=logs,
                tail=input_data.tail,
                detail_level=input_data.detail_level,
            )
        else:  # JSON format
            response = fmt.format_json_response(
                status="success",
                data={
                    "project_id": input_data.project_id,
                    "logs": logs,
                    "tail": input_data.tail,
                    "since": input_data.since,
                },
            )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker operation failed",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to get logs",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def kill_process(arguments: dict[str, Any]) -> list[TextContent]:
    """Kill background processes in a container.

    Args:
        arguments: Tool arguments matching KillProcessInput schema

    Returns:
        List with single TextContent containing result
    """
    try:
        # Validate input
        input_data = KillProcessInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Find container by project ID
        container_id = mgr.get_container_by_project_id(input_data.project_id)

        if not container_id:
            response = fmt.format_human_readable_response(
                status="error",
                error_message=f"No running container found for project '{input_data.project_id}'",
                error_details="Start a container first with dotnet_start_container",
            )
            return [TextContent(type="text", text=response)]

        # Build pkill command based on pattern
        if input_data.process_pattern:
            # Kill processes matching specific pattern
            command = ["pkill", "-f", input_data.process_pattern]
            desc = f"processes matching '{input_data.process_pattern}'"
        else:
            # Kill all background dotnet processes (common use case)
            command = ["pkill", "-f", "dotnet"]
            desc = "background dotnet processes"

        # Execute kill command (pkill returns 0 if processes were killed, 1 if none found)
        stdout, stderr, exit_code = mgr.execute_command(
            container_id=container_id,
            command=command,
            timeout=5,
        )

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            if exit_code == 0:
                message = f"Successfully killed {desc}."
            elif exit_code == 1:
                message = f"No {desc} found running."
            else:
                message = f"Kill command completed with exit code {exit_code}.\n\n**Stderr:**\n```\n{stderr}\n```"

            response = (
                f"# Process Management ✓\n\n**Project:** {input_data.project_id}\n\n{message}"
            )
        else:
            response = fmt.format_json_response(
                status="success",
                data={
                    "project_id": input_data.project_id,
                    "exit_code": exit_code,
                    "processes_killed": exit_code == 0,
                    "target": desc,
                    "stderr": stderr if stderr else None,
                },
            )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker operation failed",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to kill processes",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def list_containers(arguments: dict[str, Any]) -> list[TextContent]:
    """List all active containers managed by this MCP server.

    Args:
        arguments: Tool arguments (empty - no parameters required)

    Returns:
        List with single TextContent containing container list or error
    """
    try:
        # Validate input
        input_data = ListContainersInput(**arguments)

        # Initialize components
        mgr, _, fmt = _initialize_components()

        # Get all managed containers
        containers = mgr.list_containers()

        # Format response based on requested format
        if input_data.response_format == ResponseFormat.MARKDOWN:
            if not containers:
                response = "# Active Containers ✓\n\nNo active containers found.\n\nStart a container with `dotnet_start_container`."
            else:
                sections = [
                    "# Active Containers ✓",
                    "",
                    f"Found **{len(containers)}** active container(s):",
                    "",
                ]

                for idx, container in enumerate(containers, 1):
                    sections.append(f"## {idx}. {container.project_id}")
                    sections.append("")
                    sections.append(f"- **Container ID:** `{container.container_id[:12]}`")
                    sections.append(f"- **Name:** {container.name}")
                    sections.append(f"- **Status:** {container.status}")

                    if container.ports:
                        sections.append("- **Port Mappings:**")
                        for container_port, host_port in container.ports.items():
                            sections.append(
                                f"  - Container `{container_port}` → Host `{host_port}` (http://localhost:{host_port})"
                            )
                    else:
                        sections.append("- **Port Mappings:** None")

                    sections.append("")

                response = "\n".join(sections)
        else:
            # JSON format
            container_data = []
            for container in containers:
                container_data.append(
                    {
                        "project_id": container.project_id,
                        "container_id": container.container_id,
                        "name": container.name,
                        "status": container.status,
                        "ports": container.ports if container.ports else {},
                    }
                )

            response = fmt.format_json_response(
                status="success",
                data={
                    "containers": container_data,
                    "count": len(containers),
                },
            )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Invalid input parameters",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Docker operation failed",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        response_format = _get_response_format(arguments)
        error_response = _format_error_response(
            error_message="Failed to list containers",
            error_details=str(e),
            response_format=response_format,
        )
        return [TextContent(type="text", text=error_response)]


async def background_cleanup_task(interval_seconds: int = 300) -> None:
    """Run periodic container cleanup.

    Args:
        interval_seconds: Cleanup interval in seconds (default: 300 = 5 minutes)
    """
    global docker_manager

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            if docker_manager is not None:
                count = docker_manager._lazy_cleanup(idle_timeout_minutes=30)
                if count > 0:
                    print(f"Background cleanup: removed {count} idle container(s)", file=sys.stderr)
        except asyncio.CancelledError:
            print("Background cleanup task cancelled", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Background cleanup error: {e}", file=sys.stderr)
            # Continue running despite errors


def cleanup_all_containers() -> None:
    """Clean up all containers on server shutdown."""
    global docker_manager

    if docker_manager is not None:
        try:
            count = docker_manager.cleanup_all()
            try:
                print(f"Shutdown cleanup: removed {count} container(s)", file=sys.stderr)
            except (BrokenPipeError, OSError):
                pass  # Ignore pipe errors during logging
        except Exception as e:
            # Log the actual error so we can debug
            try:
                print(f"Shutdown cleanup FAILED: {type(e).__name__}: {e}", file=sys.stderr)
                import traceback

                traceback.print_exc(file=sys.stderr)
            except (BrokenPipeError, OSError):
                pass  # If we can't log, continue anyway


def main() -> None:
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server

    async def run_server() -> None:
        """Run server with stdio transport and background cleanup."""
        # Initialize docker_manager first so cleanup can work
        global docker_manager
        if docker_manager is None:
            try:
                docker_manager = DockerContainerManager()
            except Exception as e:
                print(f"Failed to initialize Docker: {e}", file=sys.stderr)

        # Clean up any zombie containers from previous sessions on startup
        try:
            print("Checking for zombie containers from previous sessions...", file=sys.stderr)
        except (BrokenPipeError, OSError):
            pass  # Pipes may already be closed
        cleanup_all_containers()

        # Start background cleanup task
        cleanup_task = asyncio.create_task(background_cleanup_task(interval_seconds=300))

        try:
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )
        finally:
            # Cancel background task
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

            # CRITICAL: Clean up all containers on shutdown
            try:
                print("\nCleaning up containers on shutdown...", file=sys.stderr)
            except (BrokenPipeError, OSError):
                pass
            cleanup_all_containers()

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("\nShutting down server...", file=sys.stderr)
        cleanup_all_containers()
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        cleanup_all_containers()
        sys.exit(1)


if __name__ == "__main__":
    main()
