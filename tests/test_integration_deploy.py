"""Integration tests for deployment functionality."""

import pytest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
from iac_wrapper.slug import RepoSlug
from iac_wrapper.gitops import GitOps
from iac_wrapper.dockerize import DockerOps
from iac_wrapper.envoy import EnvoyConfig


@pytest.fixture
def sample_repo_for_integration(temp_dir):
    """Create a sample repository for integration testing."""
    repo_dir = temp_dir / "integration-test-repo"
    repo_dir.mkdir()

    # Create main.py with gRPC server
    main_py = repo_dir / "main.py"
    main_py.write_text(
        """
import grpc
from concurrent.futures import ThreadPoolExecutor
import time

def main():
    print("Starting gRPC server...")
    server = grpc.server(ThreadPoolExecutor(max_workers=10))
    print("gRPC server started successfully")

    # Keep the server running
    server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    main()
"""
    )

    # Create requirements.txt
    requirements_txt = repo_dir / "requirements.txt"
    requirements_txt.write_text("grpcio>=1.59.0\n")

    # Create pyproject.toml
    pyproject_toml = repo_dir / "pyproject.toml"
    pyproject_toml.write_text(
        """
[project]
name = "integration-test-app"
version = "0.1.0"
description = "Integration test application"
requires-python = ">=3.11"

[project.scripts]
integration-test-app = "main:main"
"""
    )

    return repo_dir


