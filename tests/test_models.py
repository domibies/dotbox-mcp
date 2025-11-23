"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from src.models import (
    DetailLevel,
    DotNetVersion,
    ExecuteCommandInput,
    ExecuteSnippetInput,
    GetLogsInput,
    KillProcessInput,
    ListContainersInput,
    ListFilesInput,
    ReadFileInput,
    RunBackgroundInput,
    StartContainerInput,
    StopContainerInput,
    TestEndpointInput,
    WriteFileInput,
)


class TestDotNetVersion:
    """Test DotNetVersion enum."""

    def test_version_values(self) -> None:
        """Test that enum has correct version values."""
        assert DotNetVersion.V8.value == "8"
        assert DotNetVersion.V9.value == "9"
        assert DotNetVersion.V10.value == "10"

    def test_can_create_from_string(self) -> None:
        """Test creating enum from string."""
        assert DotNetVersion("8") == DotNetVersion.V8
        assert DotNetVersion("9") == DotNetVersion.V9
        assert DotNetVersion("10") == DotNetVersion.V10


class TestDetailLevel:
    """Test DetailLevel enum."""

    def test_detail_level_values(self) -> None:
        """Test that enum has correct values."""
        assert DetailLevel.CONCISE.value == "concise"
        assert DetailLevel.FULL.value == "full"

    def test_can_create_from_string(self) -> None:
        """Test creating enum from string."""
        assert DetailLevel("concise") == DetailLevel.CONCISE
        assert DetailLevel("full") == DetailLevel.FULL


