"""Tests for OutputFormatter."""

import json

from src.formatter import MarkdownFormatter, OutputFormatter
from src.models import DetailLevel


class TestOutputFormatter:
    """Test OutputFormatter class."""

    def test_character_limit_constant(self) -> None:
        """Test that character limit is set correctly."""
        assert OutputFormatter.CHARACTER_LIMIT == 25000

    def test_format_execution_output_concise_mode(self) -> None:
        """Test that concise mode returns first 50 lines."""
        # Create output with 100 lines
        stdout_lines = [f"Line {i}" for i in range(100)]
        stdout = "\n".join(stdout_lines)
        stderr = ""
        exit_code = 0

        formatter = OutputFormatter()
        result = formatter.format_execution_output(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            detail_level=DetailLevel.CONCISE,
        )

        # Should contain first 50 lines
        for i in range(50):
            assert f"Line {i}" in result

        # Should NOT contain lines beyond 50
        assert "Line 75" not in result
        assert "Line 99" not in result

        # Should indicate truncation
        assert "truncated" in result.lower() or "concise" in result.lower()

    def test_format_execution_output_full_mode(self) -> None:
        """Test that full mode returns all output."""
        stdout_lines = [f"Line {i}" for i in range(100)]
        stdout = "\n".join(stdout_lines)
        stderr = ""
        exit_code = 0

        formatter = OutputFormatter()
        result = formatter.format_execution_output(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            detail_level=DetailLevel.FULL,
        )

        # Should contain all lines
        for i in range(100):
            assert f"Line {i}" in result

    def test_format_execution_output_with_stderr(self) -> None:
        """Test formatting when stderr has content."""
        stdout = "Standard output"
        stderr = "Error message"
        exit_code = 1

        formatter = OutputFormatter()
        result = formatter.format_execution_output(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            detail_level=DetailLevel.FULL,
        )

        assert "Standard output" in result
        assert "Error message" in result
        assert "1" in result  # Exit code

    def test_format_execution_output_enforces_character_limit(self) -> None:
        """Test that output is truncated if it exceeds CHARACTER_LIMIT."""
        # Create output larger than 25k characters
        long_output = "x" * 30000
        stderr = ""
        exit_code = 0

        formatter = OutputFormatter()
        result = formatter.format_execution_output(
            stdout=long_output,
            stderr=stderr,
            exit_code=exit_code,
            detail_level=DetailLevel.FULL,
        )

        # Result should not exceed limit
        assert len(result) <= OutputFormatter.CHARACTER_LIMIT

        # Should contain truncation message
        assert "truncated" in result.lower()

    def test_format_json_response_success(self) -> None:
        """Test formatting successful JSON response."""
        formatter = OutputFormatter()
        result = formatter.format_json_response(
            status="success",
            data={"output": "Hello World"},
            metadata={"execution_time_ms": 123},
        )

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["output"] == "Hello World"
        assert parsed["metadata"]["execution_time_ms"] == 123

    def test_format_json_response_error(self) -> None:
        """Test formatting error JSON response."""
        formatter = OutputFormatter()
        result = formatter.format_json_response(
            status="error",
            error={
                "type": "BuildError",
                "message": "Build failed",
                "suggestions": ["Add using directive"],
            },
            metadata={"execution_time_ms": 50},
        )

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error"]["type"] == "BuildError"
        assert parsed["error"]["message"] == "Build failed"
        assert "Add using directive" in parsed["error"]["suggestions"]

    def test_truncate_to_first_n_lines(self) -> None:
        """Test truncating output to first N lines."""
        lines = [f"Line {i}" for i in range(100)]
        text = "\n".join(lines)

        formatter = OutputFormatter()
        result = formatter._truncate_to_first_n_lines(text, 10)

        # Should contain first 10 lines
        for i in range(10):
            assert f"Line {i}" in result

        # Should not contain line 11 onwards
        assert "Line 10" not in result
        assert "Line 50" not in result

    def test_truncate_to_character_limit(self) -> None:
        """Test truncating to character limit."""
        long_text = "x" * 30000

        formatter = OutputFormatter()
        result = formatter._truncate_to_char_limit(long_text, 25000)

        assert len(result) <= 25000
        assert "truncated" in result.lower()

    def test_empty_stdout_and_stderr(self) -> None:
        """Test handling empty output."""
        formatter = OutputFormatter()
        result = formatter.format_execution_output(
            stdout="",
            stderr="",
            exit_code=0,
            detail_level=DetailLevel.FULL,
        )

        # Should still be valid and contain exit code
        assert "0" in result

    def test_only_stderr_no_stdout(self) -> None:
        """Test when only stderr has content."""
        formatter = OutputFormatter()
        result = formatter.format_execution_output(
            stdout="",
            stderr="Error occurred",
            exit_code=1,
            detail_level=DetailLevel.FULL,
        )

        assert "Error occurred" in result
        assert "1" in result

    def test_format_human_readable_success(self) -> None:
        """Test human-readable success format."""
        formatter = OutputFormatter()
        result = formatter.format_human_readable_response(
            status="success",
            output="Hello World",
            exit_code=0,
            dotnet_version="8",
        )

        # Should contain success indicator
        assert "[SUCCESS]" in result or "success" in result.lower()
        # Should contain .NET version
        assert "8" in result
        # Should contain output
        assert "Hello World" in result
        # Should contain exit code
        assert "0" in result

    def test_format_human_readable_success_no_output(self) -> None:
        """Test human-readable success format with no output."""
        formatter = OutputFormatter()
        result = formatter.format_human_readable_response(
            status="success",
            output="",
            exit_code=0,
            dotnet_version="9",
        )

        # Should indicate no output
        assert "no output" in result.lower()
        # Should still show version and exit code
        assert "9" in result
        assert "0" in result

    def test_format_human_readable_error_with_build_errors(self) -> None:
        """Test human-readable error format with build errors."""
        formatter = OutputFormatter()
        result = formatter.format_human_readable_response(
            status="error",
            error_message="Build failed",
            error_details="Compilation errors occurred",
            build_errors=[
                "Program.cs(1,1): error CS0103: Name does not exist",
                "Program.cs(2,5): error CS0246: Type not found",
            ],
            dotnet_version="8",
        )

        # Should contain error indicator
        assert "[ERROR]" in result or "failed" in result.lower()
        # Should contain error message
        assert "Build failed" in result
        # Should contain build errors
        assert "CS0103" in result
        assert "CS0246" in result
        # Should use bullet points (asterisks)
        assert "*" in result

    def test_format_human_readable_error_with_suggestions(self) -> None:
        """Test human-readable error format with suggestions."""
        formatter = OutputFormatter()
        result = formatter.format_human_readable_response(
            status="error",
            error_message="Docker not available",
            error_details="Connection refused",
            suggestions=[
                "Ensure Docker is running",
                "Check permissions",
            ],
        )

        # Should contain suggestions section
        assert "Suggestions:" in result or "suggestions" in result.lower()
        # Should contain suggestion arrows (->)
        assert "->" in result
        # Should contain suggestions
        assert "Docker is running" in result
        assert "permissions" in result

    def test_format_human_readable_error_many_build_errors(self) -> None:
        """Test that many build errors are limited."""
        formatter = OutputFormatter()
        build_errors = [f"Error {i}" for i in range(20)]

        result = formatter.format_human_readable_response(
            status="error",
            error_message="Build failed",
            build_errors=build_errors,
        )

        # Should contain first 10 errors
        for i in range(10):
            assert f"Error {i}" in result

        # Should indicate more errors exist
        assert "more" in result.lower() or "..." in result

    def test_format_human_readable_enforces_character_limit(self) -> None:
        """Test that human-readable format enforces character limit."""
        formatter = OutputFormatter()

        # Create very long output
        long_output = "x" * 30000

        result = formatter.format_human_readable_response(
            status="success",
            output=long_output,
            exit_code=0,
            dotnet_version="8",
        )

        # Should not exceed character limit
        assert len(result) <= OutputFormatter.CHARACTER_LIMIT
        # Should contain truncation message
        assert "truncated" in result.lower()

    def test_format_human_readable_with_separators(self) -> None:
        """Test that output uses visual separators."""
        formatter = OutputFormatter()
        result = formatter.format_human_readable_response(
            status="success",
            output="Test output",
            exit_code=0,
            dotnet_version="8",
        )

        # Should contain separator lines
        assert "-" in result

    def test_format_human_readable_error_details(self) -> None:
        """Test error details are shown in error response."""
        formatter = OutputFormatter()
        result = formatter.format_human_readable_response(
            status="error",
            error_message="Execution failed",
            error_details="Stack trace:\nLine 1\nLine 2",
        )

        # Should contain details section
        assert "Details:" in result or "details" in result.lower()
        # Should contain the details
        assert "Stack trace" in result
        assert "Line 1" in result

    def test_format_human_readable_success_with_code(self) -> None:
        """Test that executed code is displayed in success response."""
        formatter = OutputFormatter()
        code = 'Console.WriteLine("Hello World");'
        result = formatter.format_human_readable_response(
            status="success",
            output="Hello World",
            exit_code=0,
            dotnet_version="8",
            code=code,
        )

        # Should contain code section
        assert "Executed C# Code:" in result
        # Should contain the actual code
        assert code in result
        # Should have separator lines
        assert "-" in result
        # Should still have output
        assert "Hello World" in result

    def test_format_human_readable_error_with_code(self) -> None:
        """Test that failed code is displayed in error response."""
        formatter = OutputFormatter()
        code = "InvalidCode;"
        result = formatter.format_human_readable_response(
            status="error",
            error_message="Build failed",
            error_details="Compilation error",
            code=code,
        )

        # Should contain code section
        assert "Code that failed:" in result
        # Should contain the actual code
        assert code in result
        # Should have error message
        assert "Build failed" in result

    def test_format_human_readable_error_with_output(self) -> None:
        """Test that error responses can display output (e.g. HTTP error body)."""
        formatter = OutputFormatter()
        error_body = '{"error": "Invalid parameter", "code": "BAD_REQUEST"}'
        result = formatter.format_human_readable_response(
            status="error",
            error_message="HTTP 400 Bad Request",
            output=error_body,
        )

        # Should contain error message
        assert "400 Bad Request" in result
        # Should contain the output/response body
        assert "Response:" in result
        assert "Invalid parameter" in result
        assert "BAD_REQUEST" in result

    def test_format_human_readable_without_code(self) -> None:
        """Test that response works without code parameter."""
        formatter = OutputFormatter()
        result = formatter.format_human_readable_response(
            status="success",
            output="Output",
            exit_code=0,
            dotnet_version="8",
            # No code parameter
        )

        # Should not have code section
        assert "Executed C# Code:" not in result
        # But should still have output
        assert "Output" in result


