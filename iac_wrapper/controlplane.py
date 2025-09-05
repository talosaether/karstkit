"""gRPC control plane client for communicating with services."""

import ssl
import grpc
from typing import Iterator, Optional
from datetime import datetime
from .config import config
from .envoy import EnvoyConfig

# Import generated protobuf modules
try:
    from .grpc_pb import controlplane_pb2 as pb2
    from .grpc_pb import controlplane_pb2_grpc as pb2_grpc
except ImportError:
    # Fallback for when protobufs haven't been generated yet
    pb2 = None
    pb2_grpc = None


class ControlPlaneClient:
    """gRPC client for communicating with services."""

    def __init__(self, service_name: str, use_mtls: bool = True):
        self.service_name = service_name
        self.use_mtls = use_mtls
        self.envoy_config = EnvoyConfig()

        if pb2 is None or pb2_grpc is None:
            raise ImportError("Protobuf modules not available. Run 'make proto' first.")

    def _create_channel(self) -> grpc.Channel:
        """Create a gRPC channel with mTLS if enabled."""
        if self.use_mtls:
            # Get certificate paths
            cert_paths = self.envoy_config.get_certificate_paths(self.service_name)

            # Load certificates
            with open(cert_paths["service_cert"], "rb") as f:
                cert_data = f.read()

            with open(cert_paths["service_key"], "rb") as f:
                key_data = f.read()

            with open(cert_paths["ca_cert"], "rb") as f:
                ca_data = f.read()

            # Create credentials
            credentials = grpc.ssl_channel_credentials(
                root_certificates=ca_data,
                private_key=key_data,
                certificate_chain=cert_data,
            )

            # Create channel with mTLS
            return grpc.secure_channel(
                f"{self.service_name}:{config.ENVOY_INBOUND_PORT}", credentials
            )
        else:
            # Create insecure channel
            return grpc.insecure_channel(f"{self.service_name}:{config.GRPC_PORT}")

    def health_check(self):
        """Perform a health check on the service.

        Returns:
            Health status response
        """
        with self._create_channel() as channel:
            stub = pb2_grpc.ControlPlaneStub(channel)
            try:
                from google.protobuf import empty_pb2

                response = stub.HealthCheck(empty_pb2.Empty())
                return response
            except grpc.RpcError as e:
                # Create a failed health status
                from google.protobuf import timestamp_pb2

                timestamp = timestamp_pb2.Timestamp()
                timestamp.GetCurrentTime()

                return pb2.HealthStatus(
                    status=pb2.HealthStatus.NOT_SERVING,
                    message=f"gRPC error: {e.details()}",
                    timestamp=timestamp,
                )

    def stream_logs(self, follow: bool = False, tail_lines: int = 100):
        """Stream logs from the service.

        Args:
            follow: Whether to follow the logs
            tail_lines: Number of lines to tail

        Yields:
            Log line messages
        """
        with self._create_channel() as channel:
            stub = pb2_grpc.ControlPlaneStub(channel)
            request = pb2.LogRequest(
                service_name=self.service_name, follow=follow, tail_lines=tail_lines
            )

            try:
                for log_line in stub.StreamLogs(request):
                    yield log_line
            except grpc.RpcError as e:
                # Yield an error log line
                from google.protobuf import timestamp_pb2

                timestamp = timestamp_pb2.Timestamp()
                timestamp.GetCurrentTime()

                yield pb2.LogLine(
                    timestamp=timestamp,
                    message=f"Error streaming logs: {e.details()}",
                    level="ERROR",
                    service_name=self.service_name,
                )

    def deploy(
        self, slugs: list[str], wait_for_ready: bool = True, timeout_seconds: int = 300
    ):
        """Deploy services.

        Args:
            slugs: List of repository slugs
            wait_for_ready: Whether to wait for services to be ready
            timeout_seconds: Timeout in seconds

        Returns:
            Deploy result
        """
        with self._create_channel() as channel:
            stub = pb2_grpc.ControlPlaneStub(channel)
            request = pb2.DeployRequest(
                slugs=slugs,
                wait_for_ready=wait_for_ready,
                timeout_seconds=timeout_seconds,
            )

            try:
                response = stub.Deploy(request)
                return response
            except grpc.RpcError as e:
                # Create a failed deploy result
                return pb2.DeployResult(
                    success=False,
                    error_message=f"gRPC error: {e.details()}",
                    services=[],
                )


class HealthChecker:
    """Health checker for multiple services."""

    def __init__(self):
        self.clients = {}

    def check_service_health(self, service_name: str, use_mtls: bool = True):
        """Check health of a specific service.

        Args:
            service_name: Name of the service
            use_mtls: Whether to use mTLS

        Returns:
            Health status
        """
        if service_name not in self.clients:
            self.clients[service_name] = ControlPlaneClient(service_name, use_mtls)

        return self.clients[service_name].health_check()

    def check_all_services(self, service_names: list[str], use_mtls: bool = True):
        """Check health of multiple services.

        Args:
            service_names: List of service names
            use_mtls: Whether to use mTLS

        Returns:
            Dictionary mapping service names to health statuses
        """
        results = {}
        for service_name in service_names:
            try:
                results[service_name] = self.check_service_health(
                    service_name, use_mtls
                )
            except Exception as e:
                # Create error health status
                from google.protobuf import timestamp_pb2

                timestamp = timestamp_pb2.Timestamp()
                timestamp.GetCurrentTime()

                results[service_name] = pb2.HealthStatus(
                    status=pb2.HealthStatus.SERVICE_UNKNOWN,
                    message=f"Error checking health: {str(e)}",
                    timestamp=timestamp,
                )

        return results
