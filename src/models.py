"""Pydantic models for input validation and data structures."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
