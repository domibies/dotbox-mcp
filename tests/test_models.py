"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from src.models import DetailLevel, DotNetVersion, ExecuteSnippetInput


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
