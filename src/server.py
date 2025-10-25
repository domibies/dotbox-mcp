"""FastMCP server for .NET code execution in Docker containers."""

import sys
from typing import Any

from docker.errors import DockerException
from mcp.server import Server
from mcp.types import TextContent, Tool
from pydantic import ValidationError

from src.docker_manager import DockerContainerManager
from src.executor import DotNetExecutor
from src.formatter import OutputFormatter
from src.models import DetailLevel, ExecuteSnippetInput

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


@server.list_tools()  # type: ignore[misc, no-untyped-call]
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="dotnet_execute_snippet",
            description="""Execute a C# code snippet in an isolated Docker container.

This tool creates a temporary .NET project, builds it, executes the code, and returns the output.
The container is automatically cleaned up after execution.

Features:
- Support for .NET 8, 9, and 10 RC2
- Automatic NuGet package installation
- Compilation error parsing with helpful suggestions
- Configurable output verbosity (concise/full)
- Resource limits and timeouts for safety

Common use cases:
- Quick C# code testing
- Testing NuGet packages
- Comparing behavior across .NET versions
- Prototyping algorithms

Example code formats:
- Top-level statements: Console.WriteLine("Hello");
- Full programs: class Program { static void Main() { ... } }
- Using directives: using System.Linq; var result = Enumerable.Range(1, 10).Sum();
            """,
            inputSchema=ExecuteSnippetInput.model_json_schema(),
        )
    ]


@server.call_tool()  # type: ignore[misc]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle MCP tool calls."""
    if name == "dotnet_execute_snippet":
        return await execute_snippet(arguments)

    raise ValueError(f"Unknown tool: {name}")


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
        result = exec_instance.run_snippet(
            code=input_data.code,
            dotnet_version=input_data.dotnet_version,
            packages=input_data.packages,
            timeout=30,
        )

        # Format response in human-readable format
        if result["success"]:
            # Success case
            output = result["stdout"] if result["stdout"] else result["stderr"]

            response = fmt.format_human_readable_response(
                status="success",
                output=output,
                exit_code=result["exit_code"],
                dotnet_version=input_data.dotnet_version.value,
            )

        else:
            # Build or execution error
            error_output = fmt.format_execution_output(
                stdout=result["stdout"],
                stderr=result["stderr"],
                exit_code=result["exit_code"],
                detail_level=DetailLevel.FULL,  # Always show full errors
            )

            response = fmt.format_human_readable_response(
                status="error",
                error_message="Code execution failed"
                if not result["build_errors"]
                else "Build failed",
                error_details=error_output,
                build_errors=result["build_errors"],
                dotnet_version=input_data.dotnet_version.value,
            )

        return [TextContent(type="text", text=response)]

    except ValidationError as e:
        # Input validation error
        error_response = OutputFormatter().format_human_readable_response(
            status="error",
            error_message="Invalid input parameters",
            error_details=str(e),
        )
        return [TextContent(type="text", text=error_response)]

    except DockerException as e:
        # Docker not available
        error_response = OutputFormatter().format_human_readable_response(
            status="error",
            error_message="Docker is not available",
            error_details=str(e),
            suggestions=[
                "Ensure Docker is installed and running",
                "Check Docker socket permissions",
                "Verify Docker images are built (run docker/build-images.sh)",
            ],
        )
        return [TextContent(type="text", text=error_response)]

    except Exception as e:
        # Unexpected error
        error_response = OutputFormatter().format_human_readable_response(
            status="error",
            error_message="An unexpected error occurred",
            error_details=str(e),
        )
        return [TextContent(type="text", text=error_response)]


def main() -> None:
    """Run the MCP server."""
    import asyncio

    from mcp.server.stdio import stdio_server

    async def run_server() -> None:
        """Run server with stdio transport."""
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("\nShutting down server...", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