class TestMarkdownFormatter:
    """Test MarkdownFormatter helper class."""

    def test_format_header_success(self) -> None:
        """Test formatting success header."""
        result = MarkdownFormatter.format_header("success", "Execution Result")
        assert result == "# Execution Result ✓"

    def test_format_header_error(self) -> None:
        """Test formatting error header."""
        result = MarkdownFormatter.format_header("error", "Build Failed")
        assert result == "# Build Failed ✗"

    def test_format_metadata(self) -> None:
        """Test formatting metadata."""
        metadata = {"Runtime": ".NET 8.0.0", "Container": "abc123"}
        result = MarkdownFormatter.format_metadata(metadata)
        assert "**Runtime:** .NET 8.0.0" in result
        assert "**Container:** abc123" in result

    def test_format_code_block(self) -> None:
        """Test formatting code block."""
        result = MarkdownFormatter.format_code_block("Console.WriteLine();", "csharp")
        assert result.startswith("```csharp")
        assert "Console.WriteLine();" in result
        assert result.endswith("```")

    def test_format_section(self) -> None:
        """Test formatting section."""
        result = MarkdownFormatter.format_section("Output", "Hello World")
        assert result.startswith("## Output")
        assert "Hello World" in result

    def test_format_error_list(self) -> None:
        """Test formatting error list."""
        errors = ["error CS0103: Name not found", "error CS0246: Type not found"]
        result = MarkdownFormatter.format_error_list(errors)
        assert "**error CS0103" in result
        assert "**error CS0246" in result

    def test_format_suggestions(self) -> None:
        """Test formatting suggestions."""
        suggestions = ["Add using directive", "Check variable name"]
        result = MarkdownFormatter.format_suggestions(suggestions)
        assert "- Add using directive" in result
        assert "- Check variable name" in result