class TestExecuteSnippetInput:
    """Test ExecuteSnippetInput model."""

    def test_valid_minimal_input(self) -> None:
        """Test creating model with minimal valid input."""
        input_data = ExecuteSnippetInput(code='Console.WriteLine("Hello");')

        assert input_data.code == 'Console.WriteLine("Hello");'
        assert input_data.dotnet_version == DotNetVersion.V8  # Default
        assert input_data.packages == []  # Default
        assert input_data.detail_level == DetailLevel.CONCISE  # Default

    def test_valid_full_input(self) -> None:
        """Test creating model with all fields."""
        input_data = ExecuteSnippetInput(
            code='var json = JsonConvert.SerializeObject(new { foo = "bar" });',
            dotnet_version=DotNetVersion.V9,
            packages=["Newtonsoft.Json"],
            detail_level=DetailLevel.FULL,
        )

        assert "JsonConvert" in input_data.code
        assert input_data.dotnet_version == DotNetVersion.V9
        assert input_data.packages == ["Newtonsoft.Json"]
        assert input_data.detail_level == DetailLevel.FULL

    def test_strips_whitespace_from_strings(self) -> None:
        """Test that string fields are automatically stripped."""
        input_data = ExecuteSnippetInput(code="  Console.WriteLine();  ")

        assert input_data.code == "Console.WriteLine();"

    def test_empty_code_rejected(self) -> None:
        """Test that empty code is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteSnippetInput(code="")

        errors = exc_info.value.errors()
        assert any("code" in str(e["loc"]) for e in errors)

    def test_whitespace_only_code_rejected(self) -> None:
        """Test that whitespace-only code is rejected after stripping."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteSnippetInput(code="   ")

        errors = exc_info.value.errors()
        assert any("code" in str(e["loc"]) for e in errors)

    def test_code_too_long_rejected(self) -> None:
        """Test that code exceeding max length is rejected."""
        long_code = "x" * 50001  # Max is 50000

        with pytest.raises(ValidationError) as exc_info:
            ExecuteSnippetInput(code=long_code)

        errors = exc_info.value.errors()
        assert any("code" in str(e["loc"]) for e in errors)

    def test_max_20_packages(self) -> None:
        """Test that max 20 packages are allowed."""
        valid_packages = [f"Package{i}" for i in range(20)]
        input_data = ExecuteSnippetInput(code="Console.WriteLine();", packages=valid_packages)

        assert len(input_data.packages) == 20

    def test_more_than_20_packages_rejected(self) -> None:
        """Test that more than 20 packages is rejected."""
        too_many_packages = [f"Package{i}" for i in range(21)]

        with pytest.raises(ValidationError) as exc_info:
            ExecuteSnippetInput(code="Console.WriteLine();", packages=too_many_packages)

        errors = exc_info.value.errors()
        assert any("packages" in str(e["loc"]) for e in errors)

    def test_invalid_package_name_rejected(self) -> None:
        """Test that invalid package names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteSnippetInput(code="Console.WriteLine();", packages=[""])

        errors = exc_info.value.errors()
        assert any("packages" in str(e["loc"]) for e in errors)

    def test_package_name_too_long_rejected(self) -> None:
        """Test that package names over 100 chars are rejected."""
        long_package_name = "P" * 101

        with pytest.raises(ValidationError) as exc_info:
            ExecuteSnippetInput(code="Console.WriteLine();", packages=[long_package_name])

        errors = exc_info.value.errors()
        assert any("packages" in str(e["loc"]) for e in errors)

    def test_multiple_valid_packages(self) -> None:
        """Test that multiple valid packages work."""
        input_data = ExecuteSnippetInput(
            code="test",
            packages=["Newtonsoft.Json", "Dapper", "FluentValidation"],
        )

        assert len(input_data.packages) == 3
        assert "Dapper" in input_data.packages

    def test_dotnet_version_from_string(self) -> None:
        """Test that dotnet_version accepts string values (for MCP JSON)."""
        # Test each version as string (simulating MCP tool call from JSON)
        for version_str in ["8", "9", "10"]:
            input_data = ExecuteSnippetInput(
                code="Console.WriteLine();",
                dotnet_version=version_str,  # type: ignore[arg-type]
            )
            # Should accept string and store it
            assert input_data.dotnet_version.value == version_str

    def test_dotnet_version_from_integer(self) -> None:
        """Test that dotnet_version accepts integer values (Claude Desktop bug)."""
        # Claude Desktop sometimes passes integers instead of strings
        input_data_8 = ExecuteSnippetInput(
            code="Console.WriteLine();",
            dotnet_version=8,  # type: ignore[arg-type]
        )
        assert input_data_8.dotnet_version == DotNetVersion.V8

        input_data_9 = ExecuteSnippetInput(
            code="Console.WriteLine();",
            dotnet_version=9,  # type: ignore[arg-type]
        )
        assert input_data_9.dotnet_version == DotNetVersion.V9

    def test_detail_level_from_string(self) -> None:
        """Test that detail_level accepts string values (for MCP JSON)."""
        # Test each level as string (simulating MCP tool call from JSON)
        for level_str in ["concise", "full"]:
            input_data = ExecuteSnippetInput(
                code="Console.WriteLine();",
                detail_level=level_str,  # type: ignore[arg-type]
            )
            # Should accept string and store it
            assert input_data.detail_level.value == level_str

    def test_json_schema_accepts_both_types(self) -> None:
        """Test that JSON schema explicitly allows both int and string for dotnet_version."""
        schema = ExecuteSnippetInput.model_json_schema()

        # Get the dotnet_version property schema
        version_schema = schema["properties"]["dotnet_version"]

        # Should have anyOf with both integer and string types
        assert "anyOf" in version_schema
        assert len(version_schema["anyOf"]) == 2

        # Check integer variant
        int_variant = next((v for v in version_schema["anyOf"] if v["type"] == "integer"), None)
        assert int_variant is not None
        assert set(int_variant["enum"]) == {8, 9, 10}

        # Check string variant
        str_variant = next((v for v in version_schema["anyOf"] if v["type"] == "string"), None)
        assert str_variant is not None
        assert set(str_variant["enum"]) == {"8", "9", "10"}


class TestStartContainerInput:
    """Test StartContainerInput model."""

    def test_valid_minimal_input_no_project_id(self) -> None:
        """Test creating model with no project_id (should auto-generate)."""
        input_data = StartContainerInput()

        # Should have auto-generated project_id with format: dotnet{version}-proj-{6chars}
        assert input_data.project_id is not None
        assert input_data.project_id.startswith("dotnet8-proj-")  # Default is .NET 8
        assert len(input_data.project_id) == len("dotnet8-proj-abcdef")
        assert input_data.dotnet_version == DotNetVersion.V8  # Default

    def test_valid_minimal_input_with_project_id(self) -> None:
        """Test creating model with explicit project_id."""
        input_data = StartContainerInput(project_id="my-project")

        assert input_data.project_id == "my-project"
        assert input_data.dotnet_version == DotNetVersion.V8  # Default

    def test_valid_full_input(self) -> None:
        """Test creating model with all fields."""
        input_data = StartContainerInput(
            project_id="test-app-123",
            dotnet_version=DotNetVersion.V9,
        )

        assert input_data.project_id == "test-app-123"
        assert input_data.dotnet_version == DotNetVersion.V9

    def test_auto_generated_project_id_includes_version(self) -> None:
        """Test that auto-generated project_id includes .NET version."""
        input_v8 = StartContainerInput(dotnet_version=DotNetVersion.V8)
        assert input_v8.project_id is not None
        assert input_v8.project_id.startswith("dotnet8-proj-")

        input_v9 = StartContainerInput(dotnet_version=DotNetVersion.V9)
        assert input_v9.project_id is not None
        assert input_v9.project_id.startswith("dotnet9-proj-")

        input_v10 = StartContainerInput(dotnet_version=DotNetVersion.V10)
        assert input_v10.project_id is not None
        assert input_v10.project_id.startswith("dotnet10-proj-")

    def test_auto_generated_project_id_is_unique(self) -> None:
        """Test that auto-generated project_ids are unique."""
        ids = {StartContainerInput().project_id for _ in range(10)}
        assert len(ids) == 10  # All unique

    def test_project_id_alphanumeric_with_hyphens_underscores(self) -> None:
        """Test that project_id accepts alphanumeric with hyphens and underscores."""
        valid_ids = ["project1", "my-project", "test_app", "app-123_v2"]

        for project_id in valid_ids:
            input_data = StartContainerInput(project_id=project_id)
            assert input_data.project_id == project_id

    def test_project_id_invalid_characters_rejected(self) -> None:
        """Test that project_id with invalid characters is rejected."""
        invalid_ids = ["project.name", "my project", "test@app", "app/123"]

        for project_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                StartContainerInput(project_id=project_id)

            errors = exc_info.value.errors()
            assert any("project_id" in str(e["loc"]) for e in errors)

    def test_project_id_too_long_rejected(self) -> None:
        """Test that project_id over 50 chars is rejected."""
        long_id = "x" * 51

        with pytest.raises(ValidationError) as exc_info:
            StartContainerInput(project_id=long_id)

        errors = exc_info.value.errors()
        assert any("project_id" in str(e["loc"]) for e in errors)

    def test_dotnet_version_from_integer(self) -> None:
        """Test that dotnet_version accepts integer values."""
        input_data = StartContainerInput(
            project_id="test",
            dotnet_version=9,  # type: ignore[arg-type]
        )

        assert input_data.dotnet_version == DotNetVersion.V9

    def test_ports_none_by_default(self) -> None:
        """Test that ports field defaults to None."""
        input_data = StartContainerInput(project_id="test")

        assert input_data.ports is None

    def test_valid_port_mapping(self) -> None:
        """Test creating model with valid port mapping."""
        input_data = StartContainerInput(
            project_id="test",
            ports={5000: 8080, 5001: 8081},
        )

        assert input_data.ports == {5000: 8080, 5001: 8081}

    def test_port_mapping_with_auto_assign(self) -> None:
        """Test port mapping with 0 for auto-assignment."""
        input_data = StartContainerInput(
            project_id="test",
            ports={5000: 0},  # 0 means Docker auto-assigns host port
        )

        assert input_data.ports == {5000: 0}

    def test_invalid_port_negative_rejected(self) -> None:
        """Test that negative ports are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StartContainerInput(
                project_id="test",
                ports={-1: 8080},
            )

        errors = exc_info.value.errors()
        assert any("ports" in str(e["loc"]) for e in errors)

    def test_invalid_port_too_large_rejected(self) -> None:
        """Test that ports over 65535 are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StartContainerInput(
                project_id="test",
                ports={5000: 70000},
            )

        errors = exc_info.value.errors()
        assert any("ports" in str(e["loc"]) for e in errors)

    def test_invalid_port_zero_container_rejected(self) -> None:
        """Test that container port cannot be 0 (only host port can)."""
        with pytest.raises(ValidationError) as exc_info:
            StartContainerInput(
                project_id="test",
                ports={0: 8080},
            )

        errors = exc_info.value.errors()
        assert any("ports" in str(e["loc"]) for e in errors)


class TestStartContainerInputPortCoercion:
    """Test port mapping with string key coercion (MCP JSON bug fix)."""

    def test_port_mapping_with_string_keys(self) -> None:
        """Test that string keys from JSON are coerced to integers.

        MCP clients send JSON where object keys are always strings.
        This test verifies {"5000": 8080} gets coerced to {5000: 8080}.
        """
        input_data = StartContainerInput(
            dotnet_version="8",
            ports={"5000": 8080, "5001": 8081},  # type: ignore[arg-type]  # String keys from JSON
        )
        # Should be coerced to integer keys
        assert input_data.ports == {5000: 8080, 5001: 8081}

    def test_port_mapping_with_string_values(self) -> None:
        """Test that string values are coerced to integers."""
        input_data = StartContainerInput(
            dotnet_version="8",
            ports={"5000": "8080"},  # type: ignore[arg-type]  # String value from JSON
        )
        assert input_data.ports == {5000: 8080}

    def test_port_mapping_auto_assign_with_strings(self) -> None:
        """Test auto-assignment with string keys and values."""
        input_data = StartContainerInput(
            dotnet_version="8",
            ports={"5000": "0"},  # type: ignore[arg-type]  # String "0" for auto-assign
        )
        assert input_data.ports == {5000: 0}

    def test_port_mapping_invalid_format(self) -> None:
        """Test that invalid port formats raise helpful errors."""
        with pytest.raises(ValidationError, match="must be integers"):
            StartContainerInput(
                dotnet_version="8",
                ports={"5000": "abc"},  # type: ignore[arg-type]  # Invalid value
            )

    def test_port_mapping_invalid_key_format(self) -> None:
        """Test that invalid port keys raise helpful errors."""
        with pytest.raises(ValidationError, match="must be integers"):
            StartContainerInput(
                dotnet_version="8",
                ports={"invalid": 8080},  # type: ignore[arg-type]  # Invalid key
            )

    def test_port_mapping_non_dict_rejected(self) -> None:
        """Test that non-dict/non-JSON string is rejected with helpful error."""
        # Non-JSON string (like Docker CLI format) should be rejected
        with pytest.raises(ValidationError, match="not valid JSON"):
            StartContainerInput(
                dotnet_version="8",
                ports="5000:8080",  # type: ignore[arg-type]  # Docker CLI format (invalid)
            )

    def test_port_mapping_json_string_claude_desktop_bug(self) -> None:
        """Test handling of JSON-encoded string (Claude Desktop double-encoding bug)."""
        # Claude Desktop sometimes sends: '{"5000": 8080}' instead of {"5000": 8080}
        input_data = StartContainerInput(
            dotnet_version="8",
            ports='{"5000": 8080}',  # type: ignore[arg-type]  # JSON string
        )
        assert input_data.ports == {5000: 8080}

    def test_port_mapping_json_string_with_auto_assign(self) -> None:
        """Test JSON string with auto-assignment (0 value)."""
        input_data = StartContainerInput(
            dotnet_version="8",
            ports='{"5000": 0}',  # type: ignore[arg-type]  # JSON string with auto-assign
        )
        assert input_data.ports == {5000: 0}

    def test_port_mapping_invalid_json_string(self) -> None:
        """Test that invalid JSON strings are rejected with helpful error."""
        with pytest.raises(ValidationError, match="not valid JSON"):
            StartContainerInput(
                dotnet_version="8",
                ports='{"5000: 8080',  # type: ignore[arg-type]  # Malformed JSON
            )


class TestStopContainerInput:
    """Test StopContainerInput model."""

    def test_valid_input(self) -> None:
        """Test creating model with valid input."""
        input_data = StopContainerInput(project_id="my-project-123")

        assert input_data.project_id == "my-project-123"

    def test_strips_whitespace(self) -> None:
        """Test that project_id is stripped."""
        input_data = StopContainerInput(project_id="  my-project  ")

        assert input_data.project_id == "my-project"

    def test_empty_project_id_rejected(self) -> None:
        """Test that empty project_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StopContainerInput(project_id="")

        errors = exc_info.value.errors()
        assert any("project_id" in str(e["loc"]) for e in errors)

    def test_project_id_too_long_rejected(self) -> None:
        """Test that project_id over 50 chars is rejected."""
        long_id = "x" * 51

        with pytest.raises(ValidationError) as exc_info:
            StopContainerInput(project_id=long_id)

        errors = exc_info.value.errors()
        assert any("project_id" in str(e["loc"]) for e in errors)


