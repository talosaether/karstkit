"""Configuration management for the IAC wrapper."""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class with environment-based settings."""

    # Supabase Configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # OpenTelemetry Configuration
    OTEL_EXPORTER_OTLP_ENDPOINT: str = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
    )

    # Flask Admin API Configuration
    FLASK_HOST: str = os.getenv("FLASK_HOST", "127.0.0.1")
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "8080"))
    FLASK_SOCKET_PATH: str = os.getenv("FLASK_SOCKET_PATH", "/run/iac_wrapper.sock")

    # Docker Configuration
    DOCKER_NETWORK_NAME: str = os.getenv("DOCKER_NETWORK_NAME", "iacnet")
    DOCKER_REGISTRY: str = os.getenv("DOCKER_REGISTRY", "localhost:5000")

    # gRPC Configuration
    GRPC_PORT: int = int(os.getenv("GRPC_PORT", "50051"))
    ENVOY_INBOUND_PORT: int = int(os.getenv("ENVOY_INBOUND_PORT", "15000"))
    ENVOY_OUTBOUND_PORT: int = int(os.getenv("ENVOY_OUTBOUND_PORT", "15001"))
    ENVOY_METRICS_PORT: int = int(os.getenv("ENVOY_METRICS_PORT", "9901"))

    # Development Configuration
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    SECRETS_DIR: Path = BASE_DIR / "secrets"
    INFRA_DIR: Path = BASE_DIR / "infra"
    TEMPLATES_DIR: Path = INFRA_DIR / "templates"

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        required_vars = [
            ("SUPABASE_URL", cls.SUPABASE_URL),
            ("SUPABASE_SERVICE_ROLE_KEY", cls.SUPABASE_SERVICE_ROLE_KEY),
        ]

        missing = [name for name, value in required_vars if not value]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure required directories exist."""
        cls.SECRETS_DIR.mkdir(exist_ok=True)
        cls.INFRA_DIR.mkdir(exist_ok=True)
        cls.TEMPLATES_DIR.mkdir(exist_ok=True)

    @classmethod
    def get_ca_cert_path(cls) -> Path:
        """Get the CA certificate path."""
        return cls.SECRETS_DIR / "ca.pem"

    @classmethod
    def get_ca_key_path(cls) -> Path:
        """Get the CA private key path."""
        return cls.SECRETS_DIR / "ca.key"

    @classmethod
    def get_service_cert_path(cls, service_name: str) -> Path:
        """Get the service certificate path."""
        return cls.SECRETS_DIR / f"{service_name}.crt"

    @classmethod
    def get_service_key_path(cls, service_name: str) -> Path:
        """Get the service private key path."""
        return cls.SECRETS_DIR / f"{service_name}.key"


# Global configuration instance
config = Config()
