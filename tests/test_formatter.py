"""Tests for OutputFormatter."""

import json

from src.formatter import OutputFormatter
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
