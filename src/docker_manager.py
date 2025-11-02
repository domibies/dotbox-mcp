"""Docker container management for .NET sandboxes."""

import os
import sys
import time
import uuid
from dataclasses import dataclass

from docker.errors import APIError, DockerException, ImageNotFound, NotFound

import docker


@dataclass
class ContainerInfo:
    """Information about a running container."""

    container_id: str
    name: str
    project_id: str
    status: str
    ports: dict[str, str]


class DockerContainerManager:
    """Manages Docker containers for .NET sandboxes."""

    LABEL_MANAGED_BY = "dotbox-mcp"
    MEMORY_LIMIT = "512m"  # 512 MB
    CPU_PERIOD = 100000  # 100ms
    CPU_QUOTA = 50000  # 50% of one CPU core

    def __init__(self) -> None:
        """Initialize Docker client.

        Raises:
            DockerException: If Docker is not available
        """
        try:
            self.client = docker.from_env()
            self.client.ping()  # type: ignore[no-untyped-call]  # Verify connection
        except DockerException as e:
            raise DockerException(f"Docker is not available: {e}") from e

        # Track last activity timestamp for each container (for idle cleanup)
        self.last_activity: dict[str, float] = {}

        # Configure image registry (allow override for local development)
        self.sandbox_registry = os.getenv(
            "DOTBOX_SANDBOX_REGISTRY", "ghcr.io/domibies/dotbox-mcp/dotnet-sandbox"
        )

    def _get_image_name(self, dotnet_version: str) -> str:
        """Get full image name with registry prefix.

        Args:
            dotnet_version: .NET version (8, 9, 10-rc2)

        Returns:
            Full image name (e.g., "ghcr.io/.../dotnet-sandbox:8")
        """
        if self.sandbox_registry == "local":
            # Local development: use locally built images
            return f"dotnet-sandbox:{dotnet_version}"
        else:
            # Production: use registry images
            return f"{self.sandbox_registry}:{dotnet_version}"

    def _ensure_image_exists(self, dotnet_version: str) -> None:
        """Ensure sandbox image exists locally, pulling if necessary.

        Args:
            dotnet_version: .NET version (8, 9, 10-rc2)

        Raises:
            RuntimeError: If image cannot be pulled or found
        """
        image_name = self._get_image_name(dotnet_version)

        try:
            # Check if image exists locally
            self.client.images.get(image_name)
            # Image found, no action needed
        except ImageNotFound:
            # Image not found, attempt to pull
            if self.sandbox_registry != "local":
                print(
                    f"Sandbox image not found locally, pulling {image_name}...",
                    file=sys.stderr,
                )
                try:
                    self.client.images.pull(image_name)
                    print(f"Successfully pulled {image_name}", file=sys.stderr)
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to pull sandbox image '{image_name}'. "
                        f"Error: {e}. "
                        f"Ensure Docker is running and you have internet access."
                    ) from e
            else:
                # Local mode but image not found
                raise RuntimeError(
                    f"Sandbox image '{image_name}' not found locally. "
                    f"Build it with: cd docker && ./build-images.sh"
                ) from None

    def create_container(
        self,
        dotnet_version: str,
        project_id: str,
        port_mapping: dict[int, int] | None = None,
    ) -> str:
        """Create and start a container without volume mounting (files live in container only).

        Args:
            dotnet_version: .NET version (8, 9, 10-rc2)
            project_id: Project identifier for labeling
            port_mapping: Optional port mapping {container_port: host_port}

        Returns:
            Container ID

        Raises:
            APIError: If container creation fails
        """
        # Ensure sandbox image exists (pull if necessary)
        self._ensure_image_exists(dotnet_version)

        # Generate human-readable container name
        short_id = str(uuid.uuid4())[:8]
        container_name = f"dotnet{dotnet_version}-{project_id}-{short_id}"

        # Get full image name (registry or local)
        image = self._get_image_name(dotnet_version)

        # Configure labels
        labels = {
            "managed-by": self.LABEL_MANAGED_BY,
            "project-id": project_id,
            "dotnet-version": dotnet_version,
            "created-at": str(int(time.time())),  # For fallback idle cleanup
        }

        # Configure ports
        ports = {}
        if port_mapping:
            for container_port, host_port in port_mapping.items():
                ports[container_port] = host_port

        # Create and start container (no volume mounting - files live in container only)
        try:
            container = self.client.containers.run(  # type: ignore[call-overload]
                image=image,
                name=container_name,
                detach=True,
                labels=labels,
                ports=ports,
                mem_limit=self.MEMORY_LIMIT,
                cpu_period=self.CPU_PERIOD,
                cpu_quota=self.CPU_QUOTA,
                working_dir="/workspace",
                remove=False,  # Don't auto-remove, we'll manage cleanup
            )
            container_id = str(container.id)

            # Track initial activity
            self._update_activity(container_id)

            return container_id
        except APIError as e:
            # Clean up orphaned container if it was created but failed to start
            # This commonly happens with port conflicts - Docker creates the container
            # but fails during the start phase when binding ports
            try:
                failed_container = self.client.containers.get(container_name)
                failed_container.remove(force=True)
            except Exception:
                pass  # Container might not exist, which is fine

            # Re-raise the original error with context
            raise APIError(f"Failed to create container: {e}") from e

    def execute_command(
        self,
        container_id: str,
        command: list[str],
        timeout: int = 30,
    ) -> tuple[str, str, int]:
        """Execute command in container and return output.

        Args:
            container_id: Container identifier
            command: Command to execute as list of strings
            timeout: Maximum execution time in seconds

        Returns:
            Tuple of (stdout, stderr, exit_code)

        Raises:
            APIError: If command execution fails
        """
        try:
            # Update activity timestamp before execution
            self._update_activity(container_id)

            container = self.client.containers.get(container_id)

            # Execute command
            result = container.exec_run(
                cmd=command,
                stdout=True,
                stderr=True,
                demux=False,  # Don't separate stdout/stderr
            )

            # Decode output
            output = result.output.decode("utf-8") if result.output else ""

            # For simplicity, if exit code is 0, treat as stdout, else stderr
            if result.exit_code == 0:
                return output, "", result.exit_code
            else:
                return "", output, result.exit_code

        except NotFound as e:
            raise APIError(f"Container not found: {container_id}") from e
        except APIError as e:
            raise APIError(f"Command execution failed: {e}") from e

    def stop_container(self, container_id: str) -> None:
        """Stop and remove a container.

        This operation is idempotent - if container doesn't exist, no error is raised.

        Args:
            container_id: Container identifier
        """
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=10)
            container.remove()
            # Remove from activity tracking
            if container_id in self.last_activity:
                del self.last_activity[container_id]
        except NotFound:
            # Container already removed - this is fine (idempotent)
            # Also remove from tracking if present
            if container_id in self.last_activity:
                del self.last_activity[container_id]
        except APIError as e:
            # Log but don't raise - best effort cleanup
            print(f"Warning: Failed to stop container {container_id}: {e}")

    def list_containers(self) -> list[ContainerInfo]:
        """List all active sandbox containers.

        Returns:
            List of ContainerInfo objects
        """
        try:
            # Get all containers with our label
            containers = self.client.containers.list(
                filters={"label": f"managed-by={self.LABEL_MANAGED_BY}"}
            )

            result = []
            for container in containers:
                # Extract port mapping
                ports_dict = {}
                network_settings = container.attrs.get("NetworkSettings", {})
                ports_data = network_settings.get("Ports", {})
                if ports_data:
                    for container_port, host_bindings in ports_data.items():
                        if host_bindings:
                            host_port = host_bindings[0].get("HostPort", "")
                            if host_port:
                                ports_dict[container_port] = host_port

                info = ContainerInfo(
                    container_id=container.id,
                    name=container.name,
                    project_id=container.labels.get("project-id", "unknown"),
                    status=container.status,
                    ports=ports_dict,
                )
                result.append(info)

            return result

        except APIError as e:
            raise APIError(f"Failed to list containers: {e}") from e

    def cleanup_all(self) -> int:
        """Stop and remove all sandbox containers.

        Returns:
            Number of containers cleaned up
        """
        containers = self.client.containers.list(
            filters={"label": f"managed-by={self.LABEL_MANAGED_BY}"}
        )

        count = 0
        for container in containers:
            try:
                container.stop(timeout=10)
                container.remove()
                count += 1
                # Remove from activity tracking
                if container.id in self.last_activity:
                    del self.last_activity[container.id]
            except APIError as e:
                print(f"Warning: Failed to cleanup container {container.id}: {e}")

        return count

    def get_container_by_project_id(self, project_id: str) -> str | None:
        """Find running container for a project.

        Args:
            project_id: Project identifier

        Returns:
            Container ID if found, None otherwise
        """
        try:
            containers = self.client.containers.list(
                filters={
                    "label": [
                        f"managed-by={self.LABEL_MANAGED_BY}",
                        f"project-id={project_id}",
                    ]
                }
            )

            if containers:
                return str(containers[0].id)
            return None

        except APIError:
            return None

    def _update_activity(self, container_id: str) -> None:
        """Update last activity timestamp for a container.

        Args:
            container_id: Container identifier
        """
        self.last_activity[container_id] = time.time()

    def _lazy_cleanup(self, idle_timeout_minutes: int = 30) -> int:
        """Clean up idle containers (called on each tool invocation).

        Removes containers that have been idle for longer than idle_timeout_minutes.
        Falls back to creation time if activity tracking is not available.

        Args:
            idle_timeout_minutes: Idle timeout in minutes (default: 30)

        Returns:
            Number of containers cleaned up
        """
        current_time = time.time()
        idle_threshold = idle_timeout_minutes * 60  # Convert to seconds

        try:
            containers = self.client.containers.list(
                filters={"label": f"managed-by={self.LABEL_MANAGED_BY}"}
            )

            count = 0
            for container in containers:
                container_id = str(container.id)
                should_cleanup = False

                # Check if we have activity tracking for this container
                if container_id in self.last_activity:
                    # Use tracked activity timestamp
                    idle_time = current_time - self.last_activity[container_id]
                    should_cleanup = idle_time > idle_threshold
                else:
                    # Fallback: use creation time from label
                    created_at_str = container.labels.get("created-at")
                    if created_at_str:
                        try:
                            created_at = float(created_at_str)
                            age = current_time - created_at
                            should_cleanup = age > idle_threshold
                        except ValueError:
                            # Invalid timestamp, skip this container
                            pass

                if should_cleanup:
                    try:
                        container.stop(timeout=10)
                        container.remove()
                        count += 1
                        # Remove from activity tracking
                        if container_id in self.last_activity:
                            del self.last_activity[container_id]
                    except APIError as e:
                        print(f"Warning: Failed to cleanup idle container {container_id}: {e}")

            return count

        except APIError as e:
            print(f"Warning: Failed to list containers for lazy cleanup: {e}")
            return 0

    # File operations methods

    def write_file(self, container_id: str, dest_path: str, content: str | bytes) -> None:
        """Write file to container using Docker's put_archive API.

        Args:
            container_id: Container identifier
            dest_path: Destination path inside container
            content: File content (string or bytes)

        Raises:
            APIError: If file write fails
        """
        import io
        import os
        import tarfile

        # Convert string to bytes if needed
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        # Ensure parent directory exists
        parent_dir = os.path.dirname(dest_path)
        if parent_dir and parent_dir != "/":
            self.create_directory(container_id, parent_dir)

        # Create tar archive in memory with the file
        try:
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                tarinfo = tarfile.TarInfo(name=os.path.basename(dest_path))
                tarinfo.size = len(content_bytes)
                tarinfo.mode = 0o666  # rw-rw-rw- - readable/writable by all
                tarinfo.uid = 1000  # Standard non-root user
                tarinfo.gid = 1000  # Standard non-root group
                tar.addfile(tarinfo, io.BytesIO(content_bytes))

            tar_stream.seek(0)

            # Write file to container using put_archive
            container = self.client.containers.get(container_id)
            container.put_archive(path=parent_dir or "/", data=tar_stream)

            # Update activity tracking
            self._update_activity(container_id)
        except APIError as e:
            raise APIError(
                f"Failed to write file {dest_path} in container {container_id}: {e}"
            ) from e

    def read_file(self, container_id: str, path: str) -> bytes:
        """Read file from container using base64 encoding.

        Args:
            container_id: Container identifier
            path: File path inside container

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file does not exist
            APIError: If file read fails
        """
        import base64

        stdout, _, exit_code = self.execute_command(
            container_id, ["sh", "-c", f"base64 {path}"], timeout=30
        )

        if exit_code != 0:
            raise FileNotFoundError(f"File not found: {path}")

        return base64.b64decode(stdout)

    def create_directory(self, container_id: str, path: str) -> None:
        """Create directory inside container using put_archive API.

        Args:
            container_id: Container identifier
            path: Directory path inside container

        Raises:
            APIError: If directory creation fails
        """
        import io
        import tarfile

        try:
            container = self.client.containers.get(container_id)

            # Parse path to create all parent directories (like mkdir -p)
            # Remove leading/trailing slashes and split
            parts = [p for p in path.strip("/").split("/") if p]

            if not parts:
                # Root directory or empty path - nothing to create
                return

            # Create tar archive with directory structure
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                # Add each directory level (mimics mkdir -p behavior)
                current_path = ""
                for part in parts:
                    current_path = f"{current_path}/{part}" if current_path else part
                    tarinfo = tarfile.TarInfo(name=current_path)
                    tarinfo.type = tarfile.DIRTYPE  # Mark as directory
                    tarinfo.mode = 0o777  # rwxrwxrwx - world-writable for container user
                    tarinfo.uid = 1000  # Standard non-root user
                    tarinfo.gid = 1000  # Standard non-root group
                    tar.addfile(tarinfo)

            tar_stream.seek(0)

            # Put archive at root - path contains full directory structure
            container.put_archive(path="/", data=tar_stream)

            # Update activity tracking
            self._update_activity(container_id)
        except APIError as e:
            raise APIError(f"Failed to create directory {path}: {e}") from e

    def file_exists(self, container_id: str, path: str) -> bool:
        """Check if file exists in container.

        Args:
            container_id: Container identifier
            path: File path inside container

        Returns:
            True if file exists, False otherwise
        """
        _, _, exit_code = self.execute_command(container_id, ["test", "-f", path], timeout=5)
        return exit_code == 0

    def list_files(self, container_id: str, path: str) -> list[str]:
        """List files in directory inside container.

        Args:
            container_id: Container identifier
            path: Directory path inside container

        Returns:
            List of file names (empty list if directory doesn't exist)
        """
        stdout, _, exit_code = self.execute_command(container_id, ["ls", "-1", path], timeout=10)

        if exit_code != 0:
            return []

        return [line.strip() for line in stdout.split("\n") if line.strip()]

    def get_container_logs(
        self,
        container_id: str,
        tail: int = 50,
        since: int | None = None,
    ) -> str:
        """Get container logs (stdout/stderr from all processes).

        Args:
            container_id: Container identifier
            tail: Number of lines to retrieve from end of logs (default: 50)
            since: Only return logs since this many seconds ago (optional)

        Returns:
            Container logs as string

        Raises:
            APIError: If log retrieval fails
        """
        try:
            container = self.client.containers.get(container_id)

            # Get logs from container
            logs_bytes = container.logs(tail=tail, since=since)

            # Decode to string
            if isinstance(logs_bytes, bytes):
                return logs_bytes.decode("utf-8")
            return str(logs_bytes)

        except NotFound as e:
            raise APIError(f"Container not found: {container_id}") from e
        except APIError as e:
            raise APIError(f"Failed to get logs: {e}") from e
