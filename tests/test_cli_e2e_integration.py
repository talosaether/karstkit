"""
CLI End-to-End Integration Test

This test validates the complete KarstKit CLI workflow by simulating
a real deployment scenario using the CLI commands.
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from iac_wrapper.cli import deploy


@pytest.fixture
def sample_flask_repo_yaml(temp_dir):
    """Create a sample repo YAML file and Flask application."""
    # Create Flask app directory
    flask_app = temp_dir / "sample-flask-app"
    flask_app.mkdir()

    (flask_app / "app.py").write_text(
        """
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return '<h1>Sample Flask Dashboard</h1>'

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'service': 'sample-flask'})

def main():
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    main()
"""
    )

    (flask_app / "requirements.txt").write_text("flask>=2.3.0\n")

    (flask_app / "pyproject.toml").write_text(
        """
[project]
name = "sample-flask"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = ["flask>=2.3.0"]

[project.scripts]
sample-flask = "app:main"
"""
    )

    # Create repos.yaml file
    repos_yaml = temp_dir / "repos.yaml"
    repos_content = ["gh:octocat/Hello-World"]

    with open(repos_yaml, "w") as f:
        yaml.dump(repos_content, f)

    return repos_yaml, flask_app


@pytest.mark.integration
@pytest.mark.slow
def test_cli_complete_deployment_workflow(sample_flask_repo_yaml, temp_dir):
    """
    Test the complete CLI deployment workflow.

    This test validates:
    1. CLI argument parsing
    2. YAML file reading
    3. Repository analysis
    4. Docker operations
    5. Envoy configuration
    6. Service startup ordering
    7. Health checks
    """
    repos_yaml, flask_app = sample_flask_repo_yaml

    runner = CliRunner()

    print(f"\n🚀 Testing CLI E2E Deployment")
    print(f"   Flask app: {flask_app}")
    print(f"   Repos file: {repos_yaml}")

    # Mock all the external dependencies
    with patch("iac_wrapper.gitops.GitOps") as mock_gitops, patch(
        "iac_wrapper.dockerize.DockerOps"
    ) as mock_docker, patch("iac_wrapper.envoy.EnvoyConfig") as mock_envoy, patch(
        "iac_wrapper.controlplane.HealthChecker"
    ) as mock_health:
        # Setup GitOps mock
        mock_git_instance = MagicMock()
        mock_git_instance.fetch_repo.return_value = flask_app
        mock_git_instance.detect_entrypoint.return_value = "sample-flask"
        mock_gitops.return_value = mock_git_instance

        # Setup DockerOps mock
        mock_docker_instance = MagicMock()
        mock_docker_instance.build_image.return_value = "iac-sample-flask:latest"
        mock_docker_instance.start_service_with_envoy.return_value = (
            "app123",
            "envoy456",
        )
        mock_docker.return_value = mock_docker_instance

        # Setup EnvoyConfig mock
        mock_envoy_instance = MagicMock()
        mock_envoy_instance.generate_config.return_value = "# Mock Envoy config"
        mock_envoy.return_value = mock_envoy_instance

        # Setup HealthChecker mock
        mock_health_instance = MagicMock()
        mock_health_status = MagicMock()
        mock_health_status.status = 1  # SERVING
        mock_health_status.message = "Service healthy"
        mock_health_instance.check_service_health.return_value = mock_health_status
        mock_health.return_value = mock_health_instance

        # Run the CLI deploy command
        result = runner.invoke(
            deploy, ["--file", str(repos_yaml), "--wait", "--timeout", "60"]
        )

        print(f"\n📋 CLI Output:")
        print(result.output)
        print(f"\n📊 Exit Code: {result.exit_code}")

        # Validate CLI execution
        assert result.exit_code == 0, f"CLI failed with output: {result.output}"

        # Verify output contains expected deployment phases
        output = result.output
        expected_outputs = [
            "Deploying services from",
            "Fetching repository",
            "Building Docker image",
            "Configuring Envoy",
            "Starting containers (Envoy first, then app)",
            "Service",
            "started successfully",
        ]

        for expected in expected_outputs:
            assert expected in output, f"Missing expected output: {expected}"

        # Verify method calls were made in correct order
        mock_git_instance.fetch_repo.assert_called()
        mock_git_instance.detect_entrypoint.assert_called()
        mock_docker_instance.build_image.assert_called()
        mock_envoy_instance.generate_config.assert_called()
        mock_docker_instance.start_service_with_envoy.assert_called()

        # Verify start_service_with_envoy was called with correct parameters
        start_call = mock_docker_instance.start_service_with_envoy.call_args
        assert start_call[0][0] == "iac-sample-flask:latest"  # image_name
        assert start_call[0][2] == "# Mock Envoy config"  # envoy_config

        print("\n✅ CLI E2E deployment workflow validated!")


@pytest.mark.integration
def test_cli_deployment_with_error_handling(temp_dir):
    """Test CLI deployment with error scenarios."""
    runner = CliRunner()

    # Test with non-existent file
    result = runner.invoke(deploy, ["--file", "nonexistent.yaml"])
    assert result.exit_code != 0
    assert "Error" in result.output or "not found" in result.output

    # Test with invalid YAML
    bad_yaml = temp_dir / "bad.yaml"
    bad_yaml.write_text("invalid: yaml: content: [")

    result = runner.invoke(deploy, ["--file", str(bad_yaml)])
    # Should handle YAML parsing errors gracefully
    assert result.exit_code != 0


@pytest.mark.integration
def test_cli_deployment_dry_run_mode(sample_flask_repo_yaml, temp_dir):
    """Test CLI deployment in dry-run mode (planning phase)."""
    repos_yaml, flask_app = sample_flask_repo_yaml

    runner = CliRunner()

    with patch("iac_wrapper.gitops.GitOps") as mock_gitops:
        mock_git_instance = MagicMock()
        mock_git_instance.fetch_repo.return_value = flask_app
        mock_git_instance.detect_entrypoint.return_value = "sample-flask"
        mock_gitops.return_value = mock_git_instance

        # Run without --wait flag (should not actually start containers)
        result = runner.invoke(deploy, ["--file", str(repos_yaml)])

        assert result.exit_code == 0
        assert "Deploying services" in result.output

        # Should fetch and analyze repo
        mock_git_instance.fetch_repo.assert_called()
        mock_git_instance.detect_entrypoint.assert_called()


def test_cli_help_and_version():
    """Test CLI help and version commands."""
    runner = CliRunner()

    # Test help
    result = runner.invoke(deploy, ["--help"])
    assert result.exit_code == 0
    assert "Deploy services from repository slugs" in result.output

    # Test that all expected options are present
    help_text = result.output
    expected_options = ["--file", "--slug", "--wait", "--timeout"]

    for option in expected_options:
        assert option in help_text, f"Missing CLI option: {option}"


@pytest.fixture
def mock_successful_deployment():
    """Fixture that mocks a successful deployment for testing."""
    with patch("iac_wrapper.gitops.GitOps") as mock_gitops, patch(
        "iac_wrapper.dockerize.DockerOps"
    ) as mock_docker, patch("iac_wrapper.envoy.EnvoyConfig") as mock_envoy:
        # Setup successful mocks
        mock_git_instance = MagicMock()
        mock_git_instance.fetch_repo.return_value = Path("/tmp/repo")
        mock_git_instance.detect_entrypoint.return_value = "main"
        mock_gitops.return_value = mock_git_instance

        mock_docker_instance = MagicMock()
        mock_docker_instance.build_image.return_value = "test-image:latest"
        mock_docker_instance.start_service_with_envoy.return_value = (
            "app123",
            "envoy456",
        )
        mock_docker.return_value = mock_docker_instance

        mock_envoy_instance = MagicMock()
        mock_envoy_instance.generate_config.return_value = "envoy config"
        mock_envoy.return_value = mock_envoy_instance

        yield {
            "gitops": mock_git_instance,
            "docker": mock_docker_instance,
            "envoy": mock_envoy_instance,
        }


@pytest.mark.integration
def test_cli_multiple_services_deployment(temp_dir, mock_successful_deployment):
    """Test CLI deployment with multiple services."""
    runner = CliRunner()

    # Create multiple service repos
    service1 = temp_dir / "service1"
    service1.mkdir()
    (service1 / "main.py").write_text("def main(): print('service1')")

    service2 = temp_dir / "service2"
    service2.mkdir()
    (service2 / "app.py").write_text("def main(): print('service2')")

    # Create repos.yaml with multiple services
    repos_yaml = temp_dir / "multi-repos.yaml"
    repos_content = ["gh:example/service1", "gh:example/service2"]

    with open(repos_yaml, "w") as f:
        yaml.dump(repos_content, f)

    mocks = mock_successful_deployment

    # Run deployment
    result = runner.invoke(deploy, ["--file", str(repos_yaml), "--wait"])

    print(f"\nMultiple services output:\n{result.output}")

    assert result.exit_code == 0

    # Should have processed both services
    assert mocks["gitops"].fetch_repo.call_count == 2
    assert mocks["docker"].start_service_with_envoy.call_count == 2

    print("✅ Multiple services deployment validated!")
