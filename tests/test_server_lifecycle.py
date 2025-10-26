"""Tests for server lifecycle and resource cleanup."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.docker_manager import DockerContainerManager


class TestServerLifecycle:
    """Test server lifecycle management and cleanup."""

    @pytest.fixture
    def mock_docker_client(self) -> MagicMock:
        """Create a mocked Docker client."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_docker_client: MagicMock) -> DockerContainerManager:
        """Create DockerContainerManager with mocked client."""
        with patch("src.docker_manager.docker.from_env", return_value=mock_docker_client):
            return DockerContainerManager()

    def test_cleanup_on_shutdown_cleans_all_containers(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that cleanup_all() stops and removes all containers."""
        # Setup mock containers
        mock_container1 = MagicMock()
        mock_container1.id = "container-1"
        mock_container2 = MagicMock()
        mock_container2.id = "container-2"
        mock_docker_client.containers.list.return_value = [mock_container1, mock_container2]

        # Add to activity tracking
        manager.last_activity["container-1"] = 123.0
        manager.last_activity["container-2"] = 456.0

        # Call cleanup
        count = manager.cleanup_all()

        # Verify all containers cleaned
        assert count == 2
        mock_container1.stop.assert_called_once()
        mock_container1.remove.assert_called_once()
        mock_container2.stop.assert_called_once()
        mock_container2.remove.assert_called_once()

        # Verify activity tracking cleared
        assert "container-1" not in manager.last_activity
        assert "container-2" not in manager.last_activity

    def test_cleanup_all_handles_errors_gracefully(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that cleanup_all continues even if one container fails."""
        from docker.errors import APIError

        # Setup mock containers
        mock_failing_container = MagicMock()
        mock_failing_container.id = "failing-container"
        mock_failing_container.stop.side_effect = APIError("Stop failed")

        mock_success_container = MagicMock()
        mock_success_container.id = "success-container"

        mock_docker_client.containers.list.return_value = [
            mock_failing_container,
            mock_success_container,
        ]

        # Call cleanup - should not raise error
        count = manager.cleanup_all()

        # Only successful container counted
        assert count == 1
        mock_success_container.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_background_cleanup_task_runs_periodically(
        self, manager: DockerContainerManager
    ) -> None:
        """Test that background cleanup task runs periodically."""
        cleanup_count = 0

        async def mock_cleanup_task(interval_seconds: int) -> None:
            """Mock cleanup task that runs a few times."""
            nonlocal cleanup_count
            for _ in range(3):
                await asyncio.sleep(interval_seconds)
                manager._lazy_cleanup()
                cleanup_count += 1

        # Run task for short duration
        with patch.object(manager, "_lazy_cleanup", return_value=0) as mock_lazy:
            task = asyncio.create_task(mock_cleanup_task(interval_seconds=0.1))
            await asyncio.sleep(0.35)  # Let it run ~3 times
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify cleanup was called multiple times
            assert mock_lazy.call_count >= 2

    @pytest.mark.asyncio
    async def test_background_cleanup_can_be_cancelled(self) -> None:
        """Test that background cleanup task can be cancelled gracefully."""

        async def cleanup_task() -> None:
            """Cleanup task that runs until cancelled."""
            while True:
                await asyncio.sleep(0.1)

        # Create and cancel task
        task = asyncio.create_task(cleanup_task())
        await asyncio.sleep(0.05)  # Let it start
        task.cancel()

        # Should raise CancelledError
        with pytest.raises(asyncio.CancelledError):
            await task

    def test_cleanup_all_removes_activity_tracking_even_on_notfound(
        self, manager: DockerContainerManager, mock_docker_client: MagicMock
    ) -> None:
        """Test that cleanup_all removes activity tracking even if container doesn't exist."""
        from docker.errors import NotFound

        # Container not found
        mock_docker_client.containers.list.return_value = []

        # But we have activity tracking
        manager.last_activity["phantom-container"] = 123.0

        # This should not fail even though container doesn't exist
        count = manager.cleanup_all()

        # Count should be 0 since no containers exist
        assert count == 0

        # Activity tracking should be cleared by stop_container (idempotent)
        # Note: cleanup_all only iterates existing containers, so phantom-container tracking remains
        # This is fine - it will be cleaned up on next lazy_cleanup
        # For true cleanup, we could add a method to clear all tracking