class TestWriteFileInput:
    """Test WriteFileInput model."""

    def test_valid_input(self) -> None:
        """Test creating model with valid input."""
        input_data = WriteFileInput(
            project_id="test-project",
            path="/workspace/Program.cs",
            content='Console.WriteLine("Hello");',
        )

        assert input_data.project_id == "test-project"
        assert input_data.path == "/workspace/Program.cs"
        assert 'WriteLine("Hello")' in input_data.content

    def test_valid_nested_path(self) -> None:
        """Test that nested paths within workspace are allowed."""
        input_data = WriteFileInput(
            project_id="test",
            path="/workspace/src/utils/Helper.cs",
            content="// Helper code",
        )

        assert input_data.path == "/workspace/src/utils/Helper.cs"

    def test_empty_content_allowed(self) -> None:
        """Test that empty content is allowed."""
        input_data = WriteFileInput(
            project_id="test",
            path="/workspace/empty.txt",
            content="",
        )

        assert input_data.content == ""

    def test_path_must_start_with_workspace(self) -> None:
        """Test that path must start with /workspace/."""
        with pytest.raises(ValidationError) as exc_info:
            WriteFileInput(
                project_id="test",
                path="/etc/passwd",
                content="malicious",
            )

        errors = exc_info.value.errors()
        assert any("workspace" in str(e["msg"]).lower() for e in errors)

    def test_path_cannot_contain_directory_traversal(self) -> None:
        """Test that path cannot contain '..' for directory traversal."""
        invalid_paths = [
            "/workspace/../etc/passwd",
            "/workspace/src/../../etc/passwd",
            "/workspace/foo/../bar",
        ]

        for path in invalid_paths:
            with pytest.raises(ValidationError) as exc_info:
                WriteFileInput(
                    project_id="test",
                    path=path,
                    content="test",
                )

            errors = exc_info.value.errors()
            assert any("traversal" in str(e["msg"]).lower() for e in errors)

    def test_content_too_long_rejected(self) -> None:
        """Test that content over 100KB is rejected."""
        long_content = "x" * 100001

        with pytest.raises(ValidationError) as exc_info:
            WriteFileInput(
                project_id="test",
                path="/workspace/large.txt",
                content=long_content,
            )

        errors = exc_info.value.errors()
        assert any("content" in str(e["loc"]) for e in errors)


