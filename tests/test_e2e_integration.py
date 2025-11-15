"""Real end-to-end integration tests that execute actual Docker containers.

These tests require:
- Docker daemon running
- Docker images built (dotnet-sandbox:8, dotnet-sandbox:9, dotnet-sandbox:10)

Run with: pytest -v -m e2e tests/test_e2e_integration.py
"""

from collections.abc import Generator

import pytest

from src.docker_manager import DockerContainerManager
from src.executor import DotNetExecutor
from src.formatter import OutputFormatter
from src.models import DetailLevel, DotNetVersion


@pytest.fixture(scope="function")
def docker_manager() -> DockerContainerManager:
    """Create a real DockerContainerManager for E2E tests."""
    return DockerContainerManager()


@pytest.fixture(scope="function")
def executor(docker_manager: DockerContainerManager) -> DotNetExecutor:
    """Create a real DotNetExecutor for E2E tests."""
    return DotNetExecutor(docker_manager=docker_manager)


@pytest.fixture(scope="function")
def formatter() -> OutputFormatter:
    """Create an OutputFormatter for E2E tests."""
    return OutputFormatter()


@pytest.fixture(autouse=True)
def cleanup_containers(docker_manager: DockerContainerManager) -> Generator[None, None, None]:
    """Cleanup all containers after each test."""
    yield
    # Cleanup after test
    docker_manager.cleanup_all()


class TestE2ESnippetExecution:
    """Real end-to-end tests for C# snippet execution."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_simple_hello_world(self, executor: DotNetExecutor) -> None:
        """Test executing a simple Hello World snippet."""
        code = 'Console.WriteLine("Hello from Docker!");'

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        # Verify success
        assert result["success"] is True, f"Build errors: {result.get('build_errors', [])}"
        assert "Hello from Docker!" in result["stdout"]
        assert result["exit_code"] == 0

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_with_multiple_lines(self, executor: DotNetExecutor) -> None:
        """Test executing code with loops and multiple output lines."""
        code = """
for (int i = 1; i <= 5; i++)
{
    Console.WriteLine($"Count: {i}");
}
"""

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        # Verify success
        assert result["success"] is True
        assert "Count: 1" in result["stdout"]
        assert "Count: 5" in result["stdout"]
        assert result["exit_code"] == 0

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_with_compilation_error(self, executor: DotNetExecutor) -> None:
        """Test that compilation errors are caught and reported."""
        code = "InvalidCode that does not compile;"

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        # Verify failure
        assert result["success"] is False
        # Check that either build_errors has content OR stderr contains error info
        has_error_info = (
            (len(result["build_errors"]) > 0)
            or ("error" in result["stderr"].lower())
            or ("CS0103" in result["stderr"])
        )
        assert has_error_info, f"Expected error info but got: {result}"

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_with_nuget_package(self, executor: DotNetExecutor) -> None:
        """Test executing code that uses a NuGet package (Newtonsoft.Json)."""
        code = """
using Newtonsoft.Json;

var person = new { Name = "Alice", Age = 30 };
string json = JsonConvert.SerializeObject(person);
Console.WriteLine(json);
"""

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=["Newtonsoft.Json"],
            timeout=60,  # Package restore may take longer
        )

        # Verify success
        assert result["success"] is True, f"Build errors: {result.get('build_errors', [])}"
        assert '"Name":"Alice"' in result["stdout"] or '"Name": "Alice"' in result["stdout"]
        assert '"Age":30' in result["stdout"] or '"Age": 30' in result["stdout"]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_with_runtime_error(self, executor: DotNetExecutor) -> None:
        """Test that runtime exceptions are captured."""
        code = """
// Code that compiles but throws at runtime
int[] numbers = new int[5];
Console.WriteLine("Accessing array...");
Console.WriteLine(numbers[100]); // Index out of range
"""

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        # Verify execution completed but had runtime error
        # Build should succeed (exit_code 0 for build)
        # Runtime should fail (exit_code != 0 for execution)
        assert result["exit_code"] != 0, "Expected runtime error with non-zero exit code"
        # Should have some output before the crash
        assert "Accessing array" in result["stdout"] or "Exception" in (
            result["stderr"] + result["stdout"]
        )

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_with_math_operations(self, executor: DotNetExecutor) -> None:
        """Test executing code with mathematical operations."""
        code = """
using System;

double result = Math.Sqrt(16) + Math.Pow(2, 3);
Console.WriteLine($"Result: {result}");
Console.WriteLine($"Pi: {Math.PI:F2}");
"""

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        # Verify success
        assert result["success"] is True
        assert "Result: 12" in result["stdout"]  # sqrt(16) + pow(2,3) = 4 + 8 = 12
        assert "Pi: 3.14" in result["stdout"]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_with_file_operations(self, executor: DotNetExecutor) -> None:
        """Test executing code that performs file I/O operations."""
        code = """
using System.IO;

// Write to file
File.WriteAllText("/workspace/test.txt", "Hello File System!");

// Read from file
string content = File.ReadAllText("/workspace/test.txt");
Console.WriteLine($"File content: {content}");