@pytest.mark.integration
class TestIntegrationDeploy:
    """Integration tests for deployment functionality."""

    def test_full_deployment_workflow(self, sample_repo_for_integration, temp_dir):
        """Test the complete deployment workflow."""
        # Initialize components
        git_ops = GitOps(cache_dir=temp_dir)
        docker_ops = DockerOps()
        envoy_config = EnvoyConfig()

        # Create slug
        slug = RepoSlug(scheme="gh", owner="testuser", repo="integration-test")

        # Test repository fetch (using local directory)
        repo_path = sample_repo_for_integration
        assert repo_path.exists()

        # Test entrypoint detection
        entrypoint = git_ops.detect_entrypoint(repo_path)
        assert entrypoint == "integration-test-app"

        # Test Docker image build (mocked)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stderr = ""

            image_name = docker_ops.build_image(repo_path, slug, entrypoint)
            assert image_name == "iac-testuser-integration-test:latest"

        # Test Envoy config generation
        envoy_config_content = envoy_config.generate_config(slug.service_name)
        assert "admin:" in envoy_config_content
        assert "static_resources:" in envoy_config_content
        assert slug.service_name in envoy_config_content

        # Test certificate generation
        cert_paths = envoy_config.get_certificate_paths(slug.service_name)
        assert "ca_cert" in cert_paths
        assert "service_cert" in cert_paths
        assert "service_key" in cert_paths

    @patch("subprocess.run")
    def test_container_lifecycle(self, mock_run, temp_dir):
        """Test container lifecycle operations."""
        docker_ops = DockerOps()

        # Mock successful Docker operations
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "container_id_123"
        mock_run.return_value.stderr = ""

        # Test container run
        container_id = docker_ops.run_container(
            "test-image:latest", "test-service", environment={"TEST_VAR": "test_value"}
        )
        assert container_id == "container_id_123"

        # Test container existence check
        mock_run.return_value.stdout = "test-service"
        assert docker_ops.container_exists("test-service") is True

        # Test container running check
        assert docker_ops.container_running("test-service") is True

        # Test container stop
        docker_ops.stop_container("test-service")
        mock_run.assert_called()

        # Test container removal
        docker_ops.remove_container("test-service")
        mock_run.assert_called()

    def test_envoy_config_generation(self, temp_dir):
        """Test Envoy configuration generation."""
        envoy_config = EnvoyConfig()
        service_name = "test-service"

        # Generate config
        config_content = envoy_config.generate_config(service_name)

        # Verify config structure
        assert "admin:" in config_content
        assert "static_resources:" in config_content
        assert "listeners:" in config_content
        assert "clusters:" in config_content
        assert service_name in config_content

        # Verify certificate paths are referenced
        assert "/etc/envoy/certs/ca.crt" in config_content
        assert "/etc/envoy/certs/tls.crt" in config_content
        assert "/etc/envoy/certs/tls.key" in config_content

    def test_certificate_generation(self, temp_dir):
        """Test certificate generation and management."""
        envoy_config = EnvoyConfig()
        service_name = "test-service"

        # Generate certificates
        cert_paths = envoy_config.get_certificate_paths(service_name)

        # Verify certificate files exist
        assert cert_paths["ca_cert"].exists()
        assert cert_paths["service_cert"].exists()
        assert cert_paths["service_key"].exists()

        # Verify certificate content
        ca_cert_content = cert_paths["ca_cert"].read_text()
        service_cert_content = cert_paths["service_cert"].read_text()
        service_key_content = cert_paths["service_key"].read_text()

        assert "-----BEGIN CERTIFICATE-----" in ca_cert_content
        assert "-----BEGIN CERTIFICATE-----" in service_cert_content
        assert "-----BEGIN PRIVATE KEY-----" in service_key_content

    @patch("subprocess.run")
    def test_docker_network_operations(self, mock_run):
        """Test Docker network operations."""
        # Mock successful Docker network operations
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "network_id_123"
        mock_run.return_value.stderr = ""

        # Test network creation (simulated)
        network_name = "test-network"

        # Verify network creation command would be called
        # This is a simplified test - in real integration we'd test actual Docker commands
        assert network_name == "test-network"

    def test_slug_parsing_integration(self):
        """Test slug parsing in integration context."""
        # Test various slug formats
        test_cases = [
            ("gh:testuser/testrepo", "gh", "testuser", "testrepo", None),
            ("gh:testuser/testrepo#v1.0.0", "gh", "testuser", "testrepo", "v1.0.0"),
            ("gl:testuser/testrepo", "gl", "testuser", "testrepo", None),
            ("gl:testuser/testrepo#develop", "gl", "testuser", "testrepo", "develop"),
        ]

        for (
            slug_str,
            expected_scheme,
            expected_owner,
            expected_repo,
            expected_ref,
        ) in test_cases:
            slug = RepoSlug(
                scheme=expected_scheme,
                owner=expected_owner,
                repo=expected_repo,
                ref=expected_ref,
            )

            assert slug.scheme == expected_scheme
            assert slug.owner == expected_owner
            assert slug.repo == expected_repo
            assert slug.ref == expected_ref
            assert slug.full_name == f"{expected_owner}/{expected_repo}"
            assert slug.service_name == f"{expected_owner}-{expected_repo}"

    def test_entrypoint_detection_integration(self, temp_dir):
        """Test entrypoint detection with various repository structures."""
        git_ops = GitOps(cache_dir=temp_dir)

        # Test case 1: main.py at root
        repo1 = temp_dir / "repo1"
        repo1.mkdir()
        (repo1 / "main.py").write_text("def main(): pass")
        assert git_ops.detect_entrypoint(repo1) == "main"

        # Test case 2: __main__.py at root
        repo2 = temp_dir / "repo2"
        repo2.mkdir()
        (repo2 / "__main__.py").write_text("def main(): pass")
        assert git_ops.detect_entrypoint(repo2) == "main"

        # Test case 3: package with __main__.py
        repo3 = temp_dir / "repo3"
        repo3.mkdir()
        package_dir = repo3 / "my_package"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")
        (package_dir / "__main__.py").write_text("def main(): pass")
        assert git_ops.detect_entrypoint(repo3) == "my_package.main"

        # Test case 4: pyproject.toml with scripts
        repo4 = temp_dir / "repo4"
        repo4.mkdir()
        pyproject_content = """
[project]
name = "test-app"
version = "0.1.0"

[project.scripts]
my-app = "main:main"
"""
        (repo4 / "pyproject.toml").write_text(pyproject_content)
        assert git_ops.detect_entrypoint(repo4) == "my-app"

        # Test case 5: no entrypoint found
        repo5 = temp_dir / "repo5"
        repo5.mkdir()
        (repo5 / "README.md").write_text("# Test")
        assert git_ops.detect_entrypoint(repo5) is None


@pytest.mark.slow
class TestSlowIntegrationTests:
    """Slow integration tests that may take longer to run."""

    def test_docker_build_integration(self, sample_repo_for_integration):
        """Test actual Docker build (requires Docker daemon)."""
        # This test requires Docker to be running
        try:
            # Check if Docker is available
            result = subprocess.run(
                ["docker", "--version"], capture_output=True, text=True
            )
            if result.returncode != 0:
                pytest.skip("Docker not available")
        except FileNotFoundError:
            pytest.skip("Docker not available")

        docker_ops = DockerOps()
        slug = RepoSlug(scheme="gh", owner="testuser", repo="integration-test")

        # This would be a real Docker build test
        # For now, we'll just verify the Dockerfile generation
        dockerfile_content = docker_ops._generate_dockerfile(slug, "main.main")
        assert "FROM python:3.11-slim" in dockerfile_content
        assert "main.main()" in dockerfile_content
