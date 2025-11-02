"""Output formatting utilities for MCP responses."""

import json
from typing import Any

from src.models import DetailLevel


class MarkdownFormatter:
    """Formats responses in human-readable Markdown."""

    @staticmethod
    def format_header(status: str, title: str) -> str:
        """Format result header with status indicator.

        Examples:
            format_header("success", "Execution Result")
            → "# Execution Result ✓"

            format_header("error", "Build Failed")
            → "# Build Failed ✗"

        Args:
            status: Status type ("success" or "error")
            title: Header title text

        Returns:
            Formatted header string
        """
        indicator = "✓" if status == "success" else "✗"
        return f"# {title} {indicator}"

    @staticmethod
    def format_metadata(items: dict[str, str]) -> str:
        """Format key-value metadata.

        Example:
            format_metadata({"Runtime": ".NET 8.0.0", "Container": "abc123"})
            → "**Runtime:** .NET 8.0.0\n**Container:** abc123"

        Args:
            items: Dictionary of metadata key-value pairs

        Returns:
            Formatted metadata string
        """
        lines = [f"**{key}:** {value}" for key, value in items.items()]
        return "\n".join(lines)

    @staticmethod
    def format_code_block(content: str, language: str = "") -> str:
        """Format code block with optional syntax highlighting.

        Args:
            content: Code content to format
            language: Optional language identifier (e.g., "csharp", "json")

        Returns:
            Formatted code block
        """
        return f"```{language}\n{content}\n```"

    @staticmethod
    def format_section(title: str, content: str) -> str:
        """Format section with header.

        Args:
            title: Section title
            content: Section content

        Returns:
            Formatted section
        """
        return f"## {title}\n\n{content}"

    @staticmethod
    def format_error_list(errors: list[str]) -> str:
        """Format errors as Markdown list.

        Args:
            errors: List of error messages

        Returns:
            Formatted error list
        """
        return "\n\n".join(f"**{err}**" for err in errors[:10])

    @staticmethod
    def format_suggestions(suggestions: list[str]) -> str:
        """Format suggestions as bulleted list.

        Args:
            suggestions: List of suggestion strings

        Returns:
            Formatted bulleted list
        """
        items = [f"- {s}" for s in suggestions]
        return "\n".join(items)


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

        # Enforce character limit
        if len(result) > self.CHARACTER_LIMIT:
            result = self._truncate_to_char_limit(result, self.CHARACTER_LIMIT)

        return result


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

    def format_execution_result_markdown(
        self,
        status: str,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        dotnet_version: str = "",
        execution_time_ms: int = 0,
        detail_level: DetailLevel = DetailLevel.CONCISE,
    ) -> str:
        """Format execution result as Markdown.

        Args:
            status: Status ("success" or "error")
            stdout: Standard output
            stderr: Standard error
            exit_code: Process exit code
            dotnet_version: .NET version string
            execution_time_ms: Execution time in milliseconds
            detail_level: Output detail level

        Returns:
            Markdown-formatted result
        """
        sections = []

        # Header
        title = "Execution Result" if status == "success" else "Execution Failed"
        sections.append(MarkdownFormatter.format_header(status, title))
        sections.append("")

        # Metadata
        metadata = {}
        if dotnet_version:
            metadata["Runtime"] = f".NET {dotnet_version} ({execution_time_ms/1000:.1f}s)"
        if exit_code != 0:
            metadata["Exit Code"] = str(exit_code)
        if metadata:
            sections.append(MarkdownFormatter.format_metadata(metadata))
            sections.append("")

        # Apply detail level
        if detail_level == DetailLevel.CONCISE:
            stdout = self._truncate_to_first_n_lines(stdout, 50)
            stderr = self._truncate_to_first_n_lines(stderr, 50)

        # Output section
        if stdout.strip():
            sections.append(MarkdownFormatter.format_section(
                "Output",
                MarkdownFormatter.format_code_block(stdout.strip())
            ))
            sections.append("")

        # Error section
        if stderr.strip():
            sections.append(MarkdownFormatter.format_section(
                "Error Output",
                MarkdownFormatter.format_code_block(stderr.strip())
            ))
            sections.append("")

        # Footer
        if status == "success":
            sections.append("---")
            sections.append("*C# code executed successfully*")

        result = "\n".join(sections)

        # Enforce character limit
        if len(result) > self.CHARACTER_LIMIT:
            result = self._truncate_to_char_limit(result, self.CHARACTER_LIMIT)

        return result

    def format_build_error_markdown(
        self,
        errors: list[str],
        suggestions: list[str],
        dotnet_version: str = "",
        execution_time_ms: int = 0,
    ) -> str:
        """Format build errors as Markdown.

        Args:
            errors: List of build error messages
            suggestions: List of suggestion strings
            dotnet_version: .NET version string
            execution_time_ms: Build time in milliseconds

        Returns:
            Markdown-formatted build error
        """
        sections = []

        # Header
        sections.append(MarkdownFormatter.format_header("error", "Build Failed"))
        sections.append("")

        # Metadata
        if dotnet_version:
            sections.append(MarkdownFormatter.format_metadata({
                "Runtime": f".NET {dotnet_version} ({execution_time_ms/1000:.1f}s)"
            }))
            sections.append("")

        # Errors
        if errors:
            sections.append(MarkdownFormatter.format_section(
                "Errors",
                MarkdownFormatter.format_error_list(errors)
            ))
            sections.append("")

        # Suggestions
        if suggestions:
            sections.append(MarkdownFormatter.format_section(
                "Suggestions",
                MarkdownFormatter.format_suggestions(suggestions)
            ))

        return "\n".join(sections)

    def format_error_markdown(
        self,
        title: str,
        error_message: str,
        error_details: str = "",
        output: str = "",
        suggestions: list[str] | None = None,
        metadata: dict[str, str] | None = None,
        errors: list[str] | None = None,
        detail_level: DetailLevel = DetailLevel.CONCISE,
    ) -> str:
        """Format generic error response in Markdown.

        Args:
            title: Error title
            error_message: Main error message
            error_details: Detailed error information (stack traces, etc.)
            output: Output before crash or error response body
            suggestions: List of suggestions
            metadata: Metadata key-value pairs
            errors: List of multiple errors (for build errors)
            detail_level: Output detail level

        Returns:
            Markdown-formatted error
        """
        sections = []

        # Header
        sections.append(f"# {title} ✗")
        sections.append("")

        # Metadata
        if metadata:
            sections.append(MarkdownFormatter.format_metadata(metadata))
            sections.append("")

        # Multiple errors (build errors)
        if errors:
            error_list = errors[:10] if detail_level == DetailLevel.CONCISE else errors
            sections.append("## Errors")
            sections.append("")
            sections.append(MarkdownFormatter.format_error_list(error_list))
            sections.append("")

            if len(errors) > 10 and detail_level == DetailLevel.CONCISE:
                sections.append(f"*... and {len(errors) - 10} more errors. Use `detail_level='full'` to see all.*")
                sections.append("")

        # Single error message
        elif error_message:
            sections.append("## Error")
            sections.append("")
            sections.append(error_message)
            sections.append("")

        # Error details (stack traces, technical info)
        if error_details:
            sections.append("## Details")
            sections.append("")
            sections.append(MarkdownFormatter.format_code_block(error_details))
            sections.append("")

        # Output (partial output before crash, or error response body)
        if output.strip():
            output_title = "Output (before crash)" if "crash" in title.lower() else "Response"
            sections.append(f"## {output_title}")
            sections.append("")

            if detail_level == DetailLevel.CONCISE:
                output = self._truncate_to_first_n_lines(output, 20)

            # Try to format as JSON if it looks like JSON
            if output.strip().startswith("{"):
                sections.append(MarkdownFormatter.format_code_block(output, "json"))
            else:
                sections.append(MarkdownFormatter.format_code_block(output))
            sections.append("")

        # Suggestions (always show if available)
        if suggestions:
            sections.append("## Suggestions")
            sections.append("")
            sections.append(MarkdownFormatter.format_suggestions(suggestions))

        return "\n".join(sections)

    def format_container_info_markdown(
        self,
        project_id: str,
        container_id: str,
        dotnet_version: str = "",
        ports: dict[int, int] | None = None,
        urls: list[str] | None = None,
        status: str = "success",
        message: str = "",
    ) -> str:
        """Format container information as Markdown.

        Args:
            project_id: Project identifier
            container_id: Docker container ID
            dotnet_version: .NET version string
            ports: Port mappings
            urls: List of accessible URLs
            status: Status ("success" or "error")
            message: Additional status message

        Returns:
            Markdown-formatted container info
        """
        sections = []

        # Header
        title = "Container Started" if status == "success" else "Container Status"
        sections.append(MarkdownFormatter.format_header(status, title))
        sections.append("")

        # Metadata
        metadata = {}
        if project_id:
            metadata["Project"] = project_id
        if container_id:
            metadata["Container"] = container_id[:12]  # Short ID
        if dotnet_version:
            metadata["Runtime"] = f".NET {dotnet_version}"
        if metadata:
            sections.append(MarkdownFormatter.format_metadata(metadata))
            sections.append("")

        # URLs (if provided)
        if urls:
            sections.append("## Access URLs")
            sections.append("")
            for url in urls:
                sections.append(url)
            sections.append("")
            sections.append("---")
            sections.append("*Each URL on its own line for clickability*")

        # Message
        if message:
            sections.append("")
            sections.append(message)

        return "\n".join(sections)

    def format_endpoint_response_markdown(
        self,
        method: str,
        url: str,
        status_code: int,
        response_body: str = "",
        response_headers: dict[str, str] | None = None,
        response_time_ms: int = 0,
        error_message: str = "",
        detail_level: DetailLevel = DetailLevel.CONCISE,
    ) -> str:
        """Format HTTP endpoint test response as Markdown.

        Args:
            method: HTTP method
            url: Request URL
            status_code: HTTP status code
            response_body: Response body
            response_headers: Response headers
            response_time_ms: Response time in milliseconds
            error_message: Error message if request failed
            detail_level: Output detail level

        Returns:
            Markdown-formatted endpoint response
        """
        sections = []

        # Determine success/error
        status = "success" if 200 <= status_code < 400 else "error"

        # Extract path from URL for cleaner display
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path or "/"

        # Status code text
        status_text = {
            200: "OK", 201: "Created", 204: "No Content",
            400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
            404: "Not Found", 500: "Internal Server Error", 503: "Service Unavailable"
        }.get(status_code, "")

        # Header
        title = f"{method} {path} → {status_code} {status_text}".strip()
        sections.append(MarkdownFormatter.format_header(status, title))
        sections.append("")

        # Metadata
        metadata = {"Response Time": f"{response_time_ms}ms"}
        sections.append(MarkdownFormatter.format_metadata(metadata))
        sections.append("")

        # Headers (only in full detail mode)
        if response_headers and detail_level == DetailLevel.FULL:
            header_lines = "\n".join(f"{k}: {v}" for k, v in response_headers.items())
            sections.append(MarkdownFormatter.format_section(
                "Headers",
                MarkdownFormatter.format_code_block(header_lines)
            ))
            sections.append("")

        # Response body
        if response_body.strip():
            if detail_level == DetailLevel.CONCISE:
                response_body = self._truncate_to_first_n_lines(response_body, 20)

            # Try to format as JSON if it looks like JSON
            if response_body.strip().startswith("{") or response_body.strip().startswith("["):
                sections.append(MarkdownFormatter.format_section(
                    "Response",
                    MarkdownFormatter.format_code_block(response_body, "json")
                ))
            else:
                sections.append(MarkdownFormatter.format_section(
                    "Response",
                    MarkdownFormatter.format_code_block(response_body)
                ))
            sections.append("")

        # Error message (if any)
        if error_message:
            sections.append("## Error")
            sections.append("")
            sections.append(error_message)

        return "\n".join(sections)

    def format_logs_markdown(
        self,
        project_id: str,
        logs: str,
        tail: int = 50,
        detail_level: DetailLevel = DetailLevel.CONCISE,
    ) -> str:
        """Format container logs as Markdown.

        Args:
            project_id: Project identifier
            logs: Log content
            tail: Number of lines retrieved
            detail_level: Output detail level

        Returns:
            Markdown-formatted logs
        """
        sections = []

        # Header
        sections.append(MarkdownFormatter.format_header("success", "Container Logs"))
        sections.append("")

        # Metadata
        metadata = {"Project": project_id, "Lines": str(tail)}
        sections.append(MarkdownFormatter.format_metadata(metadata))
        sections.append("")

        # Logs
        if logs.strip():
            if detail_level == DetailLevel.CONCISE:
                logs = self._truncate_to_first_n_lines(logs, 50)

            sections.append(MarkdownFormatter.format_section(
                "Logs",
                MarkdownFormatter.format_code_block(logs.strip())
            ))
        else:
            sections.append("*No logs available*")

        return "\n".join(sections)
