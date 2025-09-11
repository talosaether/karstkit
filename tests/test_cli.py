"""Tests for CLI functionality."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
from iac_wrapper.cli import main, deploy, plan, apply, destroy, health, logs


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


class TestCLIMain:
    """Test main CLI group."""

    def test_main_help(self, runner):
        """Test main command help."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Infrastructure-as-Code deployment wrapper" in result.output

    def test_main_version(self, runner):
        """Test version option."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestDeployCommand:
    """Test deploy command."""

    @patch("iac_wrapper.gitops.GitOps")
    @patch("iac_wrapper.dockerize.DockerOps")
    @patch("iac_wrapper.envoy.EnvoyConfig")
    @patch("iac_wrapper.controlplane.HealthChecker")
    def test_deploy_with_slug(
        self, mock_health, mock_envoy, mock_docker, mock_git, runner
    ):
        """Test deploy command with slug option."""
        # Setup mocks
        mock_git_instance = Mock()
        mock_git_instance.fetch_repo.return_value = "/tmp/repo"
        mock_git_instance.detect_entrypoint.return_value = "main"
        mock_git.return_value = mock_git_instance

        mock_docker_instance = Mock()
        mock_docker_instance.build_image.return_value = "test-image:latest"
        mock_docker_instance.run_container.return_value = "container123"
        mock_docker_instance.run_envoy_sidecar.return_value = "envoy123"
        mock_docker_instance.container_exists.return_value = False
        mock_docker.return_value = mock_docker_instance

        mock_envoy_instance = Mock()
        mock_envoy_instance.generate_config.return_value = "envoy config"
        mock_envoy.return_value = mock_envoy_instance

        mock_health_instance = Mock()
        mock_health_status = Mock()
        mock_health_status.status = 1  # SERVING
        mock_health_instance.check_service_health.return_value = mock_health_status
        mock_health.return_value = mock_health_instance

        result = runner.invoke(deploy, ["--slug", "gh:testuser/testrepo"])
        assert result.exit_code == 0
        assert "Deploying 1 service(s)" in result.output
        assert "Deployed successfully" in result.output

    def test_deploy_with_file(self, runner, temp_dir):
        """Test deploy command with file option."""
        # Create test YAML file
        test_file = temp_dir / "test.yaml"
        test_file.write_text("- gh:testuser/testrepo")

        with patch("iac_wrapper.gitops.GitOps") as mock_git, patch(
            "iac_wrapper.dockerize.DockerOps"
        ) as mock_docker, patch("iac_wrapper.envoy.EnvoyConfig") as mock_envoy, patch(
            "iac_wrapper.controlplane.HealthChecker"
        ) as mock_health:
            # Setup mocks (similar to above)
            mock_git_instance = Mock()
            mock_git_instance.fetch_repo.return_value = "/tmp/repo"
            mock_git_instance.detect_entrypoint.return_value = "main"
            mock_git.return_value = mock_git_instance

            mock_docker_instance = Mock()
            mock_docker_instance.build_image.return_value = "test-image:latest"
            mock_docker_instance.run_container.return_value = "container123"
            mock_docker_instance.run_envoy_sidecar.return_value = "envoy123"
            mock_docker_instance.container_exists.return_value = False
            mock_docker.return_value = mock_docker_instance

            mock_envoy_instance = Mock()
            mock_envoy_instance.generate_config.return_value = "envoy config"
            mock_envoy.return_value = mock_envoy_instance

            mock_health_instance = Mock()
            mock_health_status = Mock()
            mock_health_status.status = 1
            mock_health_instance.check_service_health.return_value = mock_health_status
            mock_health.return_value = mock_health_instance

            result = runner.invoke(deploy, ["--file", str(test_file)])
            assert result.exit_code == 0

    def test_deploy_invalid_slug(self, runner):
        """Test deploy command with invalid slug."""
        result = runner.invoke(deploy, ["--slug", "invalid-slug"])
        assert result.exit_code == 1
        assert "Invalid slug format" in result.output

    def test_deploy_no_slugs(self, runner):
        """Test deploy command with no slugs provided."""
        result = runner.invoke(deploy, [])
        assert result.exit_code == 1
        assert "No slugs provided" in result.output

    def test_deploy_file_not_found(self, runner):
        """Test deploy command with non-existent file."""
        result = runner.invoke(deploy, ["--file", "nonexistent.yaml"])
        assert result.exit_code == 2  # Click file not found error

    @patch("iac_wrapper.gitops.GitOps")
    def test_deploy_entrypoint_not_found(self, mock_git, runner):
        """Test deploy when entrypoint cannot be detected."""
        mock_git_instance = Mock()
        mock_git_instance.fetch_repo.return_value = "/tmp/repo"
        mock_git_instance.detect_entrypoint.return_value = None  # No entrypoint found
        mock_git.return_value = mock_git_instance

        result = runner.invoke(deploy, ["--slug", "gh:testuser/testrepo"])
        assert result.exit_code == 1
        assert "No entrypoint detected" in result.output

    @patch("iac_wrapper.gitops.GitOps")
    def test_deploy_build_failure(self, mock_git, runner):
        """Test deploy with Docker build failure."""
        mock_git_instance = Mock()
        mock_git_instance.fetch_repo.return_value = "/tmp/repo"
        mock_git_instance.detect_entrypoint.return_value = "main"
        mock_git.return_value = mock_git_instance

        with patch("iac_wrapper.dockerize.DockerOps") as mock_docker:
            mock_docker_instance = Mock()
            mock_docker_instance.build_image.side_effect = RuntimeError("Build failed")
            mock_docker.return_value = mock_docker_instance

            result = runner.invoke(deploy, ["--slug", "gh:testuser/testrepo"])
            assert result.exit_code == 1
            assert "Build failed" in result.output

    def test_deploy_json_file(self, runner, temp_dir):
        """Test deploy command with JSON file."""
        # Create test JSON file
        test_file = temp_dir / "test.json"
        test_data = {"slugs": ["gh:testuser/testrepo"]}
        test_file.write_text(json.dumps(test_data))

        with patch("iac_wrapper.gitops.GitOps") as mock_git, patch(
            "iac_wrapper.dockerize.DockerOps"
        ) as mock_docker, patch("iac_wrapper.envoy.EnvoyConfig") as mock_envoy, patch(
            "iac_wrapper.controlplane.HealthChecker"
        ) as mock_health:
            # Setup mocks
            self._setup_successful_mocks(mock_git, mock_docker, mock_envoy, mock_health)

            result = runner.invoke(deploy, ["--file", str(test_file)])
            assert result.exit_code == 0

    def test_deploy_no_wait(self, runner):
        """Test deploy command with --no-wait option."""
        with patch("iac_wrapper.gitops.GitOps") as mock_git, patch(
            "iac_wrapper.dockerize.DockerOps"
        ) as mock_docker, patch("iac_wrapper.envoy.EnvoyConfig") as mock_envoy:
            # Setup mocks
            mock_git_instance = Mock()
            mock_git_instance.fetch_repo.return_value = "/tmp/repo"
            mock_git_instance.detect_entrypoint.return_value = "main"
            mock_git.return_value = mock_git_instance

            mock_docker_instance = Mock()
            mock_docker_instance.build_image.return_value = "test-image:latest"
            mock_docker_instance.run_container.return_value = "container123"
            mock_docker_instance.run_envoy_sidecar.return_value = "envoy123"
            mock_docker_instance.container_exists.return_value = False
            mock_docker.return_value = mock_docker_instance

            mock_envoy_instance = Mock()
            mock_envoy_instance.generate_config.return_value = "envoy config"
            mock_envoy.return_value = mock_envoy_instance

            result = runner.invoke(
                deploy, ["--slug", "gh:testuser/testrepo", "--no-wait"]
            )
            assert result.exit_code == 0
            # Should not perform health checks

    def _setup_successful_mocks(self, mock_git, mock_docker, mock_envoy, mock_health):
        """Helper to setup successful mocks."""
        mock_git_instance = Mock()
        mock_git_instance.fetch_repo.return_value = "/tmp/repo"
        mock_git_instance.detect_entrypoint.return_value = "main"
        mock_git.return_value = mock_git_instance

        mock_docker_instance = Mock()
        mock_docker_instance.build_image.return_value = "test-image:latest"
        mock_docker_instance.run_container.return_value = "container123"
        mock_docker_instance.run_envoy_sidecar.return_value = "envoy123"
        mock_docker_instance.container_exists.return_value = False
        mock_docker.return_value = mock_docker_instance

        mock_envoy_instance = Mock()
        mock_envoy_instance.generate_config.return_value = "envoy config"
        mock_envoy.return_value = mock_envoy_instance

        if mock_health:
            mock_health_instance = Mock()
            mock_health_status = Mock()
            mock_health_status.status = 1
            mock_health_instance.check_service_health.return_value = mock_health_status
            mock_health.return_value = mock_health_instance


class TestPlanCommand:
    """Test plan command."""

    @patch("subprocess.run")
    def test_plan_success(self, mock_run, runner):
        """Test successful terraform plan."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Plan: 3 to add, 0 to change, 0 to destroy."

        result = runner.invoke(plan)
        assert result.exit_code == 0
        assert "Plan: 3 to add" in result.output

    @patch("subprocess.run")
    def test_plan_failure(self, mock_run, runner):
        """Test terraform plan failure."""
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Error: Invalid configuration"

        result = runner.invoke(plan)
        assert result.exit_code == 1
        assert "Error: Invalid configuration" in result.output


