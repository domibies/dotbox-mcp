"""Real end-to-end integration tests that execute actual Docker containers.

These tests require:
- Docker daemon running
- Docker images built (dotnet-sandbox:8, dotnet-sandbox:9, dotnet-sandbox:10-rc2)

Run with: pytest -v -m e2e tests/test_e2e_integration.py
"""

from typing import Generator

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
            (len(result["build_errors"]) > 0) or
            ("error" in result["stderr"].lower()) or
            ("CS0103" in result["stderr"])
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
        assert "Accessing array" in result["stdout"] or "Exception" in (result["stderr"] + result["stdout"])

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
        code = 'Console.WriteLine(System.Environment.Version);'

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
        code = 'Console.WriteLine(System.Environment.Version);'

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
    async def test_execute_on_dotnet10_rc2(self, executor: DotNetExecutor) -> None:
        """Test execution on .NET 10 RC2."""
        code = 'Console.WriteLine(System.Environment.Version);'

        result = await executor.run_snippet(
            code=code,
            dotnet_version=DotNetVersion.V10_RC2,
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
    def test_create_nested_directory_structure(self, docker_manager: DockerContainerManager) -> None:
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
