"""Tests for configuration functionality."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, Mock
from iac_wrapper.config import Config, config


class TestConfig:
    """Test Config class."""

    def test_init_with_defaults(self):
        """Test Config initialization with default values."""
        with patch.dict(os.environ, {}, clear=True):
            config_obj = Config()

            # Check default values
            assert config_obj.DEBUG is False
            assert config_obj.LOG_LEVEL == "INFO"
            assert config_obj.GRPC_PORT == 50051
            assert config_obj.ENVOY_INBOUND_PORT == 15000
            assert config_obj.ENVOY_OUTBOUND_PORT == 15001
            assert config_obj.ENVOY_METRICS_PORT == 9901
            assert config_obj.DOCKER_NETWORK_NAME == "iacnet"
            assert config_obj.OTEL_EXPORTER_OTLP_ENDPOINT == ""

    def test_init_with_env_vars(self):
        """Test Config initialization with environment variables."""
        env_vars = {
            "DEBUG": "true",
            "LOG_LEVEL": "DEBUG",
            "GRPC_PORT": "50052",
            "ENVOY_INBOUND_PORT": "15002",
            "ENVOY_OUTBOUND_PORT": "15003",
            "ENVOY_METRICS_PORT": "9902",
            "DOCKER_NETWORK_NAME": "customnet",
            "SUPABASE_URL": "https://custom.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "custom-key",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config_obj = Config()

            assert config_obj.DEBUG is True
            assert config_obj.LOG_LEVEL == "DEBUG"
            assert config_obj.GRPC_PORT == 50052
            assert config_obj.ENVOY_INBOUND_PORT == 15002
            assert config_obj.ENVOY_OUTBOUND_PORT == 15003
            assert config_obj.ENVOY_METRICS_PORT == 9902
            assert config_obj.DOCKER_NETWORK_NAME == "customnet"
            assert config_obj.SUPABASE_URL == "https://custom.supabase.co"
            assert config_obj.SUPABASE_SERVICE_ROLE_KEY == "custom-key"
            assert config_obj.OTEL_EXPORTER_OTLP_ENDPOINT == "http://localhost:4317"

    def test_bool_conversion(self):
        """Test boolean conversion from environment variables."""
        test_cases = [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("", False),
            ("invalid", False),
        ]

        for env_value, expected in test_cases:
            with patch.dict(os.environ, {"DEBUG": env_value}, clear=True):
                config_obj = Config()
                assert config_obj.DEBUG is expected

    def test_int_conversion(self):
        """Test integer conversion from environment variables."""
        with patch.dict(os.environ, {"GRPC_PORT": "8080"}, clear=True):
            config_obj = Config()
            assert config_obj.GRPC_PORT == 8080

    def test_int_conversion_invalid(self):
        """Test integer conversion with invalid value."""
        with patch.dict(os.environ, {"GRPC_PORT": "invalid"}, clear=True):
            config_obj = Config()
            # Should fall back to default
            assert config_obj.GRPC_PORT == 50051

    def test_path_properties(self):
        """Test path properties."""
        config_obj = Config()

        # Check that paths are Path objects
        assert isinstance(config_obj.BASE_DIR, Path)
        assert isinstance(config_obj.SECRETS_DIR, Path)
        assert isinstance(config_obj.INFRA_DIR, Path)
        assert isinstance(config_obj.TEMPLATES_DIR, Path)

        # Check path relationships
        assert config_obj.SECRETS_DIR == config_obj.BASE_DIR / "secrets"
        assert config_obj.INFRA_DIR == config_obj.BASE_DIR / "infra"
        assert config_obj.TEMPLATES_DIR == config_obj.INFRA_DIR / "templates"

    def test_dotenv_loading(self):
        """Test .env file loading."""
        # Create a temporary .env file content
        env_content = "TEST_VAR=test_value\nDEBUG=true\n"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = (
                    env_content
                )

                with patch("dotenv.load_dotenv") as mock_load_dotenv:
                    config_obj = Config()
                    mock_load_dotenv.assert_called_once()

    def test_secrets_dir_creation(self):
        """Test that secrets directory is created."""
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            config_obj = Config()
            mock_mkdir.assert_called_with(parents=True, exist_ok=True)


class TestConfigSingleton:
    """Test global config singleton."""

    def test_config_singleton(self):
        """Test that config is a singleton instance."""
        assert isinstance(config, Config)

        # Import again to verify it's the same instance
        from iac_wrapper.config import config as config2

        assert config is config2

    def test_config_attributes_accessible(self):
        """Test that config attributes are accessible."""
        assert hasattr(config, "DEBUG")
        assert hasattr(config, "LOG_LEVEL")
        assert hasattr(config, "GRPC_PORT")
        assert hasattr(config, "SUPABASE_URL")
        assert hasattr(config, "BASE_DIR")
