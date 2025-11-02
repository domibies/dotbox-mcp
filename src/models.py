"""Pydantic models for input validation and data structures."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Type aliases for .NET versions and detail levels
DotNetVersionLiteral = Literal["8", "9", "10-rc2"]
DetailLevelLiteral = Literal["concise", "full"]


class DotNetVersion(str, Enum):
    """.NET SDK version selector."""

    V8 = "8"
    V9 = "9"
    V10_RC2 = "10-rc2"


class DetailLevel(str, Enum):
    """Output detail level for responses."""

    CONCISE = "concise"
    FULL = "full"


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


class ExecuteSnippetInput(BaseModel):
    """Input model for executing a C# code snippet."""

    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(
        ...,
        description="C# code to execute (supports top-level statements)",
        min_length=1,
        max_length=50000,
    )
    dotnet_version: DotNetVersion = Field(
        default=DotNetVersion.V8,
        description=".NET version: 8, 9, or '10-rc2' (accepts integer or string)",
    )
    packages: list[str] = Field(
        default_factory=list,
        description="NuGet packages to include (e.g., ['Newtonsoft.Json', 'Dapper'])",
        max_length=20,
    )
    detail_level: DetailLevel = Field(
        default=DetailLevel.CONCISE,
        description="Output detail: 'concise' (first 50 lines) or 'full' (complete output)",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )

    @field_validator("dotnet_version", mode="before")
    @classmethod
    def coerce_dotnet_version(cls, v: DotNetVersion | str | int) -> str:
        """Convert integer version to string (for MCP JSON deserialization)."""
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            return v
        return v.value if hasattr(v, "value") else str(v)

    @field_validator("packages")
    @classmethod
    def validate_packages(cls, v: list[str]) -> list[str]:
        """Validate package names."""
        for pkg in v:
            if not pkg or len(pkg) > 100:
                raise ValueError(f"Invalid package name: {pkg!r}")
        return v

    @classmethod
    def model_json_schema(cls, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        """Override JSON schema to accept integer or string for dotnet_version."""
        schema = super().model_json_schema(**kwargs)
        # Replace dotnet_version schema to accept both int and string
        schema["properties"]["dotnet_version"] = {
            "anyOf": [
                {"type": "integer", "enum": [8, 9, 10]},
                {"type": "string", "enum": ["8", "9", "10-rc2"]},
            ],
            "default": "8",
            "description": ".NET version: 8, 9, or '10-rc2' (accepts integer or string)",
        }
        return schema


class StartContainerInput(BaseModel):
    """Input model for starting a persistent container."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str | None = Field(
        default=None,
        description="Project identifier (auto-generated if not provided: dotnet{version}-proj-{random})",
        pattern=r"^[a-zA-Z0-9_-]+$",
        min_length=1,
        max_length=50,
    )
    dotnet_version: DotNetVersion = Field(
        default=DotNetVersion.V8,
        description=".NET version: 8, 9, or '10-rc2' (accepts integer or string)",
    )
    ports: dict[int, int] | None = Field(
        default=None,
        description="Port mapping {container_port: host_port}. Use 0 for auto-assignment (e.g., {5000: 0} auto-assigns host port). Container port cannot be 0.",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )

    @field_validator("dotnet_version", mode="before")
    @classmethod
    def coerce_dotnet_version(cls, v: DotNetVersion | str | int) -> str:
        """Convert integer version to string (for MCP JSON deserialization)."""
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            return v
        return v.value if hasattr(v, "value") else str(v)

    @field_validator("ports", mode="before")
    @classmethod
    def coerce_port_keys(cls, v: Any) -> dict[int, int] | None:
        """Convert string keys to integer keys (for MCP JSON deserialization).

        MCP clients send JSON where object keys are always strings.
        This validator accepts {"5000": 8080} and converts to {5000: 8080}.

        Also handles Claude Desktop bug where ports are double-JSON-encoded as strings.

        Examples:
            {"5000": 8080} → {5000: 8080}
            {"5000": "0"} → {5000: 0}
            '{"5000": 8080}' → {5000: 8080}  (Claude Desktop double-encoding bug)
            {"5000": 8080, "5001": 8081} → {5000: 8080, 5001: 8081}

        Raises:
            ValueError: If port mapping format is invalid or values cannot be converted to integers.
        """
        if v is None:
            return v

        # Handle Claude Desktop bug: ports sent as JSON-encoded string
        # Example: '{"5000": 8080}' instead of {"5000": 8080}
        if isinstance(v, str):
            import json

            try:
                v = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Port mapping string is not valid JSON. "
                    f"Got: {v!r}. "
                    f"Expected object format like {{'5000': 8080}} not a JSON string"
                ) from e

        if not isinstance(v, dict):
            raise ValueError(
                f"Port mapping must be a dictionary, got {type(v).__name__}. "
                f"Example: {{'5000': 8080}} or {{5000: 0}} for auto-assignment"
            )

        try:
            # Convert both keys and values to integers
            result = {}
            for key, value in v.items():
                int_key = int(key)
                int_value = int(value)
                result[int_key] = int_value
            return result
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Port mapping keys and values must be integers. "
                f"Got: {v!r}. "
                f"Examples:\n"
                f"  - Specific port: {{'5000': 8080}} (container 5000 → host 8080)\n"
                f"  - Auto-assign: {{'5000': 0}} (container 5000 → random host port)\n"
                f"  - Multiple: {{'5000': 8080, '5001': 8081}}"
            ) from e

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, v: dict[int, int] | None) -> dict[int, int] | None:
        """Validate port mapping ranges."""
        if v is None:
            return v

        for container_port, host_port in v.items():
            # Container port cannot be 0 (reserved)
            if container_port <= 0:
                raise ValueError(
                    f"Container port must be between 1-65535, got {container_port}. "
                    f"Port 0 is reserved by the system. Use ports like 5000, 8080, etc."
                )
            if container_port > 65535:
                raise ValueError(
                    f"Container port must be between 1-65535, got {container_port}. "
                    f"Maximum valid port number is 65535."
                )

            # Host port can be 0 (auto-assign) or 1-65535
            if host_port < 0:
                raise ValueError(
                    f"Host port must be 0 (auto-assign) or between 1-65535, got {host_port}. "
                    f"Use 0 to let Docker assign an available port automatically."
                )
            if host_port > 65535:
                raise ValueError(
                    f"Host port must be 0 (auto-assign) or between 1-65535, got {host_port}. "
                    f"Maximum valid port number is 65535."
                )

        return v

    @model_validator(mode="after")
    def generate_project_id_if_needed(self) -> "StartContainerInput":
        """Auto-generate project_id if not provided."""
        if self.project_id is None:
            import secrets

            # Get version string from dotnet_version
            version_str = self.dotnet_version.value
            random_suffix = secrets.token_hex(3)  # 6 chars
            self.project_id = f"dotnet{version_str}-proj-{random_suffix}"
        return self

    @classmethod
    def model_json_schema(cls, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        """Override JSON schema to accept integer or string for dotnet_version and string keys for ports."""
        schema = super().model_json_schema(**kwargs)

        # Replace dotnet_version schema to accept both int and string
        schema["properties"]["dotnet_version"] = {
            "anyOf": [
                {"type": "integer", "enum": [8, 9, 10]},
                {"type": "string", "enum": ["8", "9", "10-rc2"]},
            ],
            "default": "8",
            "description": ".NET version: 8, 9, or '10-rc2' (accepts integer or string)",
        }

        # Override ports schema to accept:
        # 1. Object with string/integer keys and values (normal case)
        # 2. String (Claude Desktop bug - double-encodes as JSON string)
        # 3. Null (optional parameter)
        schema["properties"]["ports"] = {
            "anyOf": [
                {
                    "type": "object",
                    "additionalProperties": {"anyOf": [{"type": "integer"}, {"type": "string"}]},
                    "description": "Port mapping object. Example: {'5000': 8080}",
                },
                {
                    "type": "string",
                    "description": "Port mapping as JSON string (Claude Desktop workaround). Example: '{\"5000\": 8080}'",
                },
                {"type": "null"},
            ],
            "default": None,
            "description": "Port mapping {container_port: host_port}. Use 0 for auto-assignment (e.g., {5000: 0} auto-assigns host port). Container port cannot be 0.",
        }

        return schema


class StopContainerInput(BaseModel):
    """Input model for stopping a container."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(
        ...,
        description="Project identifier to find and stop the associated container",
        min_length=1,
        max_length=50,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )


