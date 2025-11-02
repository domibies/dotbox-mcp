"""Tests for DockerContainerManager using mocked Docker SDK."""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.docker_manager import DockerContainerManager


class TestDockerContainerManager:
    """Test DockerContainerManager class."""

    @pytest.fixture
    def mock_docker_client(self) -> MagicMock:
        """Create a mocked Docker client."""
        return MagicMock()

    @pytest.fixture
    def manager(
        self, mock_docker_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> DockerContainerManager:
        """Create DockerContainerManager with mocked client."""
        # Set local registry mode for tests
        monkeypatch.setenv("DOTBOX_SANDBOX_REGISTRY", "local")
        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            manager = DockerContainerManager()
            # Mock _ensure_image_exists to avoid image checks in unit tests
            manager._ensure_image_exists = MagicMock()  # type: ignore
            return manager

    def test_initialization(self, manager: DockerContainerManager) -> None:
        """Test that manager initializes correctly."""
        assert manager is not None

    def test_create_container_success(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test successful container creation."""
        # Setup mock
        mock_container = MagicMock()
        mock_container.id = "test-container-id"
        mock_docker_client.containers.run.return_value = mock_container

        # Create container
        container_id = manager.create_container(
            dotnet_version="8",
            project_id="test-project",
        )

        # Verify
        assert container_id == "test-container-id"
        mock_docker_client.containers.run.assert_called_once()
        call_kwargs = mock_docker_client.containers.run.call_args[1]
        assert call_kwargs["image"] == "dotnet-sandbox:8"
        assert call_kwargs["detach"] is True
        assert "dotbox-mcp" in call_kwargs["labels"]["managed-by"]
        assert call_kwargs["labels"]["project-id"] == "test-project"

    def test_create_container_with_port_mapping(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test container creation with port mapping."""
        mock_container = MagicMock()
        mock_container.id = "test-container-id"
        mock_docker_client.containers.run.return_value = mock_container

        container_id = manager.create_container(
            dotnet_version="8",
            project_id="test-project",
            port_mapping={5000: 5001},
        )

        assert container_id == "test-container-id"
        call_kwargs = mock_docker_client.containers.run.call_args[1]
        assert call_kwargs["ports"][5000] == 5001

    def test_create_container_with_resource_limits(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that containers are created with resource limits."""
        mock_container = MagicMock()
        mock_container.id = "test-container-id"
        mock_docker_client.containers.run.return_value = mock_container

        manager.create_container(
            dotnet_version="8",
            project_id="test-project",
        )

        call_kwargs = mock_docker_client.containers.run.call_args[1]
        # Should have CPU and memory limits
        assert "mem_limit" in call_kwargs
        assert "cpu_period" in call_kwargs or "nano_cpus" in call_kwargs

    def test_execute_command_success(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test successful command execution."""
        # Setup mock container
        mock_container = MagicMock()
        mock_result = MagicMock()
        mock_result.output = b"Hello World\n"
        mock_result.exit_code = 0
        mock_container.exec_run.return_value = mock_result
        mock_docker_client.containers.get.return_value = mock_container

        # Execute command
        stdout, stderr, exit_code = manager.execute_command(
            container_id="test-container-id",
            command=["echo", "Hello World"],
            timeout=30,
        )

        # Verify
        assert stdout == "Hello World\n"
        assert stderr == ""
        assert exit_code == 0
        mock_container.exec_run.assert_called_once()

    def test_execute_command_with_stderr(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test command execution that produces stderr."""
        mock_container = MagicMock()
        mock_result = MagicMock()
        mock_result.output = b"Error message\n"
        mock_result.exit_code = 1
        mock_container.exec_run.return_value = mock_result
        mock_docker_client.containers.get.return_value = mock_container

        stdout, stderr, exit_code = manager.execute_command(
            container_id="test-container-id",
            command=["invalid-command"],
            timeout=30,
        )

        # When exit_code != 0, output should be treated as stderr
        assert exit_code == 1
        # Implementation will determine if it goes to stdout or stderr

    def test_execute_command_timeout(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test command execution timeout."""
        mock_container = MagicMock()
        # Simulate timeout
        from docker.errors import APIError

        mock_container.exec_run.side_effect = APIError("Timeout")
        mock_docker_client.containers.get.return_value = mock_container

        with pytest.raises(APIError):
            manager.execute_command(
                container_id="test-container-id",
                command=["sleep", "1000"],
                timeout=1,
            )

    def test_stop_container_success(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test successful container stop and removal."""
        mock_container = MagicMock()
        mock_docker_client.containers.get.return_value = mock_container

        manager.stop_container("test-container-id")

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()

    def test_stop_container_already_stopped(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test stopping a container that's already stopped."""
        from docker.errors import NotFound

        mock_docker_client.containers.get.side_effect = NotFound("Container not found")

        # Should not raise error - idempotent operation
        manager.stop_container("nonexistent-container-id")

    def test_list_containers(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test listing all sandbox containers."""
        # Setup mock containers
        mock_container1 = MagicMock()
        mock_container1.id = "container-1"
        mock_container1.name = "dotnet8-project1"
        mock_container1.status = "running"
        mock_container1.labels = {"managed-by": "dotbox-mcp", "project-id": "project1"}
        mock_container1.attrs = {"NetworkSettings": {"Ports": {}}}

        mock_container2 = MagicMock()
        mock_container2.id = "container-2"
        mock_container2.name = "dotnet9-project2"
        mock_container2.status = "running"
        mock_container2.labels = {"managed-by": "dotbox-mcp", "project-id": "project2"}
        mock_container2.attrs = {"NetworkSettings": {"Ports": {"5000/tcp": [{"HostPort": "5001"}]}}}

        mock_docker_client.containers.list.return_value = [mock_container1, mock_container2]

        # List containers
        containers = manager.list_containers()

        # Verify
        assert len(containers) == 2
        assert containers[0].container_id == "container-1"
        assert containers[0].project_id == "project1"
        assert containers[0].status == "running"
        assert containers[1].container_id == "container-2"
        assert containers[1].project_id == "project2"

    def test_list_containers_with_port_mapping(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test listing containers includes port information."""
        mock_container = MagicMock()
        mock_container.id = "container-1"
        mock_container.name = "dotnet8-webapi"
        mock_container.status = "running"
        mock_container.labels = {"managed-by": "dotbox-mcp", "project-id": "webapi"}
        mock_container.attrs = {"NetworkSettings": {"Ports": {"5000/tcp": [{"HostPort": "5001"}]}}}

        mock_docker_client.containers.list.return_value = [mock_container]

        containers = manager.list_containers()

        assert len(containers) == 1
        assert containers[0].ports == {"5000/tcp": "5001"}

    def test_cleanup_all_containers(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test cleaning up all sandbox containers."""
        # Setup mock containers
        mock_container1 = MagicMock()
        mock_container2 = MagicMock()
        mock_docker_client.containers.list.return_value = [mock_container1, mock_container2]

        count = manager.cleanup_all()

        assert count == 2
        mock_container1.stop.assert_called_once()
        mock_container1.remove.assert_called_once()
        mock_container2.stop.assert_called_once()
        mock_container2.remove.assert_called_once()

    def test_docker_not_available(self) -> None:
        """Test error when Docker is not available."""
        from docker.errors import DockerException

        with patch(
            "src.docker_manager.docker.from_env", side_effect=DockerException("Docker not found")
        ):
            with pytest.raises(DockerException):
                DockerContainerManager()

    def test_container_name_generation(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that container names are human-readable."""
        mock_container = MagicMock()
        mock_container.id = "test-id"
        mock_docker_client.containers.run.return_value = mock_container

        manager.create_container(
            dotnet_version="8",
            project_id="my-project",
        )

        call_kwargs = mock_docker_client.containers.run.call_args[1]
        container_name = call_kwargs.get("name", "")

        # Should contain dotnet version and project id
        assert "dotnet8" in container_name.lower() or "8" in container_name
        assert "my-project" in container_name or "project" in container_name

    def test_get_container_by_project_id_found(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test finding a container by project ID."""
        mock_container = MagicMock()
        mock_container.id = "container-123"
        mock_docker_client.containers.list.return_value = [mock_container]

        container_id = manager.get_container_by_project_id("test-project")

        assert container_id == "container-123"
        mock_docker_client.containers.list.assert_called_once()

    def test_get_container_by_project_id_not_found(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test finding a non-existent container by project ID."""
        mock_docker_client.containers.list.return_value = []

        container_id = manager.get_container_by_project_id("nonexistent-project")

        assert container_id is None

    def test_activity_tracking_on_create(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that creating a container tracks initial activity."""
        mock_container = MagicMock()
        mock_container.id = "test-container-id"
        mock_docker_client.containers.run.return_value = mock_container

        container_id = manager.create_container(
            dotnet_version="8",
            project_id="test-project",
        )

        # Verify activity is tracked
        assert container_id in manager.last_activity
        assert isinstance(manager.last_activity[container_id], float)

    def test_activity_tracking_on_execute(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that executing a command updates activity timestamp."""
        mock_container = MagicMock()
        mock_result = MagicMock()
        mock_result.output = b"output"
        mock_result.exit_code = 0
        mock_container.exec_run.return_value = mock_result
        mock_docker_client.containers.get.return_value = mock_container

        # Set initial timestamp
        initial_time = time.time() - 100  # 100 seconds ago
        manager.last_activity["test-container-id"] = initial_time

        # Execute command
        manager.execute_command("test-container-id", ["echo", "test"])

        # Verify activity was updated
        assert manager.last_activity["test-container-id"] > initial_time

    def test_activity_tracking_removed_on_stop(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that stopping a container removes it from activity tracking."""
        mock_container = MagicMock()
        mock_docker_client.containers.get.return_value = mock_container

        # Add to activity tracking
        manager.last_activity["test-container-id"] = time.time()

        # Stop container
        manager.stop_container("test-container-id")

        # Verify removed from tracking
        assert "test-container-id" not in manager.last_activity

    def test_lazy_cleanup_idle_containers(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that lazy cleanup removes idle containers."""
        # Setup mock containers
        mock_idle_container = MagicMock()
        mock_idle_container.id = "idle-container"
        mock_idle_container.labels = {"created-at": str(int(time.time()) - 2000)}

        mock_active_container = MagicMock()
        mock_active_container.id = "active-container"
        mock_active_container.labels = {"created-at": str(int(time.time()))}

        mock_docker_client.containers.list.return_value = [
            mock_idle_container,
            mock_active_container,
        ]

        # Add active container to tracking (recent activity)
        manager.last_activity["active-container"] = time.time()

        # Add idle container to tracking (old activity - more than 30 min ago)
        manager.last_activity["idle-container"] = time.time() - 2000  # ~33 minutes ago

        # Run lazy cleanup with 30 minute timeout
        count = manager._lazy_cleanup(idle_timeout_minutes=30)

        # Verify idle container was cleaned up
        assert count == 1
        mock_idle_container.stop.assert_called_once()
        mock_idle_container.remove.assert_called_once()

        # Verify active container was not touched
        mock_active_container.stop.assert_not_called()
        mock_active_container.remove.assert_not_called()

    def test_lazy_cleanup_fallback_to_creation_time(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that lazy cleanup uses creation time as fallback."""
        # Container without activity tracking but old creation time
        mock_old_container = MagicMock()
        mock_old_container.id = "old-container-no-tracking"
        mock_old_container.labels = {"created-at": str(int(time.time()) - 2000)}

        mock_docker_client.containers.list.return_value = [mock_old_container]

        # Don't add to activity tracking to test fallback
        count = manager._lazy_cleanup(idle_timeout_minutes=30)

        # Should cleanup based on creation time
        assert count == 1
        mock_old_container.stop.assert_called_once()

    def test_lazy_cleanup_removes_from_tracking(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that lazy cleanup removes containers from activity tracking."""
        mock_container = MagicMock()
        mock_container.id = "idle-container"
        mock_container.labels = {"created-at": str(int(time.time()) - 2000)}

        mock_docker_client.containers.list.return_value = [mock_container]

        # Add to tracking
        manager.last_activity["idle-container"] = time.time() - 2000

        # Run cleanup
        manager._lazy_cleanup(idle_timeout_minutes=30)

        # Verify removed from tracking
        assert "idle-container" not in manager.last_activity

    def test_created_at_label_added(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that containers are created with created-at timestamp label."""
        mock_container = MagicMock()
        mock_container.id = "test-container-id"
        mock_docker_client.containers.run.return_value = mock_container

        manager.create_container(
            dotnet_version="8",
            project_id="test-project",
        )

        call_kwargs = mock_docker_client.containers.run.call_args[1]
        labels = call_kwargs["labels"]

        # Verify created-at label exists and is a valid timestamp
        assert "created-at" in labels
        created_at = int(labels["created-at"])
        assert created_at > 0
        assert created_at <= int(time.time())

    # File operations tests

    def test_write_file_string_content(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test writing a file with string content."""
        mock_container = MagicMock()
        mock_container.put_archive.return_value = True
        mock_docker_client.containers.get.return_value = mock_container

        manager.write_file("test-container", "/workspace/test.txt", "Hello World")

        # Verify put_archive was called (directory + file = 2 calls)
        assert mock_container.put_archive.call_count == 2

    def test_write_file_bytes_content(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test writing a file with bytes content."""
        mock_container = MagicMock()
        mock_container.put_archive.return_value = True
        mock_docker_client.containers.get.return_value = mock_container

        manager.write_file("test-container", "/workspace/test.bin", b"\x00\x01\x02")

        # Verify put_archive was called (directory + file = 2 calls)
        assert mock_container.put_archive.call_count == 2

    def test_write_file_creates_parent_directory(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that writing a file creates parent directories."""
        mock_container = MagicMock()
        mock_container.put_archive.return_value = True
        mock_docker_client.containers.get.return_value = mock_container

        manager.write_file("test-container", "/workspace/subdir/test.txt", "content")

        # Should call put_archive twice: once for directory, once for file
        assert mock_container.put_archive.call_count == 2

    def test_create_directory(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test creating a directory using put_archive."""
        mock_container = MagicMock()
        mock_container.put_archive.return_value = True
        mock_docker_client.containers.get.return_value = mock_container

        manager.create_directory("test-container", "/workspace/mydir")

        # Verify put_archive was called
        mock_container.put_archive.assert_called_once()
        # Verify it was called with root path
        call_args = mock_container.put_archive.call_args
        assert call_args[1]["path"] == "/"

    def test_create_directory_nested(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test creating nested directories (like mkdir -p)."""
        mock_container = MagicMock()
        mock_container.put_archive.return_value = True
        mock_docker_client.containers.get.return_value = mock_container

        manager.create_directory("test-container", "/workspace/a/b/c")

        # Verify put_archive was called
        mock_container.put_archive.assert_called_once()

    def test_create_directory_root(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test creating root or empty path is a no-op."""
        mock_container = MagicMock()
        mock_docker_client.containers.get.return_value = mock_container

        manager.create_directory("test-container", "/")

        # Should not call put_archive for root
        mock_container.put_archive.assert_not_called()

    def test_create_directory_failure(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test directory creation failure raises error."""
        from docker.errors import APIError

        mock_container = MagicMock()
        mock_container.put_archive.side_effect = APIError("Permission denied")
        mock_docker_client.containers.get.return_value = mock_container

        with pytest.raises(APIError) as exc_info:
            manager.create_directory("test-container", "/root/denied")

        assert "Failed to create directory" in str(exc_info.value)

    def test_read_file_success(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test reading a file successfully."""
        mock_container = MagicMock()
        mock_result = MagicMock()
        # Base64 encoded "Hello World"
        import base64

        mock_result.output = base64.b64encode(b"Hello World")
        mock_result.exit_code = 0
        mock_container.exec_run.return_value = mock_result
        mock_docker_client.containers.get.return_value = mock_container

        content = manager.read_file("test-container", "/workspace/test.txt")

        assert content == b"Hello World"

    def test_read_file_not_found(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test reading a non-existent file."""
        mock_container = MagicMock()
        mock_result = MagicMock()
        mock_result.output = b"File not found"
        mock_result.exit_code = 1
        mock_container.exec_run.return_value = mock_result
        mock_docker_client.containers.get.return_value = mock_container

        with pytest.raises(FileNotFoundError):
            manager.read_file("test-container", "/workspace/nonexistent.txt")

    def test_file_exists_true(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test checking if file exists (returns True)."""
        mock_container = MagicMock()
        mock_result = MagicMock()
        mock_result.output = b""
        mock_result.exit_code = 0
        mock_container.exec_run.return_value = mock_result
        mock_docker_client.containers.get.return_value = mock_container

        exists = manager.file_exists("test-container", "/workspace/test.txt")

        assert exists is True
        mock_container.exec_run.assert_called_once()

    def test_file_exists_false(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test checking if file exists (returns False)."""
        mock_container = MagicMock()
        mock_result = MagicMock()
        mock_result.output = b""
        mock_result.exit_code = 1
        mock_container.exec_run.return_value = mock_result
        mock_docker_client.containers.get.return_value = mock_container

        exists = manager.file_exists("test-container", "/workspace/nonexistent.txt")

        assert exists is False

    def test_list_files_success(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test listing files in a directory."""
        mock_container = MagicMock()
        mock_result = MagicMock()
        mock_result.output = b"file1.txt\nfile2.cs\nsubdir\n"
        mock_result.exit_code = 0
        mock_container.exec_run.return_value = mock_result
        mock_docker_client.containers.get.return_value = mock_container

        files = manager.list_files("test-container", "/workspace")

        assert files == ["file1.txt", "file2.cs", "subdir"]
        mock_container.exec_run.assert_called_once()

    def test_list_files_empty_directory(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test listing files in an empty or non-existent directory."""
        mock_container = MagicMock()
        mock_result = MagicMock()
        mock_result.output = b""
        mock_result.exit_code = 1
        mock_container.exec_run.return_value = mock_result
        mock_docker_client.containers.get.return_value = mock_container

        files = manager.list_files("test-container", "/nonexistent")

        assert files == []

    def test_get_container_logs_default_tail(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test getting container logs with default tail."""
        mock_container = MagicMock()
        mock_container.logs.return_value = b"Log line 1\nLog line 2\nLog line 3\n"
        mock_docker_client.containers.get.return_value = mock_container

        logs = manager.get_container_logs("test-container")

        assert logs == "Log line 1\nLog line 2\nLog line 3\n"
        mock_container.logs.assert_called_once_with(tail=50, since=None)

    def test_get_container_logs_custom_tail(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test getting container logs with custom tail."""
        mock_container = MagicMock()
        mock_container.logs.return_value = b"Recent log\n"
        mock_docker_client.containers.get.return_value = mock_container

        logs = manager.get_container_logs("test-container", tail=10)

        assert logs == "Recent log\n"
        mock_container.logs.assert_called_once_with(tail=10, since=None)

    def test_get_container_logs_with_since(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test getting container logs with since parameter."""
        mock_container = MagicMock()
        mock_container.logs.return_value = b"Recent logs only\n"
        mock_docker_client.containers.get.return_value = mock_container

        logs = manager.get_container_logs("test-container", tail=50, since=300)

        assert logs == "Recent logs only\n"
        mock_container.logs.assert_called_once_with(tail=50, since=300)

    def test_get_container_logs_empty(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test getting logs when container has no logs."""
        mock_container = MagicMock()
        mock_container.logs.return_value = b""
        mock_docker_client.containers.get.return_value = mock_container

        logs = manager.get_container_logs("test-container")

        assert logs == ""