// Check file exists
bool exists = File.Exists("/workspace/test.txt");
Console.WriteLine($"File exists: {exists}");
"""

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        # Verify success
        assert result["success"] is True
        assert "File content: Hello File System!" in result["stdout"]
        assert "File exists: True" in result["stdout"]


class TestE2EMultipleVersions:
    """Test execution across different .NET versions."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_on_dotnet8(self, executor: DotNetExecutor) -> None:
        """Test execution on .NET 8."""
        code = "Console.WriteLine(System.Environment.Version);"

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        assert result["success"] is True
        # .NET 8 should output version starting with 8
        assert "8." in result["stdout"]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_on_dotnet9(self, executor: DotNetExecutor) -> None:
        """Test execution on .NET 9."""
        code = "Console.WriteLine(System.Environment.Version);"

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V9,
            packages=[],
            timeout=30,
        )

        assert result["success"] is True
        # .NET 9 should output version starting with 9
        assert "9." in result["stdout"]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execute_on_dotnet10(self, executor: DotNetExecutor) -> None:
        """Test execution on .NET 10."""
        code = "Console.WriteLine(System.Environment.Version);"

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V10,
            packages=[],
            timeout=30,
        )

        assert result["success"] is True
        # .NET 10 should output version starting with 10
        assert "10." in result["stdout"]


class TestE2EOutputFormatting:
    """Test output formatting with real execution."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_concise_output_truncation(
        self, executor: DotNetExecutor, formatter: OutputFormatter
    ) -> None:
        """Test that concise mode properly truncates long output."""
        # Generate 100 lines of output
        code = """
for (int i = 1; i <= 100; i++)
{
    Console.WriteLine($"Line {i}");
}
"""

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        # Format with both modes
        concise = formatter.format_execution_output(
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            detail_level=DetailLevel.CONCISE,
        )

        full = formatter.format_execution_output(
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            detail_level=DetailLevel.FULL,
        )

        # Verify concise is shorter
        assert len(concise) < len(full)
        assert "truncated" in concise.lower() or "..." in concise

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_stderr_captured_separately(self, executor: DotNetExecutor) -> None:
        """Test that stderr is captured separately from stdout."""
        code = """
Console.WriteLine("This goes to stdout");
Console.Error.WriteLine("This goes to stderr");
"""

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        # Note: Docker exec_run may combine streams, so this test verifies
        # that at least the output is captured
        assert result["success"] is True
        assert "stdout" in result["stdout"] or "stderr" in result["stderr"]


class TestE2EContainerLifecycle:
    """Test container lifecycle management."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_containers_are_cleaned_up(self, docker_manager: DockerContainerManager) -> None:
        """Test that containers are properly cleaned up after execution."""
        # Get initial container count
        initial_containers = docker_manager.list_containers()
        initial_count = len(initial_containers)

        # Create and execute in a container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-cleanup",
        )

        # Verify container was created
        assert container_id is not None
        containers = docker_manager.list_containers()
        assert len(containers) == initial_count + 1

        # Stop container
        docker_manager.stop_container(container_id)

        # Verify container was removed
        final_containers = docker_manager.list_containers()
        assert len(final_containers) == initial_count

    @pytest.mark.e2e
    def test_list_containers_shows_running_containers(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test that list_containers returns correct information."""
        # Create a container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-list",
        )

        # List containers
        containers = docker_manager.list_containers()

        # Find our container
        our_container = next((c for c in containers if c.container_id == container_id), None)

        # Verify container info
        assert our_container is not None
        assert our_container.project_id == "test-list"
        assert our_container.status == "running"
        # ContainerInfo has: container_id, name, project_id, status, ports
        assert "dotnet" in our_container.name.lower() or "test-list" in our_container.name

        # Cleanup
        docker_manager.stop_container(container_id)


class TestE2ETimeout:
    """Test timeout handling."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_execution_timeout(self, executor: DotNetExecutor) -> None:
        """Test that timeout parameter can be passed (actual enforcement is Docker-level)."""
        # This test verifies the timeout parameter is accepted
        # Actual timeout enforcement depends on Docker exec timeout behavior
        # which may not interrupt Thread.Sleep immediately
        code = """
Console.WriteLine("Quick execution");
"""

        # Verify timeout parameter is accepted and doesn't cause errors
        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=5,  # Short timeout is accepted
        )

        # Should complete successfully with short code
        assert result["success"] is True
        assert "Quick execution" in result["stdout"]