class WriteFileInput(BaseModel):
    """Input model for writing a file to a container."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(
        ...,
        description="Project identifier for the container",
        min_length=1,
        max_length=50,
    )
    path: str = Field(
        ...,
        description="File path inside container (e.g., /workspace/Program.cs)",
        min_length=1,
        max_length=500,
    )
    content: str = Field(
        ...,
        description="File content to write",
        min_length=0,
        max_length=100000,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate file path is absolute and within workspace."""
        if not v.startswith("/workspace/"):
            raise ValueError("Path must start with /workspace/ for security")
        if ".." in v:
            raise ValueError("Path cannot contain '..' (directory traversal)")
        return v


class ReadFileInput(BaseModel):
    """Input model for reading a file from a container."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(
        ...,
        description="Project identifier for the container",
        min_length=1,
        max_length=50,
    )
    path: str = Field(
        ...,
        description="File path inside container (e.g., /workspace/Program.cs)",
        min_length=1,
        max_length=500,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate file path is absolute and within workspace."""
        if not v.startswith("/workspace/"):
            raise ValueError("Path must start with /workspace/ for security")
        if ".." in v:
            raise ValueError("Path cannot contain '..' (directory traversal)")
        return v


class ListFilesInput(BaseModel):
    """Input model for listing files in a container directory."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(
        ...,
        description="Project identifier for the container",
        min_length=1,
        max_length=50,
    )
    path: str = Field(
        default="/workspace",
        description="Directory path inside container (default: /workspace)",
        min_length=1,
        max_length=500,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate directory path is absolute and within workspace."""
        if not v.startswith("/workspace"):
            raise ValueError("Path must start with /workspace for security")
        if ".." in v:
            raise ValueError("Path cannot contain '..' (directory traversal)")
        return v


