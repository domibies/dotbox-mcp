"""Pydantic models for input validation and data structures."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
        description=".NET version: '8', '9', or '10-rc2'",
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

    @field_validator("packages")
    @classmethod
    def validate_packages(cls, v: list[str]) -> list[str]:
        """Validate package names."""
        for pkg in v:
            if not pkg or len(pkg) > 100:
                raise ValueError(f"Invalid package name: {pkg!r}")
        return v