class TestApplyCommand:
    """Test apply command."""

    @patch("subprocess.run")
    def test_apply_success(self, mock_run, runner):
        """Test successful terraform apply."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "Apply complete! Resources: 3 added, 0 changed, 0 destroyed."
        )

        result = runner.invoke(apply)
        assert result.exit_code == 0
        assert "Apply complete!" in result.output

    @patch("subprocess.run")
    def test_apply_failure(self, mock_run, runner):
        """Test terraform apply failure."""
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Error: Resource already exists"

        result = runner.invoke(apply)
        assert result.exit_code == 1
        assert "Error: Resource already exists" in result.output


class TestDestroyCommand:
    """Test destroy command."""

    @patch("subprocess.run")
    @patch("iac_wrapper.dockerize.DockerOps")
    def test_destroy_with_confirmation(self, mock_docker, mock_run, runner):
        """Test destroy command with confirmation."""
        # Mock Docker operations
        mock_docker_instance = Mock()
        mock_docker_instance.stop_container.return_value = None
        mock_docker_instance.remove_container.return_value = None
        mock_docker.return_value = mock_docker_instance

        # Mock subprocess calls
        def side_effect(cmd, **kwargs):
            if cmd[0] == "docker" and cmd[1] == "ps":
                result = Mock()
                result.returncode = 0
                result.stdout = "test-container\ntest-container-envoy"
                return result
            elif cmd[0] == "terraform":
                result = Mock()
                result.returncode = 0
                result.stdout = "Destroy complete!"
                return result
            return Mock(returncode=0)

        mock_run.side_effect = side_effect

        # Provide 'y' to confirmation prompt
        result = runner.invoke(destroy, input="y\n")
        assert result.exit_code == 0
        assert "Destroy complete!" in result.output

    @patch("subprocess.run")
    def test_destroy_cancelled(self, mock_run, runner):
        """Test destroy command cancelled by user."""
        result = runner.invoke(destroy, input="n\n")
        assert result.exit_code == 0
        # Should exit without running terraform destroy


class TestHealthCommand:
    """Test health command."""

    @patch("iac_wrapper.controlplane.HealthChecker")
    def test_health_specific_service(self, mock_health, runner):
        """Test health check for specific service."""
        mock_health_instance = Mock()
        mock_health_status = Mock()
        mock_health_status.status = 1  # SERVING
        mock_health_status.message = "Service is healthy"
        mock_health_status.timestamp = "2023-01-01T00:00:00Z"
        mock_health_instance.check_service_health.return_value = mock_health_status
        mock_health.return_value = mock_health_instance

        result = runner.invoke(health, ["--service", "test-service"])
        assert result.exit_code == 0
        assert "Status: SERVING" in result.output
        assert "Service is healthy" in result.output

    @patch("iac_wrapper.controlplane.HealthChecker")
    @patch("subprocess.run")
    def test_health_all_services(self, mock_run, mock_health, runner):
        """Test health check for all services."""
        # Mock docker ps output
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "service1\nservice2\nservice1-envoy"

        # Mock health checker
        mock_health_instance = Mock()
        mock_health_status = Mock()
        mock_health_status.status = 1
        mock_health_status.message = "Healthy"
        mock_health_instance.check_all_services.return_value = {
            "service1": mock_health_status,
            "service2": mock_health_status,
        }
        mock_health.return_value = mock_health_instance

        result = runner.invoke(health)
        assert result.exit_code == 0
        assert "service1: SERVING" in result.output
        assert "service2: SERVING" in result.output

    @patch("subprocess.run")
    def test_health_no_services(self, mock_run, runner):
        """Test health check when no services are running."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""

        result = runner.invoke(health)
        assert result.exit_code == 0
        assert "No services found" in result.output