class ExecuteCommandInput(BaseModel):
    """Input model for executing a command in a container."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(
        ...,
        description="Project identifier for the container",
        min_length=1,
        max_length=50,
    )
    command: list[str] = Field(
        ...,
        description="Command to execute as list of arguments (e.g., ['dotnet', 'build'])",
        min_length=1,
        max_length=50,
    )
    timeout: int = Field(
        default=30,
        description="Execution timeout in seconds (default: 30)",
        ge=1,
        le=300,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: list[str]) -> list[str]:
        """Validate command list."""
        if not v:
            raise ValueError("Command cannot be empty")
        for arg in v:
            if not arg or len(arg) > 1000:
                raise ValueError(f"Invalid command argument: {arg!r}")
        return v


class RunBackgroundInput(BaseModel):
    """Input model for running a command in background (long-running processes)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(
        ...,
        description="Project identifier for the container",
        min_length=1,
        max_length=50,
    )
    command: list[str] = Field(
        ...,
        description="Command to run in background (e.g., ['dotnet', 'run', '--project', '/workspace/MyApp'])",
        min_length=1,
        max_length=50,
    )
    wait_for_ready: int = Field(
        default=5,
        description="Seconds to wait for process to start before returning (default: 5)",
        ge=0,
        le=60,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: list[str]) -> list[str]:
        """Validate command list."""
        if not v:
            raise ValueError("Command cannot be empty")
        for arg in v:
            if not arg or len(arg) > 1000:
                raise ValueError(f"Invalid command argument: {arg!r}")
        return v


class TestEndpointInput(BaseModel):
    """Input model for testing HTTP endpoints."""

    model_config = ConfigDict(str_strip_whitespace=True)

    url: str = Field(
        ...,
        description="Full URL to test (e.g., http://localhost:8080/api/health)",
        min_length=1,
        max_length=500,
    )
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = Field(
        default="GET",
        description="HTTP method (default: GET)",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Optional HTTP headers (e.g., {'Content-Type': 'application/json'})",
    )
    body: str | None = Field(
        default=None,
        description="Optional request body (JSON string or plain text)",
        max_length=10000,
    )
    timeout: int = Field(
        default=30,
        description="Request timeout in seconds (default: 30)",
        ge=1,
        le=300,
    )
    detail_level: DetailLevel = Field(
        default=DetailLevel.CONCISE,
        description="Output detail: 'concise' (body only) or 'full' (headers + body)",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class GetLogsInput(BaseModel):
    """Input model for retrieving container logs."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(
        ...,
        description="Project identifier for the container",
        min_length=1,
        max_length=50,
    )
    tail: int = Field(
        default=50,
        description="Number of lines to retrieve from end of logs (default: 50)",
        ge=1,
        le=1000,
    )
    since: int | None = Field(
        default=None,
        description="Only return logs since this many seconds ago (optional)",
        ge=1,
        le=3600,
    )
    detail_level: DetailLevel = Field(
        default=DetailLevel.CONCISE,
        description="Output detail: 'concise' (first 50 lines) or 'full' (complete logs)",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )


class KillProcessInput(BaseModel):
    """Input model for killing background processes in a container."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(
        ...,
        description="Project identifier for the container",
        min_length=1,
        max_length=50,
    )
    process_pattern: str | None = Field(
        default=None,
        description="Process pattern to kill (e.g., 'dotnet run'). If not specified, kills all background dotnet processes.",
        max_length=200,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )


class ListContainersInput(BaseModel):
    """Input model for listing all managed containers.

    No parameters required - lists all active containers managed by this MCP server.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable, default) or 'json' (structured data)",
    )
