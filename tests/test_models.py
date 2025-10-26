"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from src.models import (
    DetailLevel,
    DotNetVersion,
    ExecuteSnippetInput,
    StartContainerInput,
    StopContainerInput,
)


class TestDotNetVersion:
    """Test DotNetVersion enum."""

    def test_version_values(self) -> None:
        """Test that enum has correct version values."""
        assert DotNetVersion.V8.value == "8"
        assert DotNetVersion.V9.value == "9"
        assert DotNetVersion.V10_RC2.value == "10-rc2"

    def test_can_create_from_string(self) -> None:
        """Test creating enum from string."""
        assert DotNetVersion("8") == DotNetVersion.V8
        assert DotNetVersion("9") == DotNetVersion.V9
        assert DotNetVersion("10-rc2") == DotNetVersion.V10_RC2


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
        for version_str in ["8", "9", "10-rc2"]:
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
        assert set(str_variant["enum"]) == {"8", "9", "10-rc2"}


class TestStartContainerInput:
    """Test StartContainerInput model."""

    def test_valid_minimal_input(self) -> None:
        """Test creating model with minimal valid input."""
        input_data = StartContainerInput(
            project_id="my-project",
            working_dir="/tmp/workspace",
        )

        assert input_data.project_id == "my-project"
        assert input_data.working_dir == "/tmp/workspace"
        assert input_data.dotnet_version == DotNetVersion.V8  # Default

    def test_valid_full_input(self) -> None:
        """Test creating model with all fields."""
        input_data = StartContainerInput(
            project_id="test-app-123",
            dotnet_version=DotNetVersion.V9,
            working_dir="/home/user/projects/test",
        )

        assert input_data.project_id == "test-app-123"
        assert input_data.dotnet_version == DotNetVersion.V9
        assert input_data.working_dir == "/home/user/projects/test"

    def test_project_id_alphanumeric_with_hyphens_underscores(self) -> None:
        """Test that project_id accepts alphanumeric with hyphens and underscores."""
        valid_ids = ["project1", "my-project", "test_app", "app-123_v2"]

        for project_id in valid_ids:
            input_data = StartContainerInput(
                project_id=project_id,
                working_dir="/tmp",
            )
            assert input_data.project_id == project_id

    def test_project_id_invalid_characters_rejected(self) -> None:
        """Test that project_id with invalid characters is rejected."""
        invalid_ids = ["project.name", "my project", "test@app", "app/123"]

        for project_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                StartContainerInput(
                    project_id=project_id,
                    working_dir="/tmp",
                )

            errors = exc_info.value.errors()
            assert any("project_id" in str(e["loc"]) for e in errors)

    def test_project_id_too_long_rejected(self) -> None:
        """Test that project_id over 50 chars is rejected."""
        long_id = "x" * 51

        with pytest.raises(ValidationError) as exc_info:
            StartContainerInput(
                project_id=long_id,
                working_dir="/tmp",
            )

        errors = exc_info.value.errors()
        assert any("project_id" in str(e["loc"]) for e in errors)

    def test_empty_working_dir_rejected(self) -> None:
        """Test that empty working_dir is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StartContainerInput(
                project_id="test",
                working_dir="",
            )

        errors = exc_info.value.errors()
        assert any("working_dir" in str(e["loc"]) for e in errors)

    def test_dotnet_version_from_integer(self) -> None:
        """Test that dotnet_version accepts integer values."""
        input_data = StartContainerInput(
            project_id="test",
            working_dir="/tmp",
            dotnet_version=9,  # type: ignore[arg-type]
        )

        assert input_data.dotnet_version == DotNetVersion.V9


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
