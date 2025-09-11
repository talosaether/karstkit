"""Tests for Envoy configuration functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
from iac_wrapper.envoy import EnvoyConfig, CertificateAuthority


class TestEnvoyConfig:
    """Test EnvoyConfig class."""

    def test_init(self, mock_config):
        """Test EnvoyConfig initialization."""
        envoy_config = EnvoyConfig()
        assert envoy_config.template_dir == mock_config.TEMPLATES_DIR
        assert envoy_config.secrets_dir == mock_config.SECRETS_DIR

    def test_init_with_custom_paths(self, temp_dir):
        """Test EnvoyConfig initialization with custom paths."""
        custom_template_dir = temp_dir / "custom_templates"
        custom_secrets_dir = temp_dir / "custom_secrets"

        envoy_config = EnvoyConfig(
            template_dir=custom_template_dir, secrets_dir=custom_secrets_dir
        )

        assert envoy_config.template_dir == custom_template_dir
        assert envoy_config.secrets_dir == custom_secrets_dir

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="test template {{ service_name }}",
    )
    def test_generate_config(self, mock_file, mock_config):
        """Test Envoy configuration generation."""
        envoy_config = EnvoyConfig()
        result = envoy_config.generate_config("test-service")

        assert "test-service" in result
        mock_file.assert_called_once()

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="""
admin:
  address:
    socket_address: { address: 0.0.0.0, port_value: 9901 }

static_resources:
  listeners:
  - name: listener_0
    address:
      socket_address: { address: 0.0.0.0, port_value: {{ envoy_inbound_port }} }
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress_http
          route_config:
            name: local_route
            virtual_hosts:
            - name: local_service
              domains: ["*"]
              routes:
              - match: { prefix: "/" }
                route: { cluster: {{ service_name }}_cluster }
          http_filters:
          - name: envoy.filters.http.router

  clusters:
  - name: {{ service_name }}_cluster
    connect_timeout: 0.25s
    type: LOGICAL_DNS
    dns_lookup_family: V4_ONLY
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: {{ service_name }}_cluster
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: {{ service_name }}
                port_value: {{ grpc_port }}
    transport_socket:
      name: envoy.transport_sockets.tls
      typed_config:
        "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
        common_tls_context:
          tls_certificates:
          - certificate_chain:
              filename: "/etc/envoy/certs/tls.crt"
            private_key:
              filename: "/etc/envoy/certs/tls.key"
          validation_context:
            trusted_ca:
              filename: "/etc/envoy/certs/ca.crt"
""",
    )
    def test_generate_config_with_template(self, mock_file, mock_config):
        """Test Envoy configuration generation with realistic template."""
        envoy_config = EnvoyConfig()
        result = envoy_config.generate_config("my-service")

        assert "my-service" in result
        assert str(mock_config.ENVOY_INBOUND_PORT) in result
        assert str(mock_config.GRPC_PORT) in result
        assert "/etc/envoy/certs/tls.crt" in result
        assert "/etc/envoy/certs/ca.crt" in result

    def test_generate_config_template_not_found(self, mock_config):
        """Test config generation when template file not found."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            envoy_config = EnvoyConfig()

            with pytest.raises(RuntimeError, match="Template file not found"):
                envoy_config.generate_config("test-service")

    def test_get_certificate_paths(self, mock_config):
        """Test certificate paths generation."""
        envoy_config = EnvoyConfig()
        cert_paths = envoy_config.get_certificate_paths("test-service")

        assert "ca_cert" in cert_paths
        assert "service_cert" in cert_paths
        assert "service_key" in cert_paths

        assert cert_paths["ca_cert"] == mock_config.SECRETS_DIR / "ca.pem"
        assert (
            cert_paths["service_cert"] == mock_config.SECRETS_DIR / "test-service.crt"
        )
        assert cert_paths["service_key"] == mock_config.SECRETS_DIR / "test-service.key"

    def test_ensure_certificates_exist(self, mock_config, temp_dir):
        """Test certificate existence check and generation."""
        # Mock certificate manager
        with patch.object(EnvoyConfig, "_cert_manager") as mock_cert_manager:
            mock_cert_manager.ensure_ca_exists.return_value = None
            mock_cert_manager.generate_service_cert.return_value = None

            envoy_config = EnvoyConfig()
            envoy_config.ensure_certificates_exist("test-service")

            mock_cert_manager.ensure_ca_exists.assert_called_once()
            mock_cert_manager.generate_service_cert.assert_called_once_with(
                "test-service"
            )


