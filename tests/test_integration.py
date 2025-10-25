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
        # Mock successful build and run
        mock_result = MagicMock()
        mock_result.output = b"Hello World\n"
        mock_result.exit_code = 0
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
        # Mock build failure
        mock_build = MagicMock()
        mock_build.output = (
            b"Program.cs(1,1): error CS0103: The name 'InvalidCode' does not exist"
        )
        mock_build.exit_code = 1
        mock_docker_client.containers.get.return_value.exec_run.return_value = (
            mock_build
        )

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
        # Mock successful build and run
        mock_result = MagicMock()
        mock_result.output = b'{"Name":"Test"}\n'
        mock_result.exit_code = 0
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

        mock_result = MagicMock()
        mock_result.output = output.encode()
        mock_result.exit_code = 0
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
        mock_result = MagicMock()
        mock_result.output = b"Output"
        mock_result.exit_code = 0
        mock_container = mock_docker_client.containers.run.return_value
        mock_docker_client.containers.get.return_value.exec_run.side_effect = [
            mock_result,
            mock_result,
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
        self, mock_docker_client: MagicMock
    ) -> None:
        """Test execution with different .NET versions."""
        mock_result = MagicMock()
        mock_result.output = b"Success"
        mock_result.exit_code = 0
        mock_docker_client.containers.get.return_value.exec_run.side_effect = [
            mock_result,
            mock_result,
        ] * 3

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            from src.docker_manager import DockerContainerManager
            from src.executor import DotNetExecutor

            docker_manager = DockerContainerManager()
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
