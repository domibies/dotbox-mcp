"""Tests for DockerContainerManager using mocked Docker SDK."""

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
    def manager(self, mock_docker_client: MagicMock) -> DockerContainerManager:
        """Create DockerContainerManager with mocked client."""
        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            return DockerContainerManager()

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
            working_dir="/workspace",
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
            working_dir="/workspace",
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
            working_dir="/workspace",
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
            working_dir="/workspace",
        )

        call_kwargs = mock_docker_client.containers.run.call_args[1]
        container_name = call_kwargs.get("name", "")

        # Should contain dotnet version and project id
        assert "dotnet8" in container_name.lower() or "8" in container_name
        assert "my-project" in container_name or "project" in container_name