class TestReadFileInput:
    """Test ReadFileInput model."""

    def test_valid_input(self) -> None:
        """Test creating model with valid input."""
        input_data = ReadFileInput(
            project_id="test-project",
            path="/workspace/Program.cs",
        )

        assert input_data.project_id == "test-project"
        assert input_data.path == "/workspace/Program.cs"

    def test_valid_nested_path(self) -> None:
        """Test that nested paths within workspace are allowed."""
        input_data = ReadFileInput(
            project_id="test",
            path="/workspace/src/utils/Helper.cs",
        )

        assert input_data.path == "/workspace/src/utils/Helper.cs"

    def test_path_must_start_with_workspace(self) -> None:
        """Test that path must start with /workspace/."""
        with pytest.raises(ValidationError) as exc_info:
            ReadFileInput(
                project_id="test",
                path="/etc/passwd",
            )

        errors = exc_info.value.errors()
        assert any("workspace" in str(e["msg"]).lower() for e in errors)

    def test_path_cannot_contain_directory_traversal(self) -> None:
        """Test that path cannot contain '..' for directory traversal."""
        with pytest.raises(ValidationError) as exc_info:
            ReadFileInput(
                project_id="test",
                path="/workspace/../etc/passwd",
            )

        errors = exc_info.value.errors()
        assert any("traversal" in str(e["msg"]).lower() for e in errors)