class TestLogsCommand:
    """Test logs command."""

    @patch("iac_wrapper.dockerize.DockerOps")
    def test_logs_specific_service(self, mock_docker, runner):
        """Test logs for specific service."""
        mock_docker_instance = Mock()
        mock_docker_instance.get_container_logs.return_value = "Test log output"
        mock_docker.return_value = mock_docker_instance

        result = runner.invoke(logs, ["--service", "test-service"])
        assert result.exit_code == 0
        assert "Test log output" in result.output

    @patch("iac_wrapper.dockerize.DockerOps")
    @patch("subprocess.run")
    def test_logs_all_services(self, mock_run, mock_docker, runner):
        """Test logs for all services."""
        # Mock docker ps output
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "service1\nservice2\nservice1-envoy"

        # Mock Docker operations
        mock_docker_instance = Mock()
        mock_docker_instance.get_container_logs.return_value = "Service logs"
        mock_docker.return_value = mock_docker_instance

        result = runner.invoke(logs)
        assert result.exit_code == 0
        assert "=== Logs for service1 ===" in result.output
        assert "=== Logs for service2 ===" in result.output

    @patch("subprocess.run")
    def test_logs_no_services(self, mock_run, runner):
        """Test logs when no services are running."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""

        result = runner.invoke(logs)
        assert result.exit_code == 0
        assert "No services found" in result.output

    @patch("iac_wrapper.dockerize.DockerOps")
    def test_logs_with_tail(self, mock_docker, runner):
        """Test logs with tail option."""
        mock_docker_instance = Mock()
        mock_docker_instance.get_container_logs.return_value = "Recent logs"
        mock_docker.return_value = mock_docker_instance

        result = runner.invoke(logs, ["--service", "test-service", "--tail", "50"])
        assert result.exit_code == 0
        assert "Recent logs" in result.output
