"""Executor for building and running .NET code in containers."""

import re
from typing import Any

import httpx
from docker.errors import APIError

from src.docker_manager import DockerContainerManager
from src.models import DotNetVersion


class DotNetExecutor:
    """Handles .NET project building and execution in containers."""

    def __init__(self, docker_manager: DockerContainerManager) -> None:
        """Initialize executor with Docker manager.

        Args:
            docker_manager: Docker container manager instance
        """
        self.docker_manager = docker_manager
        self._version_cache: dict[str, str | None] = {}

    async def generate_csproj(self, dotnet_version: DotNetVersion, packages: list[str]) -> str:
        """Generate .csproj file content.

        Args:
            dotnet_version: .NET version to target
            packages: List of NuGet packages (format: "Package" or "Package@version")

        Returns:
            XML content of .csproj file
        """
        tfm = self._version_to_tfm(dotnet_version)

        # Build package references
        package_refs = []
        for pkg in packages:
            name, version = self._parse_package(pkg)

            # If no version specified, try to get latest from NuGet API
            if not version:
                version = await self._get_latest_nuget_version(name)

            if version:
                package_refs.append(
                    f'    <PackageReference Include="{name}" Version="{version}" />'
                )
            else:
                # Fallback: no version (NuGet will use latest but may warn)
                package_refs.append(f'    <PackageReference Include="{name}" />')

        package_section = "\n".join(package_refs) if package_refs else ""

        itemgroup = f"  <ItemGroup>\n{package_section}\n  </ItemGroup>\n" if package_section else ""

        return f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>{tfm}</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
{itemgroup}</Project>
"""

    def build_project(
        self, container_id: str, project_path: str, timeout: int = 30
    ) -> tuple[bool, str, list[str]]:
        """Build .NET project in container.

        Args:
            container_id: Container identifier
            project_path: Path to project directory in container
            timeout: Build timeout in seconds

        Returns:
            Tuple of (success, output, parsed_errors)
        """
        try:
            stdout, stderr, exit_code = self.docker_manager.execute_command(
                container_id=container_id,
                command=["dotnet", "build", project_path],
                timeout=timeout,
            )

            success = exit_code == 0
            output = stdout if stdout else stderr
            errors = self._parse_build_errors(stderr) if not success else []

            return success, output, errors

        except APIError as e:
            return False, "", [f"Build failed: {e}"]

    async def run_snippet(
        self,
        code: str,
        dotnet_version: DotNetVersion,
        packages: list[str],
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Execute C# code snippet.

        Creates project files inside container (no volume mounting), builds and runs code.
        Ensures cleanup of container regardless of outcome.

        Args:
            code: C# code to execute (top-level statements)
            dotnet_version: .NET version to use
            packages: List of NuGet packages
            timeout: Execution timeout in seconds

        Returns:
            Dictionary with keys: success, stdout, stderr, exit_code, build_errors
        """
        container_id = None

        try:
            # Create container (no volume mounting - files will be created inside)
            container_id = self.docker_manager.create_container(
                dotnet_version=dotnet_version.value,
                project_id="snippet",
            )

            # Generate project files content
            project_name = "Snippet"
            csproj_content = await self.generate_csproj(dotnet_version, packages)

            # Write .csproj file inside container (write_file creates parent directories)
            self.docker_manager.write_file(
                container_id=container_id,
                dest_path=f"/workspace/{project_name}/{project_name}.csproj",
                content=csproj_content,
            )

            # Write Program.cs file inside container
            self.docker_manager.write_file(
                container_id=container_id,
                dest_path=f"/workspace/{project_name}/Program.cs",
                content=code,
            )

            # Build project
            build_success, build_output, build_errors = self.build_project(
                container_id=container_id,
                project_path=f"/workspace/{project_name}",
                timeout=timeout,
            )

            if not build_success:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": build_output,
                    "exit_code": 1,
                    "build_errors": build_errors,
                }

            # Run project
            stdout, stderr, exit_code = self.docker_manager.execute_command(
                container_id=container_id,
                command=["dotnet", "run", "--project", f"/workspace/{project_name}"],
                timeout=timeout,
            )

            return {
                "success": exit_code == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "build_errors": [],
            }

        except APIError as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution error: {e}",
                "exit_code": 1,
                "build_errors": [],
            }

        finally:
            # Cleanup container
            if container_id:
                self.docker_manager.stop_container(container_id)

    def _version_to_tfm(self, version: DotNetVersion) -> str:
        """Convert DotNetVersion to target framework moniker.

        Args:
            version: .NET version enum value

        Returns:
            Target framework moniker (e.g., "net8.0")
        """
        mapping = {
            DotNetVersion.V8: "net8.0",
            DotNetVersion.V9: "net9.0",
            DotNetVersion.V10: "net10.0",
        }
        return mapping[version]

    def _parse_package(self, package: str) -> tuple[str, str | None]:
        """Parse package string into name and version.

        Args:
            package: Package string ("Name" or "Name@version")

        Returns:
            Tuple of (package_name, version or None)
        """
        if "@" in package:
            name, version = package.split("@", 1)
            return name, version
        return package, None

    async def _get_latest_nuget_version(self, package_name: str) -> str | None:
        """Get latest stable version of a package from NuGet API.

        Args:
            package_name: NuGet package name

        Returns:
            Latest stable version string, or None if not found/error
        """
        # Check cache first
        if package_name in self._version_cache:
            return self._version_cache[package_name]

        try:
            url = f"https://api.nuget.org/v3-flatcontainer/{package_name.lower()}/index.json"

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    self._version_cache[package_name] = None
                    return None

                data = response.json()
                versions: list[str] = data.get("versions", [])

                # Filter out pre-release versions (contain -, like "3.0.0-beta")
                stable_versions: list[str] = [v for v in versions if "-" not in v]

                if not stable_versions:
                    self._version_cache[package_name] = None
                    return None

                # Get latest stable version (last in list)
                latest: str = stable_versions[-1]
                self._version_cache[package_name] = latest
                return latest

        except Exception:
            # Network error, timeout, invalid JSON, etc.
            # Cache None to avoid repeated failures
            self._version_cache[package_name] = None
            return None

    def _parse_build_errors(self, stderr: str) -> list[str]:
        """Parse MSBuild error output into structured list.

        Args:
            stderr: Build error output

        Returns:
            List of error messages
        """
        errors = []

        # Pattern: File.cs(line,col): error CODE: message
        error_pattern = r"^.*?\(\d+,\d+\): error (CS\d+):.*$"

        for line in stderr.splitlines():
            line = line.strip()
            if re.search(error_pattern, line):
                errors.append(line)

        return errors