class TestListFilesInput:
    """Test ListFilesInput model."""

    def test_valid_input_default_path(self) -> None:
        """Test creating model with default path."""
        input_data = ListFilesInput(project_id="test-project")

        assert input_data.project_id == "test-project"
        assert input_data.path == "/workspace"  # Default

    def test_valid_input_custom_path(self) -> None:
        """Test creating model with custom path."""
        input_data = ListFilesInput(
            project_id="test-project",
            path="/workspace/src",
        )

        assert input_data.path == "/workspace/src"

    def test_path_must_start_with_workspace(self) -> None:
        """Test that path must start with /workspace."""
        with pytest.raises(ValidationError) as exc_info:
            ListFilesInput(
                project_id="test",
                path="/etc",
            )

        errors = exc_info.value.errors()
        assert any("workspace" in str(e["msg"]).lower() for e in errors)

    def test_path_cannot_contain_directory_traversal(self) -> None:
        """Test that path cannot contain '..' for directory traversal."""
        with pytest.raises(ValidationError) as exc_info:
            ListFilesInput(
                project_id="test",
                path="/workspace/../etc",
            )

        errors = exc_info.value.errors()
        assert any("traversal" in str(e["msg"]).lower() for e in errors)


class TestExecuteCommandInput:
    """Test ExecuteCommandInput model."""

    def test_valid_input_default_timeout(self) -> None:
        """Test creating model with default timeout."""
        input_data = ExecuteCommandInput(
            project_id="test-project",
            command=["dotnet", "build"],
        )

        assert input_data.project_id == "test-project"
        assert input_data.command == ["dotnet", "build"]
        assert input_data.timeout == 30  # Default

    def test_valid_input_custom_timeout(self) -> None:
        """Test creating model with custom timeout."""
        input_data = ExecuteCommandInput(
            project_id="test-project",
            command=["dotnet", "run"],
            timeout=60,
        )

        assert input_data.timeout == 60

    def test_valid_complex_command(self) -> None:
        """Test creating model with complex command."""
        input_data = ExecuteCommandInput(
            project_id="test",
            command=["dotnet", "run", "--project", "/workspace/MyApp"],
        )

        assert len(input_data.command) == 4
        assert input_data.command[3] == "/workspace/MyApp"

    def test_empty_command_rejected(self) -> None:
        """Test that empty command list is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteCommandInput(
                project_id="test",
                command=[],
            )

        errors = exc_info.value.errors()
        assert any("command" in str(e["loc"]) for e in errors)

    def test_timeout_too_low_rejected(self) -> None:
        """Test that timeout below 1 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteCommandInput(
                project_id="test",
                command=["echo", "test"],
                timeout=0,
            )

        errors = exc_info.value.errors()
        assert any("timeout" in str(e["loc"]) for e in errors)

    def test_timeout_too_high_rejected(self) -> None:
        """Test that timeout above 300 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteCommandInput(
                project_id="test",
                command=["sleep", "400"],
                timeout=301,
            )

        errors = exc_info.value.errors()
        assert any("timeout" in str(e["loc"]) for e in errors)

    def test_command_with_empty_string_rejected(self) -> None:
        """Test that command with empty string is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteCommandInput(
                project_id="test",
                command=["dotnet", "", "build"],
            )

        errors = exc_info.value.errors()
        assert any("command" in str(e["msg"]).lower() for e in errors)