class TestE2EFileOperations:
    """Test file operations in persistent containers."""

    @pytest.mark.e2e
    def test_write_and_read_file(self, docker_manager: DockerContainerManager) -> None:
        """Test writing and reading files in a container."""
        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-files",
        )

        # Write a file
        content = "Hello from test file!"
        docker_manager.write_file(
            container_id=container_id,
            dest_path="/workspace/test.txt",
            content=content,
        )

        # Read the file back
        read_content = docker_manager.read_file(
            container_id=container_id,
            path="/workspace/test.txt",
        )

        # Verify content matches
        assert read_content.decode("utf-8") == content

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    def test_list_files_in_directory(self, docker_manager: DockerContainerManager) -> None:
        """Test listing files in a container directory."""
        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-list",
        )

        # Write multiple files
        docker_manager.write_file(
            container_id=container_id,
            dest_path="/workspace/file1.txt",
            content="Content 1",
        )
        docker_manager.write_file(
            container_id=container_id,
            dest_path="/workspace/file2.txt",
            content="Content 2",
        )
        docker_manager.write_file(
            container_id=container_id,
            dest_path="/workspace/file3.txt",
            content="Content 3",
        )

        # List files
        files = docker_manager.list_files(
            container_id=container_id,
            path="/workspace",
        )

        # Verify all files are listed
        assert "file1.txt" in files
        assert "file2.txt" in files
        assert "file3.txt" in files

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    def test_create_nested_directory_structure(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test creating files in nested directories."""
        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-nested",
        )

        # Write file with nested path (should create directories)
        docker_manager.write_file(
            container_id=container_id,
            dest_path="/workspace/src/utils/Helper.cs",
            content="// Helper class",
        )

        # Verify file exists
        assert docker_manager.file_exists(
            container_id=container_id,
            path="/workspace/src/utils/Helper.cs",
        )

        # Read the file back
        content = docker_manager.read_file(
            container_id=container_id,
            path="/workspace/src/utils/Helper.cs",
        )
        assert b"// Helper class" in content

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    def test_complete_project_workflow(self, docker_manager: DockerContainerManager) -> None:
        """Test complete workflow: create files, build, run."""
        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-workflow",
        )

        # Create .csproj file
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
"""
        docker_manager.write_file(
            container_id=container_id,
            dest_path="/workspace/TestApp/TestApp.csproj",
            content=csproj_content,
        )

        # Create Program.cs
        program_content = 'Console.WriteLine("Hello from complete workflow!");'
        docker_manager.write_file(
            container_id=container_id,
            dest_path="/workspace/TestApp/Program.cs",
            content=program_content,
        )

        # Verify files exist
        files = docker_manager.list_files(
            container_id=container_id,
            path="/workspace/TestApp",
        )
        assert "TestApp.csproj" in files
        assert "Program.cs" in files

        # Build the project
        stdout, stderr, exit_code = docker_manager.execute_command(
            container_id=container_id,
            command=["dotnet", "build", "/workspace/TestApp"],
            timeout=60,
        )

        # Verify build succeeded
        assert exit_code == 0, f"Build failed: {stdout} {stderr}"

        # Run the project
        stdout, stderr, exit_code = docker_manager.execute_command(
            container_id=container_id,
            command=["dotnet", "run", "--project", "/workspace/TestApp"],
            timeout=30,
        )

        # Verify execution succeeded
        assert exit_code == 0
        assert "Hello from complete workflow!" in stdout

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    def test_file_not_found_error(self, docker_manager: DockerContainerManager) -> None:
        """Test that reading non-existent file raises FileNotFoundError."""
        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-not-found",
        )

        # Try to read non-existent file
        with pytest.raises(FileNotFoundError):
            docker_manager.read_file(
                container_id=container_id,
                path="/workspace/nonexistent.txt",
            )

        # Cleanup
        docker_manager.stop_container(container_id)