class TestMarkdownFormatMethods:
    """Test Markdown formatting methods."""

    def test_format_execution_result_markdown_success(self) -> None:
        """Test formatting successful execution as Markdown."""
        formatter = OutputFormatter()
        result = formatter.format_execution_result_markdown(
            status="success",
            stdout="Hello, World!",
            stderr="",
            exit_code=0,
            dotnet_version="8.0.0",
            execution_time_ms=1234,
            detail_level=DetailLevel.CONCISE,
        )

        assert "# Execution Result ✓" in result
        assert "**Runtime:** .NET 8.0.0 (1.2s)" in result
        assert "## Output" in result
        assert "Hello, World!" in result
        assert "```" in result
        assert "*C# code executed successfully*" in result

    def test_format_execution_result_markdown_error(self) -> None:
        """Test formatting execution error as Markdown."""
        formatter = OutputFormatter()
        result = formatter.format_execution_result_markdown(
            status="error",
            stdout="",
            stderr="Unhandled exception: Division by zero",
            exit_code=1,
            dotnet_version="8.0.0",
            execution_time_ms=500,
            detail_level=DetailLevel.CONCISE,
        )

        assert "# Execution Failed ✗" in result
        assert "**Runtime:** .NET 8.0.0" in result
        assert "**Exit Code:** 1" in result
        assert "## Error Output" in result
        assert "Division by zero" in result

    def test_format_build_error_markdown(self) -> None:
        """Test formatting build errors as Markdown."""
        formatter = OutputFormatter()
        errors = ["error CS0103: The name 'x' does not exist"]
        suggestions = ["Check variable name", "Add using directive"]

        result = formatter.format_build_error_markdown(
            errors=errors,
            suggestions=suggestions,
            dotnet_version="8.0.0",
            execution_time_ms=500,
        )

        assert "# Build Failed ✗" in result
        assert "**Runtime:** .NET 8.0.0 (0.5s)" in result
        assert "## Errors" in result
        assert "**error CS0103" in result
        assert "## Suggestions" in result
        assert "- Check variable name" in result
        assert "- Add using directive" in result

    def test_format_logs_markdown(self) -> None:
        """Test formatting logs as Markdown."""
        formatter = OutputFormatter()
        logs = "2024-11-02 10:00:00 Server started\n2024-11-02 10:00:01 Listening on port 8080"

        result = formatter.format_logs_markdown(
            project_id="my-project",
            logs=logs,
            tail=50,
            detail_level=DetailLevel.CONCISE,
        )

        assert "# Container Logs ✓" in result
        assert "**Project:** my-project" in result
        assert "**Lines:** 50" in result
        assert "## Logs" in result
        assert "Server started" in result
        assert "```" in result

    def test_format_container_info_markdown_with_urls(self) -> None:
        """Test formatting container info with URLs."""
        formatter = OutputFormatter()
        result = formatter.format_container_info_markdown(
            project_id="my-api",
            container_id="abc123def456",
            dotnet_version="8.0.0",
            urls=["http://localhost:8080", "http://localhost:8080/swagger"],
            status="success",
        )

        assert "# Container Started ✓" in result
        assert "**Project:** my-api" in result
        assert "**Container:** abc123def456" in result
        assert "**Runtime:** .NET 8.0.0" in result
        assert "## Access URLs" in result
        assert "http://localhost:8080" in result
        assert "http://localhost:8080/swagger" in result
        assert "*Each URL on its own line for clickability*" in result

    def test_format_endpoint_response_markdown_success(self) -> None:
        """Test formatting HTTP response as Markdown."""
        formatter = OutputFormatter()
        result = formatter.format_endpoint_response_markdown(
            method="GET",
            url="http://localhost:8080/api/users",
            status_code=200,
            response_body='{"users": [{"id": 1, "name": "John"}]}',
            response_time_ms=145,
            detail_level=DetailLevel.CONCISE,
        )

        assert "# GET /api/users → 200 OK ✓" in result
        assert "**Response Time:** 145ms" in result
        assert "## Response" in result
        assert "```json" in result
        assert "users" in result

    def test_format_endpoint_response_markdown_error(self) -> None:
        """Test formatting HTTP error response as Markdown."""
        formatter = OutputFormatter()
        result = formatter.format_endpoint_response_markdown(
            method="GET",
            url="http://localhost:8080/api/users",
            status_code=500,
            response_body='{"error": "Internal server error"}',
            response_time_ms=234,
            detail_level=DetailLevel.CONCISE,
        )

        assert "# GET /api/users → 500 Internal Server Error ✗" in result
        assert "**Response Time:** 234ms" in result
        assert "error" in result.lower()