class TestRunBackgroundInput:
    """Test RunBackgroundInput model."""

    def test_valid_input_default_wait(self) -> None:
        """Test creating model with default wait_for_ready."""
        input_data = RunBackgroundInput(
            project_id="test-project",
            command=["dotnet", "run"],
        )

        assert input_data.project_id == "test-project"
        assert input_data.command == ["dotnet", "run"]
        assert input_data.wait_for_ready == 5  # Default

    def test_valid_input_custom_wait(self) -> None:
        """Test creating model with custom wait_for_ready."""
        input_data = RunBackgroundInput(
            project_id="test-api",
            command=["dotnet", "run", "--project", "/workspace/MyApp"],
            wait_for_ready=10,
        )

        assert input_data.wait_for_ready == 10

    def test_wait_for_ready_zero_allowed(self) -> None:
        """Test that wait_for_ready=0 is valid (no wait)."""
        input_data = RunBackgroundInput(
            project_id="test",
            command=["dotnet", "run"],
            wait_for_ready=0,
        )

        assert input_data.wait_for_ready == 0

    def test_wait_for_ready_too_high_rejected(self) -> None:
        """Test that wait_for_ready over 60 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RunBackgroundInput(
                project_id="test",
                command=["dotnet", "run"],
                wait_for_ready=61,
            )

        errors = exc_info.value.errors()
        assert any("wait_for_ready" in str(e["loc"]) for e in errors)


class TestTestEndpointInput:
    """Test TestEndpointInput model."""

    def test_valid_input_minimal(self) -> None:
        """Test creating model with minimal input (just URL)."""
        input_data = TestEndpointInput(
            url="http://localhost:8080/health",
        )

        assert input_data.url == "http://localhost:8080/health"
        assert input_data.method == "GET"  # Default
        assert input_data.headers == {}  # Default empty dict
        assert input_data.body is None
        assert input_data.timeout == 30  # Default

    def test_valid_input_full(self) -> None:
        """Test creating model with all fields."""
        input_data = TestEndpointInput(
            url="https://api.example.com/users",
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer token"},
            body='{"name": "John"}',
            timeout=60,
        )

        assert input_data.url == "https://api.example.com/users"
        assert input_data.method == "POST"
        assert input_data.headers == {
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
        }
        assert input_data.body == '{"name": "John"}'
        assert input_data.timeout == 60

    def test_url_without_scheme_rejected(self) -> None:
        """Test that URL without http:// or https:// is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TestEndpointInput(
                url="localhost:8080/api",
            )

        errors = exc_info.value.errors()
        assert any("url" in str(e["msg"]).lower() for e in errors)

    def test_invalid_method_rejected(self) -> None:
        """Test that invalid HTTP method is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TestEndpointInput(
                url="http://localhost:8080/test",
                method="INVALID",  # type: ignore[arg-type]
            )

        errors = exc_info.value.errors()
        assert any("method" in str(e["loc"]) for e in errors)


class TestGetLogsInput:
    """Test GetLogsInput model."""

    def test_valid_input_defaults(self) -> None:
        """Test creating model with default values."""
        input_data = GetLogsInput(
            project_id="test-project",
        )

        assert input_data.project_id == "test-project"
        assert input_data.tail == 50  # Default
        assert input_data.since is None  # Default

    def test_valid_input_custom_tail(self) -> None:
        """Test creating model with custom tail."""
        input_data = GetLogsInput(
            project_id="test-api",
            tail=100,
        )

        assert input_data.tail == 100

    def test_valid_input_with_since(self) -> None:
        """Test creating model with since parameter."""
        input_data = GetLogsInput(
            project_id="test",
            tail=20,
            since=300,  # Last 5 minutes
        )

        assert input_data.since == 300

    def test_tail_too_low_rejected(self) -> None:
        """Test that tail=0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GetLogsInput(
                project_id="test",
                tail=0,
            )

        errors = exc_info.value.errors()
        assert any("tail" in str(e["loc"]) for e in errors)

    def test_tail_too_high_rejected(self) -> None:
        """Test that tail over 1000 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GetLogsInput(
                project_id="test",
                tail=1001,
            )

        errors = exc_info.value.errors()
        assert any("tail" in str(e["loc"]) for e in errors)

    def test_since_too_high_rejected(self) -> None:
        """Test that since over 3600 (1 hour) is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GetLogsInput(
                project_id="test",
                since=3601,
            )

        errors = exc_info.value.errors()
        assert any("since" in str(e["loc"]) for e in errors)