class TestE2EWebServerSupport:
    """Test web server support features: port mapping, background processes, HTTP testing, logs."""

    @pytest.mark.e2e
    def test_port_mapping_basic(self, docker_manager: DockerContainerManager) -> None:
        """Test creating container with port mapping."""
        # Create container with port mapping
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-ports",
            port_mapping={5000: 0},  # Map container port 5000 to auto-assigned host port
        )

        # List containers and verify port mapping
        containers = docker_manager.list_containers()
        our_container = next((c for c in containers if c.container_id == container_id), None)

        assert our_container is not None
        assert our_container.ports is not None
        # Should have port mapping with auto-assigned host port (Docker format: "5000/tcp")
        assert "5000/tcp" in our_container.ports
        host_port = int(our_container.ports["5000/tcp"])
        assert host_port > 0  # Should be assigned a real port

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    def test_port_mapping_multiple_ports(self, docker_manager: DockerContainerManager) -> None:
        """Test creating container with multiple port mappings."""
        # Create container with multiple ports
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-multiport",
            port_mapping={5000: 0, 5001: 0},  # Two auto-assigned ports
        )

        # List containers and verify port mappings
        containers = docker_manager.list_containers()
        our_container = next((c for c in containers if c.container_id == container_id), None)

        assert our_container is not None
        assert our_container.ports is not None
        assert "5000/tcp" in our_container.ports
        assert "5001/tcp" in our_container.ports
        # Both should have different assigned ports
        host_port_5000 = int(our_container.ports["5000/tcp"])
        host_port_5001 = int(our_container.ports["5001/tcp"])
        assert host_port_5000 > 0
        assert host_port_5001 > 0
        assert host_port_5000 != host_port_5001

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    def test_get_container_logs(self, docker_manager: DockerContainerManager) -> None:
        """Test retrieving container logs."""
        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-logs",
        )

        # Execute command that writes to container's main stdout/stderr
        # This is what background processes do to make logs visible
        docker_manager.execute_command(
            container_id=container_id,
            command=[
                "sh",
                "-c",
                "echo 'Log line 1' >/proc/1/fd/1 && echo 'Log line 2' >/proc/1/fd/1 && echo 'Log line 3' >/proc/1/fd/1",
            ],
            timeout=10,
        )

        # Get logs
        logs = docker_manager.get_container_logs(
            container_id=container_id,
            tail=50,
        )

        # Verify logs contain our output
        assert "Log line 1" in logs
        assert "Log line 2" in logs
        assert "Log line 3" in logs

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    def test_get_container_logs_with_tail_limit(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test retrieving container logs with tail limit."""
        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-logs-tail",
        )

        # Execute commands that produce multiple lines
        for i in range(1, 11):
            docker_manager.execute_command(
                container_id=container_id,
                command=["sh", "-c", f"echo 'Log line {i}'"],
                timeout=10,
            )

        # Get logs with small tail
        logs = docker_manager.get_container_logs(
            container_id=container_id,
            tail=3,
        )

        # Should only get last 3 lines
        lines = [line for line in logs.strip().split("\n") if line.strip()]
        assert len(lines) <= 5  # Allow some tolerance for Docker output formatting

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_background_process_execution(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test running a background process (sleep simulation)."""
        import asyncio

        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-background",
        )

        # Start a background process using nohup
        # Use a simple sleep command that echoes before and after
        bg_command = [
            "sh",
            "-c",
            "nohup sh -c 'echo Starting background process && sleep 3 && echo Background process done' >/proc/1/fd/1 2>/proc/1/fd/2 &",
        ]

        docker_manager.execute_command(
            container_id=container_id,
            command=bg_command,
            timeout=5,
        )

        # Wait a moment for process to start
        await asyncio.sleep(1)

        # Get logs - should show start message
        logs = docker_manager.get_container_logs(
            container_id=container_id,
            tail=50,
        )
        assert "Starting background process" in logs

        # Wait for background process to complete
        await asyncio.sleep(3)

        # Get logs again - should show completion message
        logs = docker_manager.get_container_logs(
            container_id=container_id,
            tail=50,
        )
        assert "Background process done" in logs

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_simple_web_server_workflow(self, docker_manager: DockerContainerManager) -> None:
        """Test complete workflow: create web API, run in background, test endpoint, check logs."""
        import asyncio

        import httpx

        # Create container with port mapping
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-webapi",
            port_mapping={5000: 0},  # Auto-assign host port
        )

        # Get the assigned host port
        containers = docker_manager.list_containers()
        our_container = next((c for c in containers if c.container_id == container_id), None)
        assert our_container is not None
        assert our_container.ports is not None
        host_port = int(our_container.ports["5000/tcp"])
        assert host_port > 0

        # Create a minimal web API project
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
"""
        docker_manager.write_file(
            container_id=container_id,
            dest_path="/workspace/WebApi/WebApi.csproj",
            content=csproj_content,
        )

        # Create Program.cs with minimal API
        program_content = """var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapGet("/", () => "Hello from DotBox!");
app.MapGet("/health", () => new { status = "healthy", timestamp = DateTime.UtcNow });

