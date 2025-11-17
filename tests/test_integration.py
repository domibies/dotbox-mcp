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
    async def test_execute_snippet_end_to_end_success(self, mock_docker_client: MagicMock) -> None:
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
    async def test_execute_snippet_with_build_error(self, mock_docker_client: MagicMock) -> None:
        """Test snippet execution with compilation error."""
        # Mock file operations succeeding, then build failure
        mock_empty = MagicMock()
        mock_empty.output = b""
        mock_empty.exit_code = 0

        mock_build = MagicMock()
        mock_build.output = b"Program.cs(1,1): error CS0103: The name 'InvalidCode' does not exist"
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
    async def test_execute_snippet_with_packages(self, mock_docker_client: MagicMock) -> None:
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
    async def test_output_truncation_integration(self, mock_docker_client: MagicMock) -> None:
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
    async def test_container_cleanup_integration(self, mock_docker_client: MagicMock) -> None:
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
            mock_result,
            mock_result,  # Version 1
            mock_result,
            mock_result,  # Version 2
            mock_result,
            mock_result,  # Version 3
        ]

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            from src.docker_manager import DockerContainerManager
            from src.executor import DotNetExecutor

            docker_manager = DockerContainerManager()
            # Mock _ensure_image_exists to avoid image checks in unit tests
            docker_manager._ensure_image_exists = MagicMock()  # type: ignore
            executor = DotNetExecutor(docker_manager=docker_manager)

            # Test each version
            for version in [DotNetVersion.V8, DotNetVersion.V9, DotNetVersion.V10]:
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

            # Call handler with JSON format
            result = await list_containers({"response_format": "json"})

            # Verify response
            assert len(result) == 1
            response_text = result[0].text

            # Parse JSON response
            parsed = json.loads(response_text)
            assert parsed["status"] == "success"
            assert parsed["data"]["count"] == 2

            containers = parsed["data"]["containers"]
            assert len(containers) == 2

            # Check first container
            assert containers[0]["project_id"] == "my-api"
            assert containers[0]["container_id"] == "abc123def456"
            assert "5000/tcp" in containers[0]["ports"]
            assert containers[0]["ports"]["5000/tcp"] == "8080"

            # Check second container
            assert containers[1]["project_id"] == "test-project"
            assert containers[1]["container_id"] == "xyz789abc123"
            assert containers[1]["ports"] == {}  # No ports

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_name,input_args",
        [
            ("execute_snippet", {"code": 'Console.WriteLine("test");', "dotnet_version": "8"}),
            ("start_container", {"project_id": "test-proj", "dotnet_version": "8"}),
            (
                "test_endpoint",
                {"project_id": "test-proj", "url": "http://localhost:5000/", "method": "GET"},
            ),
            ("get_logs", {"project_id": "test-proj"}),
            ("run_background", {"project_id": "test-proj", "command": ["dotnet", "run"]}),
            ("stop_container", {"project_id": "test-proj"}),
            (
                "write_file",
                {"project_id": "test-proj", "path": "/workspace/test.cs", "content": "test"},
            ),
            ("read_file", {"project_id": "test-proj", "path": "/workspace/Program.cs"}),
            ("list_files", {"project_id": "test-proj", "path": "/workspace"}),
            ("execute_command", {"project_id": "test-proj", "command": ["echo", "test"]}),
            ("kill_process", {"project_id": "test-proj"}),
            ("list_containers", {}),
        ],
    )
    async def test_dual_format_matrix(
        self, tool_name: str, input_args: dict, mock_docker_client: MagicMock
    ) -> None:
        """Matrix test: all tools support both Markdown and JSON formats."""
        # Mock all Docker operations for success path
        mock_result = MagicMock()
        mock_result.output = b"test output"
        mock_result.exit_code = 0

        mock_container = mock_docker_client.containers.run.return_value
        mock_container.id = "test123"
        mock_container.name = "test-container"
        mock_container.status = "running"
        mock_container.labels = {"managed-by": "dotbox-mcp", "project-id": "test-proj"}
        mock_container.attrs = {"NetworkSettings": {"Ports": {"5000/tcp": [{"HostPort": "8080"}]}}}

        # Setup get to return the same container
        mock_docker_client.containers.get.return_value = mock_container
        mock_container.put_archive.return_value = True
        mock_container.exec_run.return_value = mock_result
        mock_container.logs.return_value = b"test logs"

        # For list operations - return container for test-proj
        mock_docker_client.containers.list.return_value = [mock_container]

        # Mock HTTP response for test_endpoint
        with patch("httpx.AsyncClient") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_response.elapsed.total_seconds.return_value = 0.1
            mock_httpx.return_value.__aenter__.return_value.request.return_value = mock_response

            with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
                # Reset global state
                import src.server

                src.server.docker_manager = None
                src.server.executor = None
                src.server.formatter = None

                # Import tool handlers
                from src.server import (
                    execute_command,
                    execute_snippet,
                    get_logs,
                    kill_process,
                    list_containers,
                    list_files,
                    read_file,
                    run_background,
                    start_container,
                    stop_container,
                    test_endpoint,
                    write_file,
                )

                tool_map = {
                    "execute_snippet": execute_snippet,
                    "start_container": start_container,
                    "test_endpoint": test_endpoint,
                    "get_logs": get_logs,
                    "run_background": run_background,
                    "stop_container": stop_container,
                    "write_file": write_file,
                    "read_file": read_file,
                    "list_files": list_files,
                    "execute_command": execute_command,
                    "kill_process": kill_process,
                    "list_containers": list_containers,
                }

                handler = tool_map[tool_name]

                # Test Markdown format
                markdown_input = {**input_args, "response_format": "markdown"}
                markdown_result = await handler(markdown_input)
                markdown_text = markdown_result[0].text

                # Validate Markdown characteristics
                assert "✓" in markdown_text or "✗" in markdown_text, (
                    f"{tool_name}: Missing status symbol in Markdown"
                )
                assert markdown_text.startswith("#"), f"{tool_name}: Missing header in Markdown"

                # Test JSON format
                json_input = {**input_args, "response_format": "json"}
                json_result = await handler(json_input)
                json_text = json_result[0].text

                # Validate JSON characteristics
                parsed = json.loads(json_text)
                assert "status" in parsed, f"{tool_name}: Missing status in JSON"
                assert parsed["status"] in [
                    "success",
                    "error",
                ], f"{tool_name}: Invalid status value"

    async def test_read_file_json_structure(self, mock_docker_client: MagicMock) -> None:
        """Regression test: read_file returns proper JSON structure with all required fields."""
        # Setup mock container
        mock_container = MagicMock()
        mock_container.id = "test123"
        mock_container.name = "test-container"
        mock_container.status = "running"
        mock_container.labels = {"managed-by": "dotbox-mcp", "project-id": "test-proj"}

        # Mock containers.list to return our container (for get_container_by_project_id)
        mock_docker_client.containers.list.return_value = [mock_container]

        # Mock containers.get to return our container (for file operations)
        mock_docker_client.containers.get.return_value = mock_container

        # Mock file read - must return base64-encoded content
        # exec_run returns an object with .output and .exit_code attributes
        import base64

        content = b"Hello, World!"
        base64_content = base64.b64encode(content)

        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.output = base64_content
        mock_container.exec_run.return_value = mock_result

        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            # Reset global state
            import src.server

            src.server.docker_manager = None
            src.server.executor = None
            src.server.formatter = None

            # Import tool handler
            from src.server import read_file

            # Execute with JSON format
            result = await read_file(
                {"project_id": "test-proj", "path": "/workspace/test.cs", "response_format": "json"}
            )

            # Parse and validate JSON structure
            parsed = json.loads(result[0].text)
            assert parsed["status"] == "success", "Status should be success"
            assert "data" in parsed, "Missing data field in JSON response"
            assert parsed["data"]["project_id"] == "test-proj", "Missing or incorrect project_id"
            assert parsed["data"]["path"] == "/workspace/test.cs", "Missing or incorrect path"
            assert parsed["data"]["content"] == "Hello, World!", "Missing or incorrect content"
