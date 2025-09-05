"""Pytest configuration and fixtures."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from iac_wrapper.config import config


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    with patch("iac_wrapper.config.config") as mock:
        mock.SUPABASE_URL = "https://test.supabase.co"
        mock.SUPABASE_SERVICE_ROLE_KEY = "test-key"
        mock.DOCKER_NETWORK_NAME = "testnet"
        mock.GRPC_PORT = 50051
        mock.ENVOY_INBOUND_PORT = 15000
        mock.ENVOY_OUTBOUND_PORT = 15001
        mock.ENVOY_METRICS_PORT = 9901
        mock.DEBUG = True
        mock.LOG_LEVEL = "DEBUG"
        mock.BASE_DIR = Path(__file__).parent.parent
        mock.SECRETS_DIR = mock.BASE_DIR / "secrets"
        mock.INFRA_DIR = mock.BASE_DIR / "infra"
        mock.TEMPLATES_DIR = mock.INFRA_DIR / "templates"
        yield mock


@pytest.fixture
def sample_repo(temp_dir):
    """Create a sample repository structure for testing."""
    repo_dir = temp_dir / "sample-repo"
    repo_dir.mkdir()

    # Create main.py
    main_py = repo_dir / "main.py"
    main_py.write_text(
        """
def main():
    print("Hello, World!")
    return 0

if __name__ == "__main__":
    main()
"""
    )

    # Create requirements.txt
    requirements_txt = repo_dir / "requirements.txt"
    requirements_txt.write_text("flask>=2.3.0\nrequests>=2.31.0\n")

    # Create pyproject.toml
    pyproject_toml = repo_dir / "pyproject.toml"
    pyproject_toml.write_text(
        """
[project]
name = "sample-app"
version = "0.1.0"
description = "Sample application"
requires-python = ">=3.11"

[project.scripts]
sample-app = "main:main"
"""
    )

    return repo_dir


@pytest.fixture
def sample_repo_with_package(temp_dir):
    """Create a sample repository with package structure."""
    repo_dir = temp_dir / "sample-package"
    repo_dir.mkdir()

    # Create package directory
    package_dir = repo_dir / "sample_package"
    package_dir.mkdir()

    # Create __init__.py
    init_py = package_dir / "__init__.py"
    init_py.write_text("# Sample package")

    # Create __main__.py
    main_py = package_dir / "__main__.py"
    main_py.write_text(
        """
def main():
    print("Hello from package!")
    return 0

if __name__ == "__main__":
    main()
"""
    )

    # Create requirements.txt
    requirements_txt = repo_dir / "requirements.txt"
    requirements_txt.write_text("flask>=2.3.0\n")

    return repo_dir


@pytest.fixture
def mock_docker():
    """Mock Docker operations."""
    with patch("subprocess.run") as mock:
        mock.return_value.returncode = 0
        mock.return_value.stdout = "container_id_123"
        mock.return_value.stderr = ""
        yield mock


@pytest.fixture
def mock_requests():
    """Mock requests for HTTP operations."""
    with patch("requests.get") as mock:
        mock.return_value.status_code = 200
        mock.return_value.raise_for_status.return_value = None
        mock.return_value.iter_content.return_value = [b"test content"]
        yield mock


@pytest.fixture
def mock_grpc():
    """Mock gRPC operations."""
    with patch("grpc.secure_channel") as mock_channel, patch(
        "grpc.insecure_channel"
    ) as mock_insecure:
        mock_channel.return_value.__enter__.return_value = Mock()
        mock_insecure.return_value.__enter__.return_value = Mock()
        yield mock_channel, mock_insecure


@pytest.fixture
def mock_supabase():
    """Mock Supabase authentication."""
    with patch("requests.get") as mock:
        mock.return_value.status_code = 200
        mock.return_value.json.return_value = {
            "keys": [{"kid": "test-key-id", "kty": "RSA", "n": "test-n", "e": "AQAB"}]
        }
        yield mock