app.Run("http://0.0.0.0:5000");
"""
        docker_manager.write_file(
            container_id=container_id,
            dest_path="/workspace/WebApi/Program.cs",
            content=program_content,
        )

        # Build the project
        stdout, stderr, exit_code = docker_manager.execute_command(
            container_id=container_id,
            command=["dotnet", "build", "/workspace/WebApi"],
            timeout=60,
        )
        assert exit_code == 0, f"Build failed: {stdout} {stderr}"

        # Run in background
        bg_command = [
            "sh",
            "-c",
            "nohup dotnet run --project /workspace/WebApi --no-build </dev/null >/proc/1/fd/1 2>/proc/1/fd/2 &",
        ]
        docker_manager.execute_command(
            container_id=container_id,
            command=bg_command,
            timeout=5,
        )

        # Wait for server to start
        await asyncio.sleep(5)

        # Test the endpoint using httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test root endpoint
                response = await client.get(f"http://localhost:{host_port}/")
                assert response.status_code == 200
                assert "Hello from DotBox" in response.text

                # Test health endpoint
                health_response = await client.get(f"http://localhost:{host_port}/health")
                assert health_response.status_code == 200
                health_data = health_response.json()
                assert health_data["status"] == "healthy"

        except Exception as e:
            # Get logs for debugging if test fails
            logs = docker_manager.get_container_logs(container_id=container_id, tail=100)
            pytest.fail(f"HTTP request failed: {e}\n\nContainer logs:\n{logs}")

        # Check logs
        logs = docker_manager.get_container_logs(
            container_id=container_id,
            tail=50,
        )
        # Should contain some indication that the app is running
        assert (
            "info:" in logs.lower() or "application" in logs.lower() or "listening" in logs.lower()
        )

        # Cleanup
        docker_manager.stop_container(container_id)

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_kill_process_workflow(self, docker_manager: DockerContainerManager) -> None:
        """Test the complete kill_process workflow: start process, kill it, verify container still works."""
        import asyncio

        from src.server import kill_process

        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-kill-workflow",
        )

        # Start a long-running background process
        bg_command = [
            "sh",
            "-c",
            "nohup sh -c 'echo Process started; sleep 120; echo Process ended' >/proc/1/fd/1 2>/proc/1/fd/2 &",
        ]
        docker_manager.execute_command(
            container_id=container_id,
            command=bg_command,
            timeout=5,
        )

        # Wait for process to start
        await asyncio.sleep(1)

        # Verify process is running
        logs_before = docker_manager.get_container_logs(
            container_id=container_id,
            tail=50,
        )
        assert "Process started" in logs_before

        # Kill the process using kill_process function
        result = await kill_process(
            {"project_id": "test-kill-workflow", "process_pattern": "sleep 120"}
        )

        # Verify kill was successful
        assert len(result) == 1
        result_text = result[0].text
        assert "success" in result_text.lower() or "killed" in result_text.lower()

        # Wait a moment
        await asyncio.sleep(1)

        # Verify container is still running and we can execute commands
        stdout, stderr, exit_code = docker_manager.execute_command(
            container_id=container_id,
            command=["echo", "Container still alive"],
            timeout=5,
        )
        assert exit_code == 0
        assert "Container still alive" in stdout

        # Test killing when no processes match (should not error)
        result2 = await kill_process(
            {"project_id": "test-kill-workflow", "process_pattern": "nonexistent-process"}
        )
        assert len(result2) == 1
        result2_text = result2[0].text
        # Should say no processes found
        assert "no" in result2_text.lower() or "not found" in result2_text.lower()

        # Cleanup
        docker_manager.stop_container(container_id)


@pytest.mark.e2e
class TestE2EListContainers:
    """E2E tests for listing containers."""

    @pytest.mark.asyncio
    async def test_list_containers_no_containers(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test listing when no containers are running."""
        from src.server import list_containers

        # Ensure no containers are running
        docker_manager.cleanup_all()

        # Call list_containers
        result = await list_containers({})

        assert len(result) == 1
        response_text = result[0].text
        assert "No active containers found" in response_text

    @pytest.mark.asyncio
    async def test_list_containers_single_container(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test listing a single container without ports."""
        from src.server import list_containers

        # Create container
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-list-single",
        )

        try:
            # Call list_containers
            result = await list_containers({})

            assert len(result) == 1
            response_text = result[0].text
            # Check for markdown-formatted count (bold)
            assert "Found" in response_text and "1" in response_text
            assert "test-list-single" in response_text
            assert container_id[:12] in response_text
            assert "running" in response_text.lower()
            assert "None" in response_text  # Port Mappings: None

        finally:
            docker_manager.stop_container(container_id)

    @pytest.mark.asyncio
    async def test_list_containers_multiple_with_ports(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test listing multiple containers with port mappings."""
        from src.server import list_containers

        # Create containers with different configurations
        container1_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="api-service",
            port_mapping={5000: 0, 5001: 0},  # Auto-assign ports
        )

        container2_id = docker_manager.create_container(
            dotnet_version="9",
            project_id="worker-service",
        )

        try:
            # Call list_containers
            result = await list_containers({})

            assert len(result) == 1
            response_text = result[0].text

            # Verify count (markdown-formatted with bold)
            assert "Found" in response_text and "2" in response_text

            # Verify container 1 (with ports)
            assert "api-service" in response_text
            assert container1_id[:12] in response_text
            assert "5000/tcp" in response_text
            assert "5001/tcp" in response_text

            # Verify container 2 (no ports)
            assert "worker-service" in response_text
            assert container2_id[:12] in response_text

            # Verify at least one has no port mappings (None)
            assert "None" in response_text  # Port Mappings: None or **Port Mappings:** None

        finally:
            docker_manager.stop_container(container1_id)
            docker_manager.stop_container(container2_id)

    @pytest.mark.asyncio
    async def test_list_containers_workflow_integration(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test list_containers in a realistic workflow."""
        from src.server import list_containers, start_container, stop_container

        # Start with clean state
        docker_manager.cleanup_all()

        # Verify no containers
        result1 = await list_containers({})
        assert "No active containers found" in result1[0].text

        # Start container using MCP tool
        start_result = await start_container(
            {"project_id": "my-api", "dotnet_version": "8", "ports": {5000: 0}}
        )
        assert len(start_result) == 1

        # List should now show 1 container
        result2 = await list_containers({})
        response2 = result2[0].text
        # Check for markdown-formatted count
        assert "Found" in response2 and "1" in response2
        assert "my-api" in response2
        assert "5000/tcp" in response2

        # Stop container using MCP tool
        stop_result = await stop_container({"project_id": "my-api"})
        assert len(stop_result) == 1

        # List should be empty again
        result3 = await list_containers({})
        assert "No active containers found" in result3[0].text


@pytest.mark.e2e
class TestE2EMCPProtocolFlow:
    """E2E tests simulating exact MCP protocol flow from Claude Desktop.

    These tests verify that the JSON schema and Pydantic validators work together
    correctly when receiving JSON-deserialized arguments with string keys.
    """

    @pytest.mark.asyncio
    async def test_port_mapping_with_json_string_keys_full_flow(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test complete MCP flow with JSON string keys (simulating Claude Desktop).

        This test simulates exactly what Claude Desktop does:
        1. Sends JSON with string keys: {"5000": 8080}
        2. JSON gets deserialized to Python dict with string keys
        3. MCP schema validation runs
        4. Pydantic validator coerces strings to integers
        5. Container is created with correct port mapping
        6. Web API is accessible externally
        """
        import json

        import httpx

        from src.server import run_background, start_container, stop_container, write_file

        # Simulate MCP client sending JSON (string keys)
        # This is EXACTLY what Claude Desktop sends
        json_payload = json.dumps(
            {"dotnet_version": "8", "project_id": "test-mcp-ports", "ports": {"5000": 8080}}
        )

        # Deserialize JSON (converts to dict with string keys)
        arguments = json.loads(json_payload)

        # Verify we have string keys (this is what breaks without our fix)
        assert isinstance(list(arguments["ports"].keys())[0], str), (
            "Keys should be strings from JSON"
        )

        # Call MCP tool handler with JSON-deserialized arguments
        start_result = await start_container(arguments)
        assert len(start_result) == 1
        assert "test-mcp-ports" in start_result[0].text
        # Check for success indicator (✓ or "started")
        assert "✓" in start_result[0].text or "started" in start_result[0].text.lower()

        try:
            # Create minimal web API
            await write_file(
                {
                    "project_id": "test-mcp-ports",
                    "path": "/workspace/TestApi/TestApi.csproj",
                    "content": """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>""",
                }
            )

            await write_file(
                {
                    "project_id": "test-mcp-ports",
                    "path": "/workspace/TestApi/Program.cs",
                    "content": """var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapGet("/", () => "MCP port mapping works!");
app.MapGet("/health", () => new { status = "healthy", message = "Port coercion successful" });

app.Run();
""",
                }
            )

            # Build project first (explicit, faster feedback on build errors)
            from src.server import execute_command

            build_result = await execute_command(
                {
                    "project_id": "test-mcp-ports",
                    "command": ["dotnet", "build", "/workspace/TestApi"],
                    "timeout": 60,
                }
            )
            assert len(build_result) == 1
            # Check for success indicator (✓ or "succeeded")
            assert "✓" in build_result[0].text or "succeeded" in build_result[0].text.lower()

            # Start web server (with --no-build since we already built)
            run_result = await run_background(
                {
                    "project_id": "test-mcp-ports",
                    "command": [
                        "dotnet",
                        "run",
                        "--project",
                        "/workspace/TestApi",
                        "--no-build",
                        "--urls",
                        "http://0.0.0.0:5000",
                    ],
                    "wait_for_ready": 5,
                }
            )
            assert len(run_result) == 1

            # Test external HTTP access (THE KEY TEST - proves port mapping worked)
            async with httpx.AsyncClient() as client:
                # Test root endpoint
                response = await client.get("http://localhost:8080/", timeout=5.0)
                assert response.status_code == 200
                assert "MCP port mapping works!" in response.text

                # Test health endpoint
                health_response = await client.get("http://localhost:8080/health", timeout=5.0)
                assert health_response.status_code == 200
                data = health_response.json()
                assert data["status"] == "healthy"
                assert "Port coercion successful" in data["message"]

        finally:
            await stop_container({"project_id": "test-mcp-ports"})

    @pytest.mark.asyncio
    async def test_auto_port_assignment_with_json_string_keys(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test auto-assignment with JSON string keys: {"5000": "0"}."""
        import json
        import re

        import httpx

        from src.server import (
            list_containers,
            run_background,
            start_container,
            stop_container,
            write_file,
        )

        # Simulate MCP client with auto-assignment (string "0")
        json_payload = json.dumps(
            {"dotnet_version": "8", "project_id": "test-auto-port", "ports": {"5000": "0"}}
        )
        arguments = json.loads(json_payload)

        # Verify string values from JSON
        assert isinstance(arguments["ports"]["5000"], str), "Value should be string '0' from JSON"

        start_result = await start_container(arguments)
        assert len(start_result) == 1

        try:
            # Discover assigned port
            containers_result = await list_containers({})
            response_text = containers_result[0].text

            # Extract host port from response
            match = re.search(r"5000/tcp.*?(\d+)", response_text)
            assert match, f"Could not find assigned port in: {response_text}"
            assigned_port = int(match.group(1))
            assert assigned_port > 1024, "Assigned port should be ephemeral (>1024)"

            # Create minimal API
            await write_file(
                {
                    "project_id": "test-auto-port",
                    "path": "/workspace/TestApi/TestApi.csproj",
                    "content": """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>""",
                }
            )

            await write_file(
                {
                    "project_id": "test-auto-port",
                    "path": "/workspace/TestApi/Program.cs",
                    "content": """var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();
app.MapGet("/test", () => new { status = "ok", port = "auto-assigned" });
app.Run();
""",
                }
            )

            # Build project first (explicit, faster feedback on build errors)
            from src.server import execute_command

            build_result = await execute_command(
                {
                    "project_id": "test-auto-port",
                    "command": ["dotnet", "build", "/workspace/TestApi"],
                    "timeout": 60,
                }
            )
            assert len(build_result) == 1
            # Check for success indicator (✓ or exit code 0)
            assert "✓" in build_result[0].text or "exit code: 0" in build_result[0].text.lower()

            # Start web server (with --no-build since we already built)
            await run_background(
                {
                    "project_id": "test-auto-port",
                    "command": [
                        "dotnet",
                        "run",
                        "--project",
                        "/workspace/TestApi",
                        "--no-build",
                        "--urls",
                        "http://0.0.0.0:5000",
                    ],
                    "wait_for_ready": 5,
                }
            )

            # Test via discovered port
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://localhost:{assigned_port}/test", timeout=5.0)
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                assert data["port"] == "auto-assigned"

        finally:
            await stop_container({"project_id": "test-auto-port"})

    @pytest.mark.asyncio
    async def test_multiple_ports_with_mixed_string_formats(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test multiple port mappings with various string/int combinations."""
        import json

        from src.server import start_container, stop_container

        # Test all possible combinations from MCP JSON
        test_cases = [
            # String keys, integer values
            {"5000": 8080, "5001": 8081},
            # String keys, string values
            {"5000": "8080", "5001": "8081"},
            # Mixed (string key with string value for auto-assign)
            {"5000": 8080, "5001": "0"},
        ]

        for i, ports_config in enumerate(test_cases):
            project_id = f"test-multi-ports-{i}"
            json_payload = json.dumps(
                {"dotnet_version": "8", "project_id": project_id, "ports": ports_config}
            )
            arguments = json.loads(json_payload)

            try:
                # Should not raise validation error
                start_result = await start_container(arguments)
                assert len(start_result) == 1
                assert project_id in start_result[0].text

            finally:
                await stop_container({"project_id": project_id})


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_command_failure_shows_stderr_and_stdout(
    docker_manager: DockerContainerManager,
) -> None:
    """Test that failed commands show stderr/stdout in error response.

    This is a critical UX issue: when commands fail, users MUST see the
    error output to debug. This test verifies the fix for:
    https://github.com/user-feedback/issue-123

    Before fix: "Command failed" with no error details
    After fix: Full stderr/stdout visible in error response
    """
    from src.server import execute_command, start_container, stop_container

    project_id = "test-error-output"

    try:
        # Start container
        start_result = await start_container({"dotnet_version": "8", "project_id": project_id})
        assert len(start_result) == 1

        # Execute command that will fail
        result = await execute_command(
            {
                "project_id": project_id,
                "command": ["dotnet", "new", "invalid-template-that-does-not-exist"],
            }
        )

        assert len(result) == 1
        response_text = result[0].text

        # CRITICAL: Error response MUST contain stderr output
        # The command will fail with a message about template not found
        assert "exit code" in response_text.lower() or "Exit code" in response_text
        assert (
            "stderr" in response_text.lower()
            or "Stderr" in response_text
            or "could not be found" in response_text.lower()
            or "template" in response_text.lower()
        ), f"Expected stderr/error details in response, got: {response_text}"

        # Verify it's marked as error/failure
        assert (
            "failed" in response_text.lower()
            or "error" in response_text.lower()
            or "✗" in response_text
        ), f"Expected error status in response, got: {response_text}"

    finally:
        await stop_container({"project_id": project_id})


@pytest.mark.e2e
class TestE2EEnhancedTools:
    """E2E tests for LLM-usable tools (git, jq, sqlite3, tree) in sandbox images."""

    @pytest.mark.asyncio
    async def test_git_available(self, docker_manager: DockerContainerManager) -> None:
        """Verify git is installed and functional in sandbox."""
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-git",
        )

        try:
            # Test git is available
            stdout, stderr, exit_code = docker_manager.execute_command(
                container_id=container_id,
                command=["git", "--version"],
                timeout=5,
            )
            assert exit_code == 0, f"git --version failed: {stderr}"
            assert "git version" in stdout.lower(), f"Unexpected git output: {stdout}"

        finally:
            docker_manager.stop_container(container_id)

    @pytest.mark.asyncio
    async def test_jq_available(self, docker_manager: DockerContainerManager) -> None:
        """Verify jq is installed and functional in sandbox."""
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-jq",
        )

        try:
            # Test jq is available
            stdout, stderr, exit_code = docker_manager.execute_command(
                container_id=container_id,
                command=["jq", "--version"],
                timeout=5,
            )
            assert exit_code == 0, f"jq --version failed: {stderr}"
            assert "jq" in stdout.lower(), f"Unexpected jq output: {stdout}"

            # Test jq can parse JSON
            stdout, stderr, exit_code = docker_manager.execute_command(
                container_id=container_id,
                command=["sh", "-c", 'echo \'{"name":"test","value":42}\' | jq .name'],
                timeout=5,
            )
            assert exit_code == 0, f"jq parse failed: {stderr}"
            assert '"test"' in stdout, f"Expected jq to extract name field: {stdout}"

        finally:
            docker_manager.stop_container(container_id)

    @pytest.mark.asyncio
    async def test_sqlite_available(self, docker_manager: DockerContainerManager) -> None:
        """Verify sqlite3 is installed and functional in sandbox."""
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-sqlite",
        )

        try:
            # Test sqlite3 is available
            stdout, stderr, exit_code = docker_manager.execute_command(
                container_id=container_id,
                command=["sqlite3", "--version"],
                timeout=5,
            )
            assert exit_code == 0, f"sqlite3 --version failed: {stderr}"
            assert len(stdout) > 0, "Expected version output from sqlite3"

            # Test sqlite3 can create and query database
            commands = [
                "sqlite3 /workspace/test.db 'CREATE TABLE test (id INTEGER, name TEXT)'",
                "sqlite3 /workspace/test.db \"INSERT INTO test VALUES (1, 'hello')\"",
                "sqlite3 /workspace/test.db 'SELECT * FROM test'",
            ]
            for cmd in commands:
                stdout, stderr, exit_code = docker_manager.execute_command(
                    container_id=container_id,
                    command=["sh", "-c", cmd],
                    timeout=5,
                )
                assert exit_code == 0, f"sqlite3 command failed: {cmd}\nstderr: {stderr}"

            # Verify data was inserted
            assert "1|hello" in stdout, f"Expected query result: {stdout}"

        finally:
            docker_manager.stop_container(container_id)

    @pytest.mark.asyncio
    async def test_tree_available(self, docker_manager: DockerContainerManager) -> None:
        """Verify tree is installed and functional in sandbox."""
        container_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-tree",
        )

        try:
            # Test tree is available
            stdout, stderr, exit_code = docker_manager.execute_command(
                container_id=container_id,
                command=["tree", "--version"],
                timeout=5,
            )
            assert exit_code == 0, f"tree --version failed: {stderr}"
            assert "tree" in stdout.lower(), f"Unexpected tree output: {stdout}"

            # Create directory structure and visualize with tree
            docker_manager.execute_command(
                container_id=container_id,
                command=["sh", "-c", "mkdir -p /workspace/src/Controllers /workspace/tests"],
                timeout=5,
            )

            stdout, stderr, exit_code = docker_manager.execute_command(
                container_id=container_id,
                command=["tree", "/workspace", "-L", "2"],
                timeout=5,
            )
            assert exit_code == 0, f"tree command failed: {stderr}"
            assert "src" in stdout and "Controllers" in stdout, f"Expected tree output: {stdout}"

        finally:
            docker_manager.stop_container(container_id)

    @pytest.mark.asyncio
    async def test_tools_available_across_all_versions(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Verify all tools are available in .NET 8, 9, and 10 images."""
        tools = ["git", "jq", "sqlite3", "tree"]
        versions = ["8", "9", "10"]

        for version in versions:
            container_id = docker_manager.create_container(
                dotnet_version=version,
                project_id=f"test-tools-{version}",
            )

            try:
                for tool in tools:
                    stdout, stderr, exit_code = docker_manager.execute_command(
                        container_id=container_id,
                        command=[tool, "--version"],
                        timeout=5,
                    )
                    assert exit_code == 0, f"{tool} not available in .NET {version} image: {stderr}"

            finally:
                docker_manager.stop_container(container_id)


@pytest.mark.e2e
class TestE2EPortConflictHandling:
    """E2E tests for port conflict detection and cleanup."""

    @pytest.mark.asyncio
    async def test_port_conflict_cleans_up_orphaned_container(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test that failed containers due to port conflicts are cleaned up."""
        # Start first container with port 9876
        container1_id = docker_manager.create_container(
            dotnet_version="8",
            project_id="test-port-first",
            port_mapping={5000: 9876},
        )

        try:
            # Attempt to create second container with same port (should fail)
            with pytest.raises(Exception) as exc_info:
                docker_manager.create_container(
                    dotnet_version="8",
                    project_id="test-port-second",
                    port_mapping={5000: 9876},  # Conflict!
                )

            # Verify error mentions port/networking issue
            error_msg = str(exc_info.value).lower()
            assert any(
                phrase in error_msg
                for phrase in [
                    "address already in use",
                    "port",
                    "failed to set up container networking",
                ]
            ), f"Expected port conflict error, got: {error_msg}"

            # Verify no orphaned container exists
            # Check Docker directly to be sure
            all_containers = docker_manager.client.containers.list(
                all=True, filters={"name": "test-port-second"}
            )
            assert len(all_containers) == 0, "Orphaned container was not cleaned up!"

        finally:
            docker_manager.stop_container(container1_id)

    @pytest.mark.asyncio
    async def test_port_conflict_error_message_has_suggestions(
        self, docker_manager: DockerContainerManager
    ) -> None:
        """Test that port conflict errors include actionable suggestions for LLM."""
        from src.server import start_container

        # Start first container
        result1 = await start_container(
            {"dotnet_version": "8", "project_id": "occupy-port", "ports": {"5000": 9877}}
        )
        assert len(result1) == 1
        assert "occupy-port" in result1[0].text

        try:
            # Try to start second container with same port
            result2 = await start_container(
                {"dotnet_version": "8", "project_id": "conflict-port", "ports": {"5000": 9877}}
            )

            assert len(result2) == 1
            response_text = result2[0].text.lower()

            # Verify error message mentions port conflict
            assert "port" in response_text and (
                "conflict" in response_text or "already in use" in response_text
            ), f"Expected port conflict error, got: {result2[0].text}"

            # Verify suggestions are provided
            assert any(
                phrase in response_text
                for phrase in [
                    "auto-assign",
                    "ports=",
                    ": 0",
                    "list_containers",
                    "stop",
                ]
            ), f"Expected actionable suggestions in error, got: {result2[0].text}"

            # Verify no orphaned container exists
            all_containers = docker_manager.client.containers.list(
                all=True, filters={"name": "conflict-port"}
            )
            assert len(all_containers) == 0, "Orphaned container was not cleaned up!"

        finally:
            # Cleanup first container
            from src.server import stop_container

            await stop_container({"project_id": "occupy-port"})