class TestKillProcessInput:
    """Test KillProcessInput model."""

    def test_valid_input_no_pattern(self) -> None:
        """Test creating model without process pattern (kills all dotnet)."""
        input_data = KillProcessInput(
            project_id="test-project",
        )

        assert input_data.project_id == "test-project"
        assert input_data.process_pattern is None

    def test_valid_input_with_pattern(self) -> None:
        """Test creating model with specific process pattern."""
        input_data = KillProcessInput(
            project_id="test-api",
            process_pattern="dotnet run",
        )

        assert input_data.project_id == "test-api"
        assert input_data.process_pattern == "dotnet run"

    def test_strips_whitespace(self) -> None:
        """Test that whitespace is stripped from fields."""
        input_data = KillProcessInput(
            project_id="  test  ",
            process_pattern="  dotnet run --project MyApp  ",
        )

        assert input_data.project_id == "test"
        assert input_data.process_pattern == "dotnet run --project MyApp"

    def test_pattern_too_long_rejected(self) -> None:
        """Test that patterns over 200 chars are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            KillProcessInput(
                project_id="test",
                process_pattern="x" * 201,
            )

        errors = exc_info.value.errors()
        assert any("process_pattern" in str(e["loc"]) for e in errors)


class TestListContainersInput:
    """Test ListContainersInput model."""

    def test_valid_input_no_parameters(self) -> None:
        """Test creating model with no parameters (lists all containers)."""
        input_data = ListContainersInput()

        # Should successfully create with no fields
        assert input_data is not None
        assert isinstance(input_data, ListContainersInput)

    def test_valid_input_from_empty_dict(self) -> None:
        """Test creating model from empty dict."""
        input_data = ListContainersInput(**{})

        assert input_data is not None
        assert isinstance(input_data, ListContainersInput)

    def test_model_json_schema(self) -> None:
        """Test that JSON schema is generated correctly."""
        schema = ListContainersInput.model_json_schema()

        assert schema is not None
        assert "properties" in schema
        # Should have no required fields
        assert schema.get("required", []) == []
