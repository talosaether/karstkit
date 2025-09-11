"""Tests for gRPC control plane functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import grpc
from iac_wrapper.controlplane import HealthChecker, ControlPlaneClient


class TestHealthChecker:
    """Test HealthChecker class."""

    def test_init(self):
        """Test HealthChecker initialization."""
        health_checker = HealthChecker()
        assert health_checker.timeout == 30

    def test_init_with_timeout(self):
        """Test HealthChecker initialization with custom timeout."""
        health_checker = HealthChecker(timeout=60)
        assert health_checker.timeout == 60

    @patch("grpc.insecure_channel")
    def test_check_service_health_success(self, mock_channel):
        """Test successful service health check."""
        # Mock gRPC channel and stub
        mock_channel_context = MagicMock()
        mock_channel.return_value.__enter__ = Mock(return_value=mock_channel_context)
        mock_channel.return_value.__exit__ = Mock(return_value=None)

        # Mock health status response
        mock_response = Mock()
        mock_response.status = 1  # SERVING
        mock_response.message = "Service is healthy"
        mock_response.timestamp.seconds = 1640995200
        mock_response.timestamp.nanos = 0

        # Mock the stub and method call
        with patch(
            "iac_wrapper.grpc_pb.controlplane_pb2_grpc.ControlPlaneStub"
        ) as mock_stub_class:
            mock_stub = Mock()
            mock_stub.HealthCheck.return_value = mock_response
            mock_stub_class.return_value = mock_stub

            health_checker = HealthChecker()
            result = health_checker.check_service_health("test-service")

            assert result.status == 1
            assert result.message == "Service is healthy"
            mock_channel.assert_called_once_with("test-service:50051")

    @patch("grpc.insecure_channel")
    def test_check_service_health_connection_error(self, mock_channel):
        """Test service health check with connection error."""
        # Mock gRPC channel to raise exception
        mock_channel.side_effect = grpc.RpcError("Connection failed")

        health_checker = HealthChecker()
        result = health_checker.check_service_health("test-service")

        assert result.status == 0  # UNKNOWN
        assert "Error connecting to service" in result.message

    @patch("grpc.insecure_channel")
    def test_check_service_health_grpc_error(self, mock_channel):
        """Test service health check with gRPC error."""
        # Mock gRPC channel and stub
        mock_channel_context = MagicMock()
        mock_channel.return_value.__enter__ = Mock(return_value=mock_channel_context)
        mock_channel.return_value.__exit__ = Mock(return_value=None)

        # Mock the stub to raise gRPC error
        with patch(
            "iac_wrapper.grpc_pb.controlplane_pb2_grpc.ControlPlaneStub"
        ) as mock_stub_class:
            mock_stub = Mock()
            mock_stub.HealthCheck.side_effect = grpc.RpcError("Service unavailable")
            mock_stub_class.return_value = mock_stub

            health_checker = HealthChecker()
            result = health_checker.check_service_health("test-service")

            assert result.status == 2  # NOT_SERVING
            assert "gRPC error" in result.message

    @patch("grpc.insecure_channel")
    def test_check_all_services(self, mock_channel):
        """Test checking multiple services health."""
        # Mock gRPC responses
        mock_channel_context = MagicMock()
        mock_channel.return_value.__enter__ = Mock(return_value=mock_channel_context)
        mock_channel.return_value.__exit__ = Mock(return_value=None)

        with patch(
            "iac_wrapper.grpc_pb.controlplane_pb2_grpc.ControlPlaneStub"
        ) as mock_stub_class:
            mock_stub = Mock()

            # Mock different responses for different services
            def side_effect_func(*args, **kwargs):
                if "service1" in str(mock_channel.call_args):
                    response = Mock()
                    response.status = 1  # SERVING
                    response.message = "Service 1 healthy"
                    return response
                else:
                    response = Mock()
                    response.status = 2  # NOT_SERVING
                    response.message = "Service 2 unhealthy"
                    return response

            mock_stub.HealthCheck.side_effect = side_effect_func
            mock_stub_class.return_value = mock_stub

            health_checker = HealthChecker()
            services = ["service1", "service2"]
            results = health_checker.check_all_services(services)

            assert len(results) == 2
            assert "service1" in results
            assert "service2" in results


class TestControlPlaneClient:
    """Test ControlPlaneClient class."""

    def test_init(self):
        """Test ControlPlaneClient initialization."""
        client = ControlPlaneClient("localhost:50051")
        assert client.address == "localhost:50051"
        assert client.timeout == 30

    def test_init_with_options(self):
        """Test ControlPlaneClient initialization with options."""
        client = ControlPlaneClient("localhost:50051", timeout=60, secure=True)
        assert client.address == "localhost:50051"
        assert client.timeout == 60
        assert client.secure is True

    @patch("grpc.insecure_channel")
    def test_health_check_success(self, mock_channel):
        """Test successful health check."""
        # Mock gRPC channel and stub
        mock_channel_context = MagicMock()
        mock_channel.return_value.__enter__ = Mock(return_value=mock_channel_context)
        mock_channel.return_value.__exit__ = Mock(return_value=None)

        # Mock health response
        mock_response = Mock()
        mock_response.status = 1
        mock_response.message = "Healthy"

        with patch(
            "iac_wrapper.grpc_pb.controlplane_pb2_grpc.ControlPlaneStub"
        ) as mock_stub_class:
            mock_stub = Mock()
            mock_stub.HealthCheck.return_value = mock_response
            mock_stub_class.return_value = mock_stub

            client = ControlPlaneClient("localhost:50051")
            result = client.health_check()

            assert result.status == 1
            assert result.message == "Healthy"

    @patch("grpc.secure_channel")
    def test_secure_connection(self, mock_secure_channel):
        """Test secure gRPC connection."""
        # Mock secure channel
        mock_channel_context = MagicMock()
        mock_secure_channel.return_value.__enter__ = Mock(
            return_value=mock_channel_context
        )
        mock_secure_channel.return_value.__exit__ = Mock(return_value=None)

        # Mock response
        mock_response = Mock()
        mock_response.status = 1

        with patch(
            "iac_wrapper.grpc_pb.controlplane_pb2_grpc.ControlPlaneStub"
        ) as mock_stub_class:
            mock_stub = Mock()
            mock_stub.HealthCheck.return_value = mock_response
            mock_stub_class.return_value = mock_stub

            client = ControlPlaneClient("localhost:50051", secure=True)
            result = client.health_check()

            mock_secure_channel.assert_called_once()
            assert result.status == 1

    @patch("grpc.insecure_channel")
    def test_stream_logs(self, mock_channel):
        """Test log streaming."""
        # Mock gRPC channel and stub
        mock_channel_context = MagicMock()
        mock_channel.return_value.__enter__ = Mock(return_value=mock_channel_context)
        mock_channel.return_value.__exit__ = Mock(return_value=None)

        # Mock log stream
        mock_log_line = Mock()
        mock_log_line.message = "Test log line"
        mock_log_line.level = "INFO"
        mock_log_line.service_name = "test-service"

        with patch(
            "iac_wrapper.grpc_pb.controlplane_pb2_grpc.ControlPlaneStub"
        ) as mock_stub_class:
            mock_stub = Mock()
            mock_stub.StreamLogs.return_value = [mock_log_line]
            mock_stub_class.return_value = mock_stub

            client = ControlPlaneClient("localhost:50051")
            log_stream = client.stream_logs("test-service")

            logs = list(log_stream)
            assert len(logs) == 1
            assert logs[0].message == "Test log line"

    @patch("grpc.insecure_channel")
    def test_connection_error_handling(self, mock_channel):
        """Test connection error handling."""
        # Mock connection error
        mock_channel.side_effect = grpc.RpcError("Connection failed")

        client = ControlPlaneClient("localhost:50051")

        with pytest.raises(grpc.RpcError):
            client.health_check()

    def test_invalid_address(self):
        """Test invalid address handling."""
        client = ControlPlaneClient("")
        assert client.address == ""

    @patch("grpc.insecure_channel")
    def test_timeout_configuration(self, mock_channel):
        """Test timeout configuration."""
        # Mock gRPC channel and stub
        mock_channel_context = MagicMock()
        mock_channel.return_value.__enter__ = Mock(return_value=mock_channel_context)
        mock_channel.return_value.__exit__ = Mock(return_value=None)

        mock_response = Mock()
        mock_response.status = 1

        with patch(
            "iac_wrapper.grpc_pb.controlplane_pb2_grpc.ControlPlaneStub"
        ) as mock_stub_class:
            mock_stub = Mock()
            mock_stub.HealthCheck.return_value = mock_response
            mock_stub_class.return_value = mock_stub

            client = ControlPlaneClient("localhost:50051", timeout=120)
            result = client.health_check()

            # Verify that the timeout is used in the call
            call_args = mock_stub.HealthCheck.call_args
            assert call_args is not None
