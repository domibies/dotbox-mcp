"""Output formatting utilities for MCP responses."""

import json
from typing import Any

from src.models import DetailLevel


class OutputFormatter:
    """Formats tool outputs for optimal LLM consumption."""

    CHARACTER_LIMIT = 25000  # Standard MCP limit

    def format_execution_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        detail_level: DetailLevel,
    ) -> str:
        """Format execution results with clear sections.

        Args:
            stdout: Standard output from execution
            stderr: Standard error from execution
            exit_code: Process exit code
            detail_level: Level of detail to include

        Returns:
            Formatted output string
        """
        # Apply detail level filtering
        if detail_level == DetailLevel.CONCISE:
            stdout = self._truncate_to_first_n_lines(stdout, 50)
            stderr = self._truncate_to_first_n_lines(stderr, 50)

        # Build output sections
        sections = []

        if stdout:
            sections.append(f"=== STDOUT ===\n{stdout}")

        if stderr:
            sections.append(f"=== STDERR ===\n{stderr}")

        sections.append(f"=== EXIT CODE ===\n{exit_code}")

        combined = "\n\n".join(sections)

        # Enforce character limit
        if len(combined) > self.CHARACTER_LIMIT:
            combined = self._truncate_to_char_limit(combined, self.CHARACTER_LIMIT)

        return combined

    def format_json_response(
        self,
        status: str,
        data: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Format response as JSON string.

        Args:
            status: Response status ("success" or "error")
            data: Response data (for success)
            error: Error details (for error)
            metadata: Optional metadata

        Returns:
            JSON string
        """
        response: dict[str, Any] = {"status": status}

        if data is not None:
            response["data"] = data

        if error is not None:
            response["error"] = error

        if metadata is not None:
            response["metadata"] = metadata

        return json.dumps(response, indent=2)

    def _truncate_to_first_n_lines(self, text: str, n: int) -> str:
        """Truncate text to first N lines.

        Args:
            text: Input text
            n: Number of lines to keep

        Returns:
            Truncated text with message if truncated
        """
        if not text:
            return text

        lines = text.split("\n")
        if len(lines) <= n:
            return text

        truncated_lines = lines[:n]
        truncated_lines.append(
            f"\n... (truncated to first {n} lines, use detail_level='full' for complete output)"
        )
        return "\n".join(truncated_lines)

    def _truncate_to_char_limit(self, text: str, limit: int) -> str:
        """Truncate text to character limit.

        Args:
            text: Input text
            limit: Maximum character count

        Returns:
            Truncated text with message
        """
        if len(text) <= limit:
            return text

        # Reserve space for truncation message
        message = f"\n\n... (output truncated from {len(text)} to {limit} characters)"
        available = limit - len(message)

        if available <= 0:
            return message

        return text[:available] + message
