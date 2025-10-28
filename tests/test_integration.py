"""Integration tests for MCP server with all components."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.models import DetailLevel, DotNetVersion, ExecuteSnippetInput


@pytest.fixture
def mock_docker_client() -> MagicMock:
    """Create a fully mocked Docker client."""
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "test-container-123"

    mock_client.containers.run.return_value = mock_container
    mock_client.containers.get.return_value = mock_container
    mock_client.containers.list.return_value = []
    mock_client.ping.return_value = True

    return mock_client


class TestMCPIntegration:
    """Integration tests for MCP server tool."""

    @pytest.mark.asyncio
    async def test_execute_snippet_end_to_end_success(
        self, mock_docker_client: MagicMock
    ) -> None:
        """Test successful snippet execution through MCP tool."""
        # Mock successful file operations, build, and run
        mock_empty = MagicMock()
        mock_empty.output = b""
        mock_empty.exit_code = 0

        mock_result = MagicMock()
        mock_result.output = b"Hello World\n"
        mock_result.exit_code = 0

        # Mock put_archive for both directories and file writes
        mock_docker_client.containers.get.return_value.put_archive.return_value = True

        # Mock exec_run for build and run only (directories use put_archive now)
        mock_docker_client.containers.get.return_value.exec_run.side_effect = [
            mock_result,  # Build
            mock_result,  # Run
        ]

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            from src.docker_manager import DockerContainerManager
            from src.executor import DotNetExecutor
            from src.formatter import OutputFormatter

            # Simulate full workflow
            docker_manager = DockerContainerManager()
            executor = DotNetExecutor(docker_manager=docker_manager)
            formatter = OutputFormatter()

            # Execute snippet
            result = await executor.run_snippet(
                code='Console.WriteLine("Hello World");',
                dotnet_version=DotNetVersion.V8,
                packages=[],
                timeout=30,
            )

            # Format output
            formatted = formatter.format_execution_output(
                stdout=result["stdout"],
                stderr=result["stderr"],
                exit_code=result["exit_code"],
                detail_level=DetailLevel.FULL,
            )

            # Verify success
            assert result["success"] is True
            assert "Hello World" in formatted

    @pytest.mark.asyncio
    async def test_execute_snippet_with_build_error(
        self, mock_docker_client: MagicMock
    ) -> None:
        """Test snippet execution with compilation error."""
        # Mock file operations succeeding, then build failure
        mock_empty = MagicMock()
        mock_empty.output = b""
        mock_empty.exit_code = 0

        mock_build = MagicMock()
        mock_build.output = (
            b"Program.cs(1,1): error CS0103: The name 'InvalidCode' does not exist"
        )
        mock_build.exit_code = 1

        # Mock put_archive for both directories and file writes
        mock_docker_client.containers.get.return_value.put_archive.return_value = True

        # Mock exec_run for build failure only (directories use put_archive now)
        mock_docker_client.containers.get.return_value.exec_run.side_effect = [
            mock_build,  # Build fails
        ]

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            from src.docker_manager import DockerContainerManager
            from src.executor import DotNetExecutor

            docker_manager = DockerContainerManager()
            executor = DotNetExecutor(docker_manager=docker_manager)

            result = await executor.run_snippet(
                code="InvalidCode;",
                dotnet_version=DotNetVersion.V8,
                packages=[],
                timeout=30,
            )

            # Verify failure and error parsing
            assert result["success"] is False
            assert len(result["build_errors"]) > 0
            assert "CS0103" in result["build_errors"][0]

    @pytest.mark.asyncio
    async def test_execute_snippet_with_packages(
        self, mock_docker_client: MagicMock
    ) -> None:
        """Test snippet execution with NuGet packages."""
        # Mock successful file operations, build, and run
        mock_empty = MagicMock()
        mock_empty.output = b""
        mock_empty.exit_code = 0

        mock_result = MagicMock()
        mock_result.output = b'{"Name":"Test"}\n'
        mock_result.exit_code = 0

        # Mock put_archive for both directories and file writes
        mock_docker_client.containers.get.return_value.put_archive.return_value = True

        # Mock exec_run for build and run only (directories use put_archive now)
        mock_docker_client.containers.get.return_value.exec_run.side_effect = [
            mock_result,  # Build
            mock_result,  # Run
        ]

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            from src.docker_manager import DockerContainerManager
            from src.executor import DotNetExecutor

            docker_manager = DockerContainerManager()
            executor = DotNetExecutor(docker_manager=docker_manager)

            result = await executor.run_snippet(
                code='using Newtonsoft.Json; var obj = new { Name = "Test" }; Console.WriteLine(JsonConvert.SerializeObject(obj));',
                dotnet_version=DotNetVersion.V8,
                packages=["Newtonsoft.Json"],
                timeout=30,
            )

            # Verify packages were handled
            assert result["success"] is True
            assert "Test" in result["stdout"]

    def test_pydantic_validation_integration(self) -> None:
        """Test that Pydantic models validate input correctly."""
        # Valid input
        valid_input = ExecuteSnippetInput(
            code='Console.WriteLine("Test");',
            dotnet_version=DotNetVersion.V8,
            packages=[],
            detail_level=DetailLevel.CONCISE,
        )
        assert valid_input.code == 'Console.WriteLine("Test");'
        assert valid_input.dotnet_version == DotNetVersion.V8

        # Invalid input - empty code
        with pytest.raises(ValueError):
            ExecuteSnippetInput(
                code="",
                dotnet_version=DotNetVersion.V8,
                packages=[],
                detail_level=DetailLevel.CONCISE,
            )

        # Invalid input - too many packages
        with pytest.raises(ValueError):
            ExecuteSnippetInput(
                code='Console.WriteLine("Test");',
                dotnet_version=DotNetVersion.V8,
                packages=["Package" + str(i) for i in range(25)],  # Max is 20
                detail_level=DetailLevel.CONCISE,
            )

    @pytest.mark.asyncio
    async def test_output_truncation_integration(
        self, mock_docker_client: MagicMock
    ) -> None:
        """Test that concise mode truncates output properly."""
        # Generate 100 lines of output
        output_lines = [f"Line {i}" for i in range(100)]
        output = "\n".join(output_lines)

        mock_empty = MagicMock()
        mock_empty.output = b""
        mock_empty.exit_code = 0

        mock_result = MagicMock()
        mock_result.output = output.encode()
        mock_result.exit_code = 0

        # Mock put_archive for both directories and file writes
        mock_docker_client.containers.get.return_value.put_archive.return_value = True

        # Mock exec_run for build and run only (directories use put_archive now)
        mock_docker_client.containers.get.return_value.exec_run.side_effect = [
            mock_result,  # Build
            mock_result,  # Run
        ]

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            from src.docker_manager import DockerContainerManager
            from src.executor import DotNetExecutor
            from src.formatter import OutputFormatter

            docker_manager = DockerContainerManager()
            executor = DotNetExecutor(docker_manager=docker_manager)
            formatter = OutputFormatter()

            result = await executor.run_snippet(
                code='for (int i = 0; i < 100; i++) Console.WriteLine($"Line {i}");',
                dotnet_version=DotNetVersion.V8,
                packages=[],
                timeout=30,
            )

            # Format with concise mode
            formatted_concise = formatter.format_execution_output(
                stdout=result["stdout"],
                stderr=result["stderr"],
                exit_code=result["exit_code"],
                detail_level=DetailLevel.CONCISE,
            )

            # Format with full mode
            formatted_full = formatter.format_execution_output(
                stdout=result["stdout"],
                stderr=result["stderr"],
                exit_code=result["exit_code"],
                detail_level=DetailLevel.FULL,
            )

            # Concise should be shorter than full
            assert len(formatted_concise) < len(formatted_full)

    @pytest.mark.asyncio
    async def test_container_cleanup_integration(
        self, mock_docker_client: MagicMock
    ) -> None:
        """Test that containers are cleaned up after execution."""
        mock_empty = MagicMock()
        mock_empty.output = b""
        mock_empty.exit_code = 0

        mock_result = MagicMock()
        mock_result.output = b"Output"
        mock_result.exit_code = 0

        mock_container = mock_docker_client.containers.run.return_value
        # Mock put_archive for both directories and file writes
        mock_docker_client.containers.get.return_value.put_archive.return_value = True

        # Mock exec_run for build and run only (directories use put_archive now)
        mock_docker_client.containers.get.return_value.exec_run.side_effect = [
            mock_result,  # Build
            mock_result,  # Run
        ]

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            from src.docker_manager import DockerContainerManager
            from src.executor import DotNetExecutor

            docker_manager = DockerContainerManager()
            executor = DotNetExecutor(docker_manager=docker_manager)

            await executor.run_snippet(
                code='Console.WriteLine("Test");',
                dotnet_version=DotNetVersion.V8,
                packages=[],
                timeout=30,
            )

            # Verify container was stopped and removed
            mock_container.stop.assert_called_once()
            mock_container.remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_different_dotnet_versions(
        self, mock_docker_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test execution with different .NET versions."""
        # Set local registry mode for tests
        monkeypatch.setenv("DOTBOX_SANDBOX_REGISTRY", "local")
        mock_empty = MagicMock()
        mock_empty.output = b""
        mock_empty.exit_code = 0

        mock_result = MagicMock()
        mock_result.output = b"Success"
        mock_result.exit_code = 0

        # Mock put_archive for both directories and file writes
        mock_docker_client.containers.get.return_value.put_archive.return_value = True

        # Each version needs: build, run = 2 calls (directories use put_archive now)
        # Testing 3 versions = 6 calls total
        mock_docker_client.containers.get.return_value.exec_run.side_effect = [
            mock_result, mock_result,  # Version 1
            mock_result, mock_result,  # Version 2
            mock_result, mock_result,  # Version 3
        ]

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            from src.docker_manager import DockerContainerManager
            from src.executor import DotNetExecutor

            docker_manager = DockerContainerManager()
            # Mock _ensure_image_exists to avoid image checks in unit tests
            docker_manager._ensure_image_exists = MagicMock()  # type: ignore
            executor = DotNetExecutor(docker_manager=docker_manager)

            # Test each version
            for version in [DotNetVersion.V8, DotNetVersion.V9, DotNetVersion.V10_RC2]:
                result = await executor.run_snippet(
                    code='Console.WriteLine("Test");',
                    dotnet_version=version,
                    packages=[],
                    timeout=30,
                )
                assert result["success"] is True

                # Verify correct image was used
                call_args = mock_docker_client.containers.run.call_args
                image_name = call_args[1]["image"]
                assert f"dotnet-sandbox:{version.value}" == image_name

    def test_json_response_format(self, mock_docker_client: MagicMock) -> None:
        """Test that JSON responses are properly formatted."""
        from src.formatter import OutputFormatter

        formatter = OutputFormatter()

        # Success response
        success_response = formatter.format_json_response(
            status="success",
            data={"output": "Hello World", "exit_code": 0},
            metadata={"execution_time_ms": 1234, "dotnet_version": "8.0.0"},
        )

        parsed = json.loads(success_response)
        assert parsed["status"] == "success"
        assert "output" in parsed["data"]
        assert "execution_time_ms" in parsed["metadata"]

        # Error response
        error_response = formatter.format_json_response(
            status="error",
            error={
                "type": "BuildError",
                "message": "Compilation failed",
                "suggestions": ["Add using directive"],
            },
            metadata={"execution_time_ms": 500},
        )

        parsed_error = json.loads(error_response)
        assert parsed_error["status"] == "error"
        assert parsed_error["error"]["type"] == "BuildError"
        assert len(parsed_error["error"]["suggestions"]) > 0

    @pytest.mark.asyncio
    async def test_list_containers_handler_no_containers(
        self, mock_docker_client: MagicMock
    ) -> None:
        """Test list_containers handler when no containers are running."""
        # Mock empty container list
        mock_docker_client.containers.list.return_value = []

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            # Reset global state to force re-initialization with mocked client
            import src.server
            src.server.docker_manager = None
            src.server.executor = None
            src.server.formatter = None

            from src.server import list_containers

            # Call handler
            result = await list_containers({})

            # Verify response
            assert len(result) == 1
            response_text = result[0].text
            assert "No active containers found" in response_text
            assert "dotnet_start_container" in response_text

    @pytest.mark.asyncio
    async def test_list_containers_handler_with_containers(
        self, mock_docker_client: MagicMock
    ) -> None:
        """Test list_containers handler with active containers."""
        # Mock container data
        mock_container1 = MagicMock()
        mock_container1.id = "abc123def456"
        mock_container1.name = "dotnet8-proj-x7k2p9"
        mock_container1.status = "running"
        mock_container1.labels = {
            "managed-by": "dotbox-mcp",
            "project-id": "my-api",
        }
        mock_container1.attrs = {
            "NetworkSettings": {
                "Ports": {
                    "5000/tcp": [{"HostPort": "8080"}],
                    "5001/tcp": [{"HostPort": "8081"}],
                }
            }
        }

        mock_container2 = MagicMock()
        mock_container2.id = "xyz789abc123"
        mock_container2.name = "dotnet9-proj-a1b2c3"
        mock_container2.status = "running"
        mock_container2.labels = {
            "managed-by": "dotbox-mcp",
            "project-id": "test-project",
        }
        mock_container2.attrs = {"NetworkSettings": {"Ports": {}}}

        mock_docker_client.containers.list.return_value = [
            mock_container1,
            mock_container2,
        ]

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            # Reset global state to force re-initialization with mocked client
            import src.server
            src.server.docker_manager = None
            src.server.executor = None
            src.server.formatter = None

            from src.server import list_containers

            # Call handler
            result = await list_containers({})

            # Verify response
            assert len(result) == 1
            response_text = result[0].text
            assert "Found 2 active container(s)" in response_text
            assert "my-api" in response_text
            assert "test-project" in response_text
            assert "abc123def456"[:12] in response_text
            assert "xyz789abc123"[:12] in response_text
            assert "5000/tcp" in response_text
            assert "8080" in response_text
            assert "Port Mappings: None" in response_text  # Second container has no ports