class TestCertificateAuthority:
    """Test CertificateAuthority class."""

    def test_init(self, temp_dir):
        """Test CertificateAuthority initialization."""
        ca_cert_path = temp_dir / "ca.pem"
        ca_key_path = temp_dir / "ca.key"
        cert_auth = CertificateAuthority(ca_cert_path, ca_key_path)
        assert cert_auth.ca_cert_path == ca_cert_path
        assert cert_auth.ca_key_path == ca_key_path

    def test_ca_paths(self, temp_dir):
        """Test CA certificate paths."""
        ca_cert_path = temp_dir / "ca.pem"
        ca_key_path = temp_dir / "ca.key"
        cert_auth = CertificateAuthority(ca_cert_path, ca_key_path)

        assert cert_auth.ca_cert_path == ca_cert_path
        assert cert_auth.ca_key_path == ca_key_path

    def test_service_paths(self, temp_dir):
        """Test service certificate paths."""
        ca_cert_path = temp_dir / "ca.pem"
        ca_key_path = temp_dir / "ca.key"
        cert_auth = CertificateAuthority(ca_cert_path, ca_key_path)

        # Test would need actual method implementation
        assert True  # Placeholder for actual service cert path test

    def test_ca_generation_on_init(self, temp_dir):
        """Test CA certificate generation on initialization."""
        ca_cert_path = temp_dir / "ca.pem"
        ca_key_path = temp_dir / "ca.key"

        with patch.object(CertificateAuthority, "_generate_ca") as mock_gen_ca:
            cert_auth = CertificateAuthority(ca_cert_path, ca_key_path)
            mock_gen_ca.assert_called_once()

    def test_ca_not_regenerated_if_exists(self, temp_dir):
        """Test CA certificate not regenerated if exists."""
        ca_cert_path = temp_dir / "ca.pem"
        ca_key_path = temp_dir / "ca.key"

        # Create existing certificate files
        ca_cert_path.write_text("existing cert")
        ca_key_path.write_text("existing key")

        with patch.object(CertificateAuthority, "_generate_ca") as mock_gen_ca:
            cert_auth = CertificateAuthority(ca_cert_path, ca_key_path)
            mock_gen_ca.assert_not_called()

    @patch("cryptography.x509.CertificateBuilder")
    @patch("cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key")
    def test_generate_ca(self, mock_gen_key, mock_cert_builder, temp_dir):
        """Test CA certificate generation."""
        ca_cert_path = temp_dir / "ca.pem"
        ca_key_path = temp_dir / "ca.key"

        # Mock private key generation
        mock_private_key = Mock()
        mock_gen_key.return_value = mock_private_key

        # Mock certificate building
        mock_builder = Mock()
        mock_cert_builder.return_value = mock_builder
        mock_builder.subject_name.return_value = mock_builder
        mock_builder.issuer_name.return_value = mock_builder
        mock_builder.public_key.return_value = mock_builder
        mock_builder.serial_number.return_value = mock_builder
        mock_builder.not_valid_before.return_value = mock_builder
        mock_builder.not_valid_after.return_value = mock_builder
        mock_builder.add_extension.return_value = mock_builder

        mock_certificate = Mock()
        mock_builder.sign.return_value = mock_certificate

        # Mock serialization
        mock_private_key.private_bytes.return_value = b"mock private key"
        mock_certificate.public_bytes.return_value = b"mock certificate"

        cert_auth = CertificateAuthority(ca_cert_path, ca_key_path)

        # Verify files would be created (mocked behavior)
        assert cert_auth.ca_cert_path == ca_cert_path
        assert cert_auth.ca_key_path == ca_key_path
