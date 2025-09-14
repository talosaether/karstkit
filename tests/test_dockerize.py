"""Tests for Docker operations functionality."""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from iac_wrapper.dockerize import DockerOps
from iac_wrapper.slug import RepoSlug


class TestDockerOps:
    """Test DockerOps class."""

    def test_init(self, mock_config):
        """Test DockerOps initialization."""
        docker_ops = DockerOps()
        assert docker_ops.template_dir == mock_config.TEMPLATES_DIR

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_build_image_success(
        self, mock_run, mock_temp_file, sample_repo, mock_config
    ):
        """Test successful Docker image build."""
        # Mock temporary file
        mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test.Dockerfile"
        mock_temp_file.return_value.__enter__.return_value.write = Mock()

        # Mock successful Docker build
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        docker_ops = DockerOps()
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")

        result = docker_ops.build_image(sample_repo, slug)

        assert result == "iac-testuser-testrepo:latest"
        mock_run.assert_called_once()

        # Verify Docker build command
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "docker"
        assert call_args[1] == "build"
        assert call_args[2] == "-f"
        assert call_args[3] == "/tmp/test.Dockerfile"
        assert call_args[4] == "-t"
        assert call_args[5] == "iac-testuser-testrepo:latest"
        assert call_args[6] == str(sample_repo)

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_build_image_failure(
        self, mock_run, mock_temp_file, sample_repo, mock_config
    ):
        """Test Docker image build failure."""
        # Mock temporary file
        mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test.Dockerfile"
        mock_temp_file.return_value.__enter__.return_value.write = Mock()

        # Mock failed Docker build
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Docker build failed"

        docker_ops = DockerOps()
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")

        with pytest.raises(RuntimeError, match="Docker build failed"):
            docker_ops.build_image(sample_repo, slug)

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_build_image_with_entrypoint(
        self, mock_run, mock_temp_file, sample_repo, mock_config
    ):
        """Test Docker image build with custom entrypoint."""
        # Mock temporary file
        mock_temp_file.return_value.__enter__.return_value.name = "/tmp/test.Dockerfile"
        mock_temp_file.return_value.__enter__.return_value.write = Mock()

        # Mock successful Docker build
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        docker_ops = DockerOps()
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")

        result = docker_ops.build_image(sample_repo, slug, entrypoint="custom.main")

        assert result == "iac-testuser-testrepo:latest"

        # Verify that write was called with custom entrypoint
        mock_temp_file.return_value.__enter__.return_value.write.assert_called()

    @patch("subprocess.run")
    def test_run_container_success(self, mock_run, mock_config):
        """Test successful container run."""
        # Mock successful Docker run
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "container_id_123"
        mock_run.return_value.stderr = ""

        docker_ops = DockerOps()

        result = docker_ops.run_container(
            "test-image:latest",
            "test-service",
            environment={"TEST_VAR": "test_value"},
            volumes=["/host/path:/container/path"],
        )

        assert result == "container_id_123"
        mock_run.assert_called_once()

        # Verify Docker run command
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "docker"
        assert call_args[1] == "run"
        assert call_args[2] == "-d"
        assert call_args[3] == "--name"
        assert call_args[4] == "test-service"
        assert call_args[5] == "--network"
        assert call_args[6] == mock_config.DOCKER_NETWORK_NAME
        assert call_args[7] == "--restart"
        assert call_args[8] == "unless-stopped"
        assert call_args[9] == "-e"
        assert call_args[10] == "TEST_VAR=test_value"
        assert call_args[11] == "-v"
        assert call_args[12] == "/host/path:/container/path"
        assert call_args[13] == "test-image:latest"

    @patch("subprocess.run")
    def test_run_container_failure(self, mock_run, mock_config):
        """Test container run failure."""
        # Mock failed Docker run
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Docker run failed"

        docker_ops = DockerOps()

        with pytest.raises(RuntimeError, match="Docker run failed"):
            docker_ops.run_container("test-image:latest", "test-service")

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_run_envoy_sidecar_success(self, mock_run, mock_temp_file, mock_config):
        """Test successful Envoy sidecar run."""
        # Mock temporary file
        mock_temp_file.return_value.__enter__.return_value.name = "/tmp/envoy.yaml"
        mock_temp_file.return_value.__enter__.return_value.write = Mock()

        # Mock successful Docker run
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "envoy_container_id_456"
        mock_run.return_value.stderr = ""

        docker_ops = DockerOps()

        result = docker_ops.run_envoy_sidecar("test-service", "envoy config content")

        assert result == "envoy_container_id_456"
        mock_run.assert_called_once()

        # Verify Envoy Docker run command
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "docker"
        assert call_args[1] == "run"
        assert call_args[2] == "-d"
        assert call_args[3] == "--name"
        assert call_args[4] == "test-service-envoy"
        assert call_args[5] == "--network"
        assert call_args[6] == mock_config.DOCKER_NETWORK_NAME
        assert call_args[7] == "--restart"
        assert call_args[8] == "unless-stopped"
        assert call_args[9] == "-v"
        assert call_args[10] == "/tmp/envoy.yaml:/etc/envoy/envoy.yaml:ro"
        assert call_args[11] == "-p"
        assert (
            call_args[12]
            == f"{mock_config.ENVOY_INBOUND_PORT}:{mock_config.ENVOY_INBOUND_PORT}"
        )
        assert call_args[13] == "-p"
        assert (
            call_args[14]
            == f"{mock_config.ENVOY_METRICS_PORT}:{mock_config.ENVOY_METRICS_PORT}"
        )
        assert call_args[15] == "envoyproxy/envoy:v1.28-latest"
        assert call_args[16] == "/usr/local/bin/envoy"
        assert call_args[17] == "-c"
        assert call_args[18] == "/etc/envoy/envoy.yaml"
        assert call_args[19] == "--service-cluster"
        assert call_args[20] == "test-service"
        assert call_args[21] == "--service-node"
        assert call_args[22] == "test-service-node"

    @patch("subprocess.run")
    def test_stop_container(self, mock_run):
        """Test stopping a container."""
        # Mock successful Docker stop
        mock_run.return_value.returncode = 0

        docker_ops = DockerOps()
        docker_ops.stop_container("test-container")

        mock_run.assert_called_once_with(
            ["docker", "stop", "test-container"], capture_output=True, text=True
        )

    @patch("subprocess.run")
    def test_remove_container(self, mock_run):
        """Test removing a container."""
        # Mock successful Docker rm
        mock_run.return_value.returncode = 0

        docker_ops = DockerOps()
        docker_ops.remove_container("test-container")

        mock_run.assert_called_once_with(
            ["docker", "rm", "test-container"], capture_output=True, text=True
        )

    @patch("subprocess.run")
    def test_get_container_logs(self, mock_run):
        """Test getting container logs."""
        # Mock successful Docker logs
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "container log output"
        mock_run.return_value.stderr = ""

        docker_ops = DockerOps()
        result = docker_ops.get_container_logs("test-container", tail=50)

        assert result == "container log output"
        mock_run.assert_called_once_with(
            ["docker", "logs", "--tail", "50", "test-container"],
            capture_output=True,
            text=True,
        )

    @patch("subprocess.run")
    def test_get_container_logs_error(self, mock_run):
        """Test getting container logs with error."""
        # Mock failed Docker logs
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Container not found"

        docker_ops = DockerOps()
        result = docker_ops.get_container_logs("test-container")

        assert "Error getting logs" in result
        assert "Container not found" in result

    @patch("subprocess.run")
    def test_container_exists_true(self, mock_run):
        """Test container exists check when container exists."""
        # Mock successful Docker ps
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "test-container"

        docker_ops = DockerOps()
        result = docker_ops.container_exists("test-container")

        assert result is True
        mock_run.assert_called_once_with(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "name=test-container",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
        )

    @patch("subprocess.run")
    def test_container_exists_false(self, mock_run):
        """Test container exists check when container doesn't exist."""
        # Mock successful Docker ps with no output
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""

        docker_ops = DockerOps()
        result = docker_ops.container_exists("test-container")

        assert result is False

    @patch("subprocess.run")
    def test_container_running_true(self, mock_run):
        """Test container running check when container is running."""
        # Mock successful Docker ps
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "test-container"

        docker_ops = DockerOps()
        result = docker_ops.container_running("test-container")

        assert result is True
        mock_run.assert_called_once_with(
            [
                "docker",
                "ps",
                "--filter",
                "name=test-container",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
        )

    @patch("subprocess.run")
    def test_container_running_false(self, mock_run):
        """Test container running check when container is not running."""
        # Mock successful Docker ps with no output
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""

        docker_ops = DockerOps()
        result = docker_ops.container_running("test-container")

        assert result is False

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="FROM python:3.11-slim\nRUN echo '{{ entrypoint | default(\"main.main()\") }}' > /app/entrypoint.sh",
    )
    def test_generate_dockerfile(self, mock_file, mock_config):
        """Test Dockerfile generation."""
        docker_ops = DockerOps()
        slug = RepoSlug(scheme="gh", owner="testuser", repo="testrepo")

        result = docker_ops._generate_dockerfile(slug, entrypoint="custom.main")

        assert "FROM python:3.11-slim" in result
        assert "custom.main" in result
        assert str(mock_config.GRPC_PORT) in result


