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

    def format_human_readable_response(
        self,
        status: str,
        output: str = "",
        exit_code: int = 0,
        dotnet_version: str = "",
        code: str = "",
        error_type: str = "",
        error_message: str = "",
        error_details: str = "",
        build_errors: list[str] | None = None,
        suggestions: list[str] | None = None,
        container_id: str = "",
        project_id: str = "",
    ) -> str:
        """Format response in human-readable format.

        Args:
            status: Response status ("success" or "error")
            output: Execution output
            exit_code: Process exit code
            dotnet_version: .NET version used
            code: C# code that was executed (optional, for display)
            error_type: Type of error (if status is error)
            error_message: Error message (if status is error)
            error_details: Detailed error information
            build_errors: List of build errors
            suggestions: List of suggestions
            container_id: Docker container ID (optional)
            project_id: Project identifier (optional)

        Returns:
            Human-readable formatted string
        """
        sections = []

        if status == "success":
            # Success header
            sections.append(f"[SUCCESS] Code executed successfully using .NET {dotnet_version}")
            sections.append("")

            # Code section (if provided)
            if code:
                sections.append("Executed C# Code:")
                sections.append("-" * 60)
                sections.append(code)
                sections.append("-" * 60)
                sections.append("")

            # Output section
            if output.strip():
                sections.append("Output:")
                sections.append("-" * 60)
                sections.append(output.strip())
                sections.append("-" * 60)
            else:
                sections.append("(no output)")

            sections.append("")
            sections.append(f"Exit code: {exit_code}")

        else:
            # Error header
            sections.append(f"[ERROR] Execution failed: {error_message}")
            if dotnet_version:
                sections.append(f"(.NET {dotnet_version})")
            sections.append("")

            # Code section (if provided)
            if code:
                sections.append("Code that failed:")
                sections.append("-" * 60)
                sections.append(code)
                sections.append("-" * 60)
                sections.append("")

            # Build errors
            if build_errors:
                sections.append("Build Errors:")
                sections.append("-" * 60)
                for err in build_errors[:10]:  # Limit to first 10
                    sections.append(f"  * {err}")
                if len(build_errors) > 10:
                    sections.append(f"  ... and {len(build_errors) - 10} more errors")
                sections.append("-" * 60)
                sections.append("")

            # Error details
            if error_details:
                sections.append("Details:")
                sections.append("-" * 60)
                sections.append(error_details.strip())
                sections.append("-" * 60)
                sections.append("")

            # Output section (for error responses with output like HTTP error bodies)
            if output.strip():
                sections.append("Response:")
                sections.append("-" * 60)
                sections.append(output.strip())
                sections.append("-" * 60)
                sections.append("")

            # Suggestions
            if suggestions:
                sections.append("Suggestions:")
                for suggestion in suggestions:
                    sections.append(f"  -> {suggestion}")
                sections.append("")

        # Metadata (container_id, project_id)
        if container_id or project_id:
            metadata_parts = []
            if project_id:
                metadata_parts.append(f"Project ID: {project_id}")
            if container_id:
                metadata_parts.append(f"Container ID: {container_id[:12]}")  # Show short ID
            if metadata_parts:
                sections.append("Metadata:")
                for part in metadata_parts:
                    sections.append(f"  {part}")

        result = "\n".join(sections)

        # Add artifact reminder guardrail for success cases with formatted output
        if status == "success" and output:
            needs_artifact = self._should_suggest_artifact(output)
            if needs_artifact:
                artifact_type = self._detect_output_type(output)
                result += f"\n\n{'-' * 60}"
                result += "\n[!] REMINDER: Create an artifact to display this output properly!"
                result += f"\n    Type: {artifact_type}"
                result += "\n    This ensures proper formatting and user experience."
                result += f"\n{'-' * 60}"

        # Enforce character limit
        if len(result) > self.CHARACTER_LIMIT:
            result = self._truncate_to_char_limit(result, self.CHARACTER_LIMIT)

        return result

    def _should_suggest_artifact(self, output: str) -> bool:
        """Determine if output should be displayed in an artifact.

        Args:
            output: The execution output

        Returns:
            True if artifact is recommended
        """
        if not output or not output.strip():
            return False

        output_stripped = output.strip()

        # Detect structured formats FIRST (before length check)
        # JSON
        if (output_stripped.startswith('{') or output_stripped.startswith('[')) and \
           (output_stripped.endswith('}') or output_stripped.endswith(']')):
            return True

        # HTML/SVG
        if output_stripped.startswith('<html') or output_stripped.startswith('<!DOCTYPE') or \
           output_stripped.startswith('<svg'):
            return True

        # XML
        if output_stripped.startswith('<?xml') or (output_stripped.startswith('<') and '>' in output_stripped):
            return True

        # Table indicators
        if any(indicator in output_stripped for indicator in ['|', '─', '═', '┌', '└']):
            return True

        # Multiple lines - needs artifact
        lines = output_stripped.split('\n')
        if len(lines) > 3:
            return True

        # Single short line - no artifact needed
        if len(lines) == 1 and len(lines[0]) < 50:
            return False

        return False

    def _detect_output_type(self, output: str) -> str:
        """Detect the appropriate artifact type for output.

        Args:
            output: The execution output

        Returns:
            Suggested artifact type
        """
        output_stripped = output.strip()

        # JSON
        if (output_stripped.startswith('{') or output_stripped.startswith('[')) and \
           (output_stripped.endswith('}') or output_stripped.endswith(']')):
            return "application/json"

        # HTML/SVG
        if output_stripped.startswith('<html') or output_stripped.startswith('<!DOCTYPE'):
            return "text/html"
        if output_stripped.startswith('<svg'):
            return "text/html (for SVG rendering)"

        # XML
        if output_stripped.startswith('<?xml') or output_stripped.startswith('<'):
            return "text/plain with XML highlighting"

        # Default to text
        return "text/plain"

    def format_json_response(
        self,
        status: str,
        data: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        output: str = "",
    ) -> str:
        """Format response as JSON string with artifact instructions.

        Args:
            status: Response status ("success" or "error")
            data: Response data (for success)
            error: Error details (for error)
            metadata: Optional metadata
            output: Output string to check for artifact requirement (for success cases)

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

        # Add artifact instruction for success cases with formatted output
        if status == "success" and output:
            needs_artifact = self._should_suggest_artifact(output)
            if needs_artifact:
                artifact_type = self._detect_output_type(output)
                response["artifact_instruction"] = {
                    "required": True,
                    "type": artifact_type,
                    "message": "⚠️ CREATE ARTIFACT NOW - This output requires proper formatting",
                }

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
