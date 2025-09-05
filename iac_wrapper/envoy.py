"""Envoy sidecar configuration and certificate management."""

import os
import ssl
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jinja2 import Template
from .config import config


class CertificateAuthority:
    """Certificate Authority for mTLS certificates."""

    def __init__(self, ca_cert_path: Path, ca_key_path: Path):
        self.ca_cert_path = ca_cert_path
        self.ca_key_path = ca_key_path
        self._ensure_ca_exists()

    def _ensure_ca_exists(self) -> None:
        """Ensure CA certificate and key exist, create if they don't."""
        if not self.ca_cert_path.exists() or not self.ca_key_path.exists():
            self._generate_ca()

    def _generate_ca(self) -> None:
        """Generate a new CA certificate and private key."""
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Create certificate
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IAC Wrapper CA"),
                x509.NameAttribute(NameOID.COMMON_NAME, "iac-wrapper-ca"),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=3650))  # 10 years
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_encipherment=True,
                    key_agreement=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    digital_signature=True,
                    content_commitment=False,
                    data_encipherment=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Save CA certificate and key
        self.ca_cert_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.ca_cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        with open(self.ca_key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

    def generate_service_certificate(self, service_name: str) -> tuple[Path, Path]:
        """Generate a certificate for a service.

        Args:
            service_name: Name of the service

        Returns:
            Tuple of (cert_path, key_path)
        """
        # Load CA certificate and key
        with open(self.ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())

        with open(self.ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)

        # Generate service private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Create certificate
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IAC Wrapper Services"),
                x509.NameAttribute(NameOID.COMMON_NAME, service_name),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=365))  # 1 year
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    key_encipherment=True,
                    key_agreement=True,
                    key_cert_sign=False,
                    crl_sign=False,
                    digital_signature=True,
                    content_commitment=False,
                    data_encipherment=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName(service_name),
                        x509.DNSName(f"{service_name}.{config.DOCKER_NETWORK_NAME}"),
                    ]
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )

        # Save service certificate and key
        cert_path = config.get_service_cert_path(service_name)
        key_path = config.get_service_key_path(service_name)

        cert_path.parent.mkdir(parents=True, exist_ok=True)

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        with open(key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        return cert_path, key_path


class EnvoyConfig:
    """Envoy configuration generator."""

    def __init__(self):
        self.ca = CertificateAuthority(
            config.get_ca_cert_path(), config.get_ca_key_path()
        )

    def generate_config(self, service_name: str, **kwargs) -> str:
        """Generate Envoy configuration for a service.

        Args:
            service_name: Name of the service
            **kwargs: Additional configuration parameters

        Returns:
            Envoy configuration as string
        """
        # Ensure service certificate exists
        self.ca.generate_service_certificate(service_name)

        # Load template
        template_path = config.TEMPLATES_DIR / "envoy.yaml.tmpl"
        with open(template_path, "r") as f:
            template = Template(f.read())

        # Prepare context
        context = {
            "service_name": service_name,
            "grpc_port": config.GRPC_PORT,
            "envoy_inbound_port": config.ENVOY_INBOUND_PORT,
            "envoy_outbound_port": config.ENVOY_OUTBOUND_PORT,
            "envoy_metrics_port": config.ENVOY_METRICS_PORT,
            **kwargs,
        }

        return template.render(**context)

    def get_certificate_paths(self, service_name: str) -> Dict[str, Path]:
        """Get certificate paths for a service.

        Args:
            service_name: Name of the service

        Returns:
            Dictionary with certificate paths
        """
        return {
            "ca_cert": config.get_ca_cert_path(),
            "service_cert": config.get_service_cert_path(service_name),
            "service_key": config.get_service_key_path(service_name),
        }