class TestEnvoyStartupOrdering:
    """Test Envoy startup ordering functionality."""

    @patch("requests.get")
    @patch("subprocess.run")
    def test_wait_for_envoy_ready_success(self, mock_run, mock_requests, mock_config):
        """Test successful Envoy readiness check."""
        docker_ops = DockerOps()

        # Mock container running check
        mock_run.side_effect = [
            # First call: container running check returns True
            Mock(returncode=0, stdout="test-service-envoy\n"),
            # Second call: get container IP
            Mock(returncode=0, stdout="172.20.0.10\n"),
        ]

        # Mock successful readiness check
        mock_response = Mock()
        mock_response.status_code = 200
        mock_requests.return_value = mock_response

        result = docker_ops.wait_for_envoy_ready("test-service", timeout=5)

        assert result is True
        mock_requests.assert_called_with(
            f"http://172.20.0.10:{mock_config.ENVOY_METRICS_PORT}/ready", timeout=2
        )

    @patch("requests.get")
    @patch("subprocess.run")
    @patch("time.sleep")
    def test_wait_for_envoy_ready_timeout(
        self, mock_sleep, mock_run, mock_requests, mock_config
    ):
        """Test Envoy readiness check timeout."""
        docker_ops = DockerOps()

        # Mock container not running
        mock_run.return_value = Mock(returncode=0, stdout="")

        # Mock sleep to speed up test
        mock_sleep.return_value = None

        result = docker_ops.wait_for_envoy_ready("test-service", timeout=1)

        assert result is False

    @patch("iac_wrapper.dockerize.DockerOps.container_running")
    @patch("requests.get")
    @patch("subprocess.run")
    @patch("time.sleep")
    def test_wait_for_envoy_ready_http_error(
        self, mock_sleep, mock_run, mock_requests, mock_container_running, mock_config
    ):
        """Test Envoy readiness check with HTTP error."""
        docker_ops = DockerOps()

        # Mock container running
        mock_container_running.return_value = True

        # Mock IP retrieval
        mock_run.return_value = Mock(returncode=0, stdout="172.20.0.10\n")

        # Mock HTTP error
        mock_requests.side_effect = Exception("Connection error")

        result = docker_ops.wait_for_envoy_ready("test-service", timeout=1)

        assert result is False

    @patch("iac_wrapper.dockerize.DockerOps.run_container")
    @patch("iac_wrapper.dockerize.DockerOps.run_envoy_sidecar")
    @patch("iac_wrapper.dockerize.DockerOps.wait_for_envoy_ready")
    @patch("iac_wrapper.dockerize.DockerOps.container_exists")
    @patch("iac_wrapper.dockerize.DockerOps.stop_container")
    @patch("iac_wrapper.dockerize.DockerOps.remove_container")
    def test_start_service_with_envoy_success(
        self,
        mock_remove,
        mock_stop,
        mock_exists,
        mock_wait_ready,
        mock_run_envoy,
        mock_run_container,
        mock_config,
    ):
        """Test successful service start with Envoy."""
        docker_ops = DockerOps()

        # Setup mocks
        mock_exists.return_value = False  # No existing containers
        mock_wait_ready.return_value = True  # Envoy becomes ready
        mock_run_envoy.return_value = "envoy123"
        mock_run_container.return_value = "app456"

        app_id, envoy_id = docker_ops.start_service_with_envoy(
            "test-image:latest",
            "test-service",
            "envoy config content",
            environment={"TEST": "value"},
        )

        assert app_id == "app456"
        assert envoy_id == "envoy123"

        # Verify order: Envoy started first, then app
        assert mock_run_envoy.call_count == 1
        assert mock_run_container.call_count == 1
        assert mock_wait_ready.call_count == 1

    @patch("iac_wrapper.dockerize.DockerOps.run_envoy_sidecar")
    @patch("iac_wrapper.dockerize.DockerOps.wait_for_envoy_ready")
    @patch("iac_wrapper.dockerize.DockerOps.container_exists")
    @patch("iac_wrapper.dockerize.DockerOps.stop_container")
    @patch("iac_wrapper.dockerize.DockerOps.remove_container")
    def test_start_service_with_envoy_envoy_not_ready(
        self,
        mock_remove,
        mock_stop,
        mock_exists,
        mock_wait_ready,
        mock_run_envoy,
        mock_config,
    ):
        """Test service start failure when Envoy doesn't become ready."""
        docker_ops = DockerOps()

        # Setup mocks
        mock_exists.return_value = False
        mock_wait_ready.return_value = False  # Envoy fails to become ready
        mock_run_envoy.return_value = "envoy123"

        with pytest.raises(RuntimeError) as exc_info:
            docker_ops.start_service_with_envoy(
                "test-image:latest", "test-service", "envoy config content"
            )

        assert "failed to become ready" in str(exc_info.value)
        # Verify cleanup was called
        assert mock_stop.call_count == 1
        assert mock_remove.call_count == 1

    @patch("iac_wrapper.dockerize.DockerOps.run_container")
    @patch("iac_wrapper.dockerize.DockerOps.run_envoy_sidecar")
    @patch("iac_wrapper.dockerize.DockerOps.wait_for_envoy_ready")
    @patch("iac_wrapper.dockerize.DockerOps.container_exists")
    @patch("iac_wrapper.dockerize.DockerOps.stop_container")
    @patch("iac_wrapper.dockerize.DockerOps.remove_container")
    def test_start_service_with_envoy_app_failure(
        self,
        mock_remove,
        mock_stop,
        mock_exists,
        mock_wait_ready,
        mock_run_envoy,
        mock_run_container,
        mock_config,
    ):
        """Test cleanup when app container fails to start."""
        docker_ops = DockerOps()

        # Setup mocks
        mock_exists.return_value = False
        mock_wait_ready.return_value = True
        mock_run_envoy.return_value = "envoy123"
        mock_run_container.side_effect = Exception("App start failed")

        with pytest.raises(Exception) as exc_info:
            docker_ops.start_service_with_envoy(
                "test-image:latest", "test-service", "envoy config content"
            )

        assert "App start failed" in str(exc_info.value)
        # Verify Envoy cleanup was called
        assert mock_stop.call_count == 1
        assert mock_remove.call_count == 1

    @patch("iac_wrapper.dockerize.DockerOps.container_exists")
    @patch("iac_wrapper.dockerize.DockerOps.stop_container")
    @patch("iac_wrapper.dockerize.DockerOps.remove_container")
    @patch("iac_wrapper.dockerize.DockerOps.run_envoy_sidecar")
    @patch("iac_wrapper.dockerize.DockerOps.wait_for_envoy_ready")
    @patch("iac_wrapper.dockerize.DockerOps.run_container")
    def test_start_service_with_envoy_cleanup_existing(
        self,
        mock_run_container,
        mock_wait_ready,
        mock_run_envoy,
        mock_remove,
        mock_stop,
        mock_exists,
        mock_config,
    ):
        """Test cleanup of existing containers before starting new ones."""
        docker_ops = DockerOps()

        # Mock existing containers
        mock_exists.side_effect = [True, True]  # Both containers exist
        mock_wait_ready.return_value = True
        mock_run_envoy.return_value = "envoy123"
        mock_run_container.return_value = "app456"

        docker_ops.start_service_with_envoy(
            "test-image:latest", "test-service", "envoy config content"
        )

        # Verify cleanup was called for both containers
        assert mock_stop.call_count == 2  # Stop both app and envoy
        assert mock_remove.call_count == 2  # Remove both app and envoy

        # Verify expected calls for service and envoy containers
        mock_stop.assert_any_call("test-service")
        mock_stop.assert_any_call("test-service-envoy")
        mock_remove.assert_any_call("test-service")
        mock_remove.assert_any_call("test-service-envoy")
