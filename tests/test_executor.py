"""Tests for DotNetExecutor using mocked Docker operations."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.executor import DotNetExecutor
from src.models import DotNetVersion


class TestDotNetExecutor:
    """Test DotNetExecutor class."""

    @pytest.fixture
    def mock_docker_manager(self) -> MagicMock:
        """Create a mocked Docker manager."""
        return MagicMock()

    @pytest.fixture
    def executor(self, mock_docker_manager: MagicMock) -> DotNetExecutor:
        """Create DotNetExecutor with mocked dependencies."""
        return DotNetExecutor(docker_manager=mock_docker_manager)

    def test_initialization(self, executor: DotNetExecutor) -> None:
        """Test that executor initializes correctly."""
        assert executor is not None

    @pytest.mark.asyncio
    async def test_generate_csproj_minimal(self, executor: DotNetExecutor) -> None:
        """Test generating minimal .csproj file without packages."""
        csproj = await executor.generate_csproj(
            dotnet_version=DotNetVersion.V8,
            packages=[],
        )

        # Should contain target framework
        assert "<TargetFramework>net8.0</TargetFramework>" in csproj
        # Should be executable
        assert "<OutputType>Exe</OutputType>" in csproj
        # Should not contain package references
        assert "<PackageReference" not in csproj

    @pytest.mark.asyncio
    async def test_generate_csproj_with_packages(self, executor: DotNetExecutor) -> None:
        """Test generating .csproj with NuGet packages."""
        csproj = await executor.generate_csproj(
            dotnet_version=DotNetVersion.V8,
            packages=["Newtonsoft.Json", "Dapper@2.0.0"],
        )

        # Should contain target framework
        assert "<TargetFramework>net8.0</TargetFramework>" in csproj
        # Should contain package references (with versions fetched from NuGet)
        assert '<PackageReference Include="Newtonsoft.Json"' in csproj
        assert '<PackageReference Include="Dapper" Version="2.0.0"' in csproj

    @pytest.mark.asyncio
    async def test_generate_csproj_dotnet9(self, executor: DotNetExecutor) -> None:
        """Test generating .csproj for .NET 9."""
        csproj = await executor.generate_csproj(
            dotnet_version=DotNetVersion.V9,
            packages=[],
        )

        assert "<TargetFramework>net9.0</TargetFramework>" in csproj

    @pytest.mark.asyncio
    async def test_generate_csproj_dotnet10(self, executor: DotNetExecutor) -> None:
        """Test generating .csproj for .NET 10."""
        csproj = await executor.generate_csproj(
            dotnet_version=DotNetVersion.V10,
            packages=[],
        )

        assert "<TargetFramework>net10.0</TargetFramework>" in csproj

    def test_parse_package_with_version(self, executor: DotNetExecutor) -> None:
        """Test parsing package string with version."""
        name, version = executor._parse_package("Newtonsoft.Json@13.0.1")
        assert name == "Newtonsoft.Json"
        assert version == "13.0.1"

    def test_parse_package_without_version(self, executor: DotNetExecutor) -> None:
        """Test parsing package string without version."""
        name, version = executor._parse_package("Dapper")
        assert name == "Dapper"
        assert version is None

    @pytest.mark.asyncio
    async def test_get_latest_nuget_version_success(self, executor: DotNetExecutor) -> None:
        """Test fetching latest version from NuGet API."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"versions": ["1.0.0", "2.0.0", "3.0.0-beta", "2.5.0"]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            version = await executor._get_latest_nuget_version("TestPackage")

            # Should return latest stable (not beta)
            assert version == "2.5.0"

    @pytest.mark.asyncio
    async def test_get_latest_nuget_version_package_not_found(
        self, executor: DotNetExecutor
    ) -> None:
        """Test handling package not found on NuGet."""
        mock_response = Mock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            version = await executor._get_latest_nuget_version("NonExistentPackage")

            assert version is None

    @pytest.mark.asyncio
    async def test_get_latest_nuget_version_network_error(self, executor: DotNetExecutor) -> None:
        """Test handling network errors gracefully."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception(
                "Network error"
            )

            version = await executor._get_latest_nuget_version("TestPackage")

            # Should return None on error
            assert version is None

    @pytest.mark.asyncio
    async def test_get_latest_nuget_version_caching(self, executor: DotNetExecutor) -> None:
        """Test that package versions are cached."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"versions": ["1.0.0"]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = mock_client.return_value.__aenter__.return_value.get
            mock_get.return_value = mock_response

            # First call
            version1 = await executor._get_latest_nuget_version("TestPackage")
            # Second call for same package
            version2 = await executor._get_latest_nuget_version("TestPackage")

            assert version1 == "1.0.0"
            assert version2 == "1.0.0"
            # Should only call API once (cached)
            assert mock_get.call_count == 1

    def test_build_project_success(
        self, executor: DotNetExecutor, mock_docker_manager: MagicMock
    ) -> None:
        """Test successful project build."""
        # Mock successful build
        mock_docker_manager.execute_command.return_value = (
            "Build succeeded.\n    0 Warning(s)\n    0 Error(s)",
            "",
            0,
        )

        success, output, errors = executor.build_project(
            container_id="test-container",
            project_path="/workspace",
        )

        assert success is True
        assert "Build succeeded" in output
        assert len(errors) == 0
        mock_docker_manager.execute_command.assert_called_once()

    def test_build_project_failure(
        self, executor: DotNetExecutor, mock_docker_manager: MagicMock
    ) -> None:
        """Test project build with compilation errors."""
        # Mock build failure
        mock_docker_manager.execute_command.return_value = (
            "",
            "Program.cs(5,13): error CS0103: The name 'Console' does not exist",
            1,
        )

        success, output, errors = executor.build_project(
            container_id="test-container",
            project_path="/workspace",
        )

        assert success is False
        assert len(errors) > 0
        assert any("CS0103" in err for err in errors)

    def test_parse_build_errors_cs0246(self, executor: DotNetExecutor) -> None:
        """Test parsing CS0246 (missing type) error."""
        stderr = "Program.cs(3,7): error CS0246: The type or namespace name 'JsonConvert' could not be found"

        errors = executor._parse_build_errors(stderr)

        assert len(errors) == 1
        assert "CS0246" in errors[0]
        assert "JsonConvert" in errors[0]

    def test_parse_build_errors_cs0103(self, executor: DotNetExecutor) -> None:
        """Test parsing CS0103 (name does not exist) error."""
        stderr = "Program.cs(5,13): error CS0103: The name 'Console' does not exist"

        errors = executor._parse_build_errors(stderr)

        assert len(errors) == 1
        assert "CS0103" in errors[0]

    def test_parse_build_errors_multiple(self, executor: DotNetExecutor) -> None:
        """Test parsing multiple build errors."""
        stderr = """
Program.cs(3,7): error CS0246: Type 'Foo' not found
Program.cs(5,13): error CS0103: The name 'bar' does not exist
Program.cs(8,1): error CS1002: ; expected
        """

        errors = executor._parse_build_errors(stderr)

        assert len(errors) == 3

    @pytest.mark.asyncio
    async def test_run_snippet_success(
        self, executor: DotNetExecutor, mock_docker_manager: MagicMock
    ) -> None:
        """Test successful snippet execution."""
        # Mock container creation and execution
        mock_docker_manager.create_container.return_value = "container-123"

        # Mock file operations (no return value needed)
        mock_docker_manager.write_file.return_value = None

        # Mock build and run
        mock_docker_manager.execute_command.side_effect = [
            ("Build succeeded", "", 0),  # Build
            ("Hello World", "", 0),  # Run
        ]

        result = await executor.run_snippet(
            code='Console.WriteLine("Hello World");',
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        assert result["success"] is True
        assert result["stdout"] == "Hello World"
        assert result["stderr"] == ""
        assert result["exit_code"] == 0

        # Verify cleanup was called
        mock_docker_manager.stop_container.assert_called_once_with("container-123")

    @pytest.mark.asyncio
    async def test_run_snippet_build_failure(
        self, executor: DotNetExecutor, mock_docker_manager: MagicMock
    ) -> None:
        """Test snippet execution with build failure."""
        mock_docker_manager.create_container.return_value = "container-123"

        # Mock file operations (no return value needed)
        mock_docker_manager.write_file.return_value = None

        # Mock build failure
        mock_docker_manager.execute_command.side_effect = [
            (
                "",
                "Program.cs(1,1): error CS0103: The name 'InvalidCode' does not exist",
                1,
            ),  # Build fails
        ]

        result = await executor.run_snippet(
            code="InvalidCode;",
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        assert result["success"] is False
        assert "CS0103" in result["stderr"]
        assert len(result["build_errors"]) > 0

        # Verify cleanup was called even on failure
        mock_docker_manager.stop_container.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_snippet_with_packages(
        self, executor: DotNetExecutor, mock_docker_manager: MagicMock
    ) -> None:
        """Test snippet execution with NuGet packages."""
        mock_docker_manager.create_container.return_value = "container-123"

        # Mock file operations (no return value needed)
        mock_docker_manager.write_file.return_value = None

        # Mock build and run
        mock_docker_manager.execute_command.side_effect = [
            ("Build succeeded", "", 0),  # Build
            ("JSON output", "", 0),  # Run
        ]

        result = await executor.run_snippet(
            code='var obj = new { Name = "Test" }; Console.WriteLine(JsonConvert.SerializeObject(obj));',
            dotnet_version=DotNetVersion.V8,
            packages=["Newtonsoft.Json"],
            timeout=30,
        )

        # Verify execution succeeded and packages were handled
        assert result["success"] is True
        assert result["stdout"] == "JSON output"

    @pytest.mark.asyncio
    async def test_run_snippet_timeout(
        self, executor: DotNetExecutor, mock_docker_manager: MagicMock
    ) -> None:
        """Test snippet execution with timeout."""
        from docker.errors import APIError

        mock_docker_manager.create_container.return_value = "container-123"

        # Mock file operations (no return value needed)
        mock_docker_manager.write_file.return_value = None

        # Mock timeout during execution
        mock_docker_manager.execute_command.side_effect = [
            ("Build succeeded", "", 0),  # Build succeeds
            APIError("Timeout"),  # Run times out
        ]

        result = await executor.run_snippet(
            code="while(true) { }",
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=1,
        )

        assert result["success"] is False
        assert "timeout" in result["stderr"].lower() or "Timeout" in result["stderr"]

    @pytest.mark.asyncio
    async def test_run_snippet_cleanup_on_exception(
        self, executor: DotNetExecutor, mock_docker_manager: MagicMock
    ) -> None:
        """Test that cleanup happens even when non-API exception occurs."""
        from docker.errors import APIError

        mock_docker_manager.create_container.return_value = "container-123"

        # Mock file operations (no return value needed)
        mock_docker_manager.write_file.return_value = None

        # Mock API error on build
        mock_docker_manager.execute_command.side_effect = [
            APIError("Docker error"),  # Build fails with API error
        ]

        # APIError is caught and returned as failure result
        result = await executor.run_snippet(
            code='Console.WriteLine("Test");',
            dotnet_version=DotNetVersion.V8,
            packages=[],
            timeout=30,
        )

        assert result["success"] is False

        # Verify cleanup was still called
        mock_docker_manager.stop_container.assert_called_once_with("container-123")

    def test_version_to_tfm_mapping(self, executor: DotNetExecutor) -> None:
        """Test target framework moniker mapping."""
        assert executor._version_to_tfm(DotNetVersion.V8) == "net8.0"
        assert executor._version_to_tfm(DotNetVersion.V9) == "net9.0"
        assert executor._version_to_tfm(DotNetVersion.V10) == "net10.0"
