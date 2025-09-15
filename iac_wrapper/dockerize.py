"""Docker operations for building and managing containers."""

import os
import tempfile
import subprocess
import time
import requests
from pathlib import Path
from typing import Optional, Tuple, List
from jinja2 import Template
from .config import config
from .slug import RepoSlug


class DockerOps:
    """Docker operations handler."""

    def __init__(self):
        self.template_dir = config.TEMPLATES_DIR

    def build_image(
        self, repo_path: Path, slug: RepoSlug, entrypoint: Optional[str] = None
    ) -> str:
        """Build a Docker image for a repository.

        Args:
            repo_path: Path to the repository
            slug: Repository slug
            entrypoint: Optional entrypoint override

        Returns:
            Image name/tag
        """
        # Generate Dockerfile
        dockerfile_content = self._generate_dockerfile(slug, entrypoint)

        # Create temporary Dockerfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".Dockerfile", delete=False
        ) as f:
            f.write(dockerfile_content)
            dockerfile_path = f.name

        try:
            # Build the image
            image_name = f"iac-{slug.service_name}:latest"
            cmd = [
                "docker",
                "build",
                "-f",
                dockerfile_path,
                "-t",
                image_name,
                str(repo_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Docker build failed: {result.stderr}")

            return image_name

        finally:
            # Clean up temporary file
            os.unlink(dockerfile_path)

    def _generate_dockerfile(
        self, slug: RepoSlug, entrypoint: Optional[str] = None
    ) -> str:
        """Generate Dockerfile content.

        Args:
            slug: Repository slug
            entrypoint: Optional entrypoint override

        Returns:
            Dockerfile content as string
        """
        # Load template
        template_path = self.template_dir / "app.Dockerfile.tmpl"
        with open(template_path, "r") as f:
            template = Template(f.read())

        # Prepare context
        context = {
            "grpc_port": config.GRPC_PORT,
            "entrypoint": entrypoint or "main.main()",
        }

        return template.render(**context)

    def run_container(self, image_name: str, service_name: str, **kwargs) -> str:
        """Run a Docker container.

        Args:
            image_name: Name of the image to run
            service_name: Name of the service
            **kwargs: Additional container options

        Returns:
            Container ID
        """
        cmd = [
            "docker",
            "run",
            "-d",  # Detached mode
            "--name",
            service_name,
            "--network",
            config.DOCKER_NETWORK_NAME,
            "--restart",
            "unless-stopped",
        ]

        # Add environment variables
        for key, value in kwargs.get("environment", {}).items():
            cmd.extend(["-e", f"{key}={value}"])

        # Add volume mounts
        for volume in kwargs.get("volumes", []):
            cmd.extend(["-v", volume])

        # Add port mappings
        for port_mapping in kwargs.get("ports", []):
            cmd.extend(["-p", port_mapping])

        # Add the image name
        cmd.append(image_name)

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Docker run failed: {result.stderr}")

        return result.stdout.strip()

    def run_envoy_sidecar(self, service_name: str, envoy_config: str) -> str:
        """Run an Envoy sidecar container.

        Args:
            service_name: Name of the service
            envoy_config: Envoy configuration content

        Returns:
            Container ID
        """
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(envoy_config)
            config_path = f.name

        # Make config file readable by container (Docker may run as different user)
        os.chmod(config_path, 0o644)

        # Get certificate paths
        from .envoy import EnvoyConfig

        envoy_ops = EnvoyConfig()
        cert_paths = envoy_ops.get_certificate_paths(service_name)

        # Run Envoy container
        cmd = [
            "docker",
            "run",
            "-d",  # Detached mode
            "--name",
            f"{service_name}-envoy",
            "--network",
            config.DOCKER_NETWORK_NAME,
            "--restart",
            "unless-stopped",
            "-v",
            f"{config_path}:/etc/envoy/envoy.yaml:ro",
            "-v",
            f"{cert_paths['ca_cert']}:/etc/envoy/certs/ca.crt:ro",
            "-v",
            f"{cert_paths['service_cert']}:/etc/envoy/certs/tls.crt:ro",
            "-v",
            f"{cert_paths['service_key']}:/etc/envoy/certs/tls.key:ro",
            "-p",
            f"{config.ENVOY_INBOUND_PORT}:{config.ENVOY_INBOUND_PORT}",
            "-p",
            f"{config.ENVOY_METRICS_PORT}:{config.ENVOY_METRICS_PORT}",
            "envoyproxy/envoy:v1.28-latest",
            "/usr/local/bin/envoy",
            "-c",
            "/etc/envoy/envoy.yaml",
            "--service-cluster",
            service_name,
            "--service-node",
            f"{service_name}-node",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Clean up config file on failure
            try:
                os.unlink(config_path)
            except OSError:
                pass
            raise RuntimeError(f"Envoy container run failed: {result.stderr}")

        # Store config path for later cleanup
        container_id = result.stdout.strip()
        if not hasattr(self, "_envoy_config_files"):
            self._envoy_config_files = {}
        self._envoy_config_files[f"{service_name}-envoy"] = config_path

        return container_id

    def stop_container(self, container_name: str) -> None:
        """Stop a Docker container.

        Args:
            container_name: Name of the container to stop
        """
        cmd = ["docker", "stop", container_name]
        subprocess.run(cmd, capture_output=True, text=True)

    def remove_container(self, container_name: str) -> None:
        """Remove a Docker container.

        Args:
            container_name: Name of the container to remove
        """
        cmd = ["docker", "rm", container_name]
        subprocess.run(cmd, capture_output=True, text=True)

        # Clean up temporary config file if this is an Envoy container
        if (
            hasattr(self, "_envoy_config_files")
            and container_name in self._envoy_config_files
        ):
            try:
                os.unlink(self._envoy_config_files[container_name])
            except OSError:
                pass
            del self._envoy_config_files[container_name]

    def get_container_logs(self, container_name: str, tail: int = 100) -> str:
        """Get container logs.

        Args:
            container_name: Name of the container
            tail: Number of lines to return

        Returns:
            Container logs
        """
        cmd = ["docker", "logs", "--tail", str(tail), container_name]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return f"Error getting logs: {result.stderr}"
        return result.stdout

    def container_exists(self, container_name: str) -> bool:
        """Check if a container exists.

        Args:
            container_name: Name of the container

        Returns:
            True if container exists, False otherwise
        """
        cmd = [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"name={container_name}",
            "--format",
            "{{.Names}}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return container_name in result.stdout.strip().split("\n")

    def container_running(self, container_name: str) -> bool:
        """Check if a container is running.

        Args:
            container_name: Name of the container

        Returns:
            True if container is running, False otherwise
        """
        cmd = [
            "docker",
            "ps",
            "--filter",
            f"name={container_name}",
            "--format",
            "{{.Names}}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return container_name in result.stdout.strip().split("\n")

    def wait_for_envoy_ready(self, service_name: str, timeout: int = 30) -> bool:
        """Wait for Envoy sidecar to be ready.

        Args:
            service_name: Name of the service
            timeout: Timeout in seconds

        Returns:
            True if Envoy is ready, False if timeout
        """
        envoy_container_name = f"{service_name}-envoy"
        start_time = time.time()

        while time.time() - start_time < timeout:
            # First check if container is running
            if not self.container_running(envoy_container_name):
                time.sleep(1)
                continue

            # Check Envoy admin endpoint for readiness
            try:
                # Get container IP address
                cmd = [
                    "docker",
                    "inspect",
                    "-f",
                    "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                    envoy_container_name,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    time.sleep(1)
                    continue

                container_ip = result.stdout.strip()
                if not container_ip:
                    time.sleep(1)
                    continue

                # Check readiness via admin endpoint
                response = requests.get(
                    f"http://{container_ip}:{config.ENVOY_METRICS_PORT}/ready",
                    timeout=2,
                )
                if response.status_code == 200:
                    return True

            except (requests.exceptions.RequestException, Exception):
                pass

            time.sleep(1)

        return False

    def start_service_with_envoy(
        self, image_name: str, service_name: str, envoy_config: str, **kwargs
    ) -> Tuple[str, str]:
        """Start a service with its Envoy sidecar in the correct order.

        Args:
            image_name: Docker image name for the service
            service_name: Name of the service
            envoy_config: Envoy configuration content
            **kwargs: Additional container options

        Returns:
            Tuple of (app_container_id, envoy_container_id)

        Raises:
            RuntimeError: If Envoy fails to start or become ready
        """
        # Clean up any existing containers
        if self.container_exists(service_name):
            self.stop_container(service_name)
            self.remove_container(service_name)

        if self.container_exists(f"{service_name}-envoy"):
            self.stop_container(f"{service_name}-envoy")
            self.remove_container(f"{service_name}-envoy")

        # Step 1: Start Envoy sidecar first
        envoy_container_id = self.run_envoy_sidecar(service_name, envoy_config)

        # Step 2: Wait for Envoy to be ready
        if not self.wait_for_envoy_ready(service_name):
            # Clean up failed Envoy container
            self.stop_container(f"{service_name}-envoy")
            self.remove_container(f"{service_name}-envoy")
            raise RuntimeError(
                f"Envoy sidecar for {service_name} failed to become ready"
            )

        try:
            # Step 3: Start the application container
            app_container_id = self.run_container(image_name, service_name, **kwargs)
            return app_container_id, envoy_container_id

        except Exception as e:
            # If app container fails to start, clean up Envoy
            self.stop_container(f"{service_name}-envoy")
            self.remove_container(f"{service_name}-envoy")
            raise e

    def get_container_ip(self, container_name: str) -> Optional[str]:
        """Get the IP address of a container.

        Args:
            container_name: Name of the container

        Returns:
            IP address of the container, or None if not found
        """
        try:
            cmd = [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                container_name,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                ip = result.stdout.strip()
                return ip if ip else None
            return None
        except Exception:
            return None

    def detect_service_port(self, repo_path: Path, entrypoint: str) -> Optional[int]:
        """Detect the web port used by a service by analyzing code patterns.

        Args:
            repo_path: Path to the repository
            entrypoint: Service entrypoint command

        Returns:
            Detected port number or None if not found
        """

        # First try to detect from entrypoint patterns
        if "port" in entrypoint.lower():
            import re

            port_match = re.search(r"port[=:\s]+(\d+)", entrypoint.lower())
            if port_match:
                port = int(port_match.group(1))
                if 1000 <= port <= 65535:
                    return port

        # Search for common port patterns in Python files
        for py_file in repo_path.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")

                # Look for Flask app.run patterns
                import re

                flask_patterns = [
                    r"app\.run\([^)]*port\s*=\s*(\d+)",
                    r'host\s*=\s*["\'][^"\']*["\']\s*,\s*port\s*=\s*(\d+)',
                    r"port\s*=\s*(\d+)[^}]*\)",
                ]

                for pattern in flask_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        port = int(match)
                        if 1000 <= port <= 65535:
                            return port

                # Look for PORT environment variable usage
                env_patterns = [
                    r'os\.environ\.get\(["\']PORT["\']\s*,\s*["\']?(\d+)',
                    r'os\.getenv\(["\']PORT["\']\s*,\s*["\']?(\d+)',
                ]

                for pattern in env_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        port = int(match)
                        if 1000 <= port <= 65535:
                            return port

            except Exception:
                continue

        # If no specific port found, check if it's a common framework
        if any(framework in entrypoint.lower() for framework in ["flask", "django"]):
            return 5000  # Default Flask port
        elif any(
            framework in entrypoint.lower() for framework in ["node", "npm", "yarn"]
        ):
            return 3000  # Default Node.js port

        return None

    def generate_port_mappings(
        self, repo_path: Path, entrypoint: str, service_name: str
    ) -> List[str]:
        """Generate port mappings for a service.

        Args:
            repo_path: Path to the repository
            entrypoint: Service entrypoint command
            service_name: Name of the service

        Returns:
            List of port mapping strings in format "host_port:container_port"
        """
        port_mappings = []

        # Detect the service's primary port
        detected_port = self.detect_service_port(repo_path, entrypoint)

        if detected_port:
            # Map to the same port on host if available, or find next available
            host_port = self._find_available_host_port(detected_port)
            port_mappings.append(f"{host_port}:{detected_port}")

        # Always expose common ports if they're different from detected port
        common_web_ports = [5000, 8000, 8080, 3000, 4000, 9000]
        for port in common_web_ports:
            if port != detected_port:
                # Only map if this port seems to be used by the service
                if self._port_likely_used(repo_path, port):
                    host_port = self._find_available_host_port(port)
                    port_mappings.append(f"{host_port}:{port}")

        return port_mappings

    def _find_available_host_port(self, preferred_port: int) -> int:
        """Find an available port on the host, starting with the preferred port.

        Args:
            preferred_port: The preferred port to use

        Returns:
            Available port number
        """
        import socket

        # Try the preferred port first
        if self._is_port_available(preferred_port):
            return preferred_port

        # Try ports in a range around the preferred port
        for offset in range(1, 100):
            for port in [preferred_port + offset, preferred_port - offset]:
                if 1024 <= port <= 65535 and self._is_port_available(port):
                    return port

        # Fallback to a high port range
        for port in range(8000, 9000):
            if self._is_port_available(port):
                return port

        return preferred_port  # Fallback

    def _is_port_available(self, port: int) -> bool:
        """Check if a port is available on the host.

        Args:
            port: Port number to check

        Returns:
            True if port is available, False otherwise
        """
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", port))
                return True
        except OSError:
            return False

    def _port_likely_used(self, repo_path: Path, port: int) -> bool:
        """Check if a port is likely used by the service.

        Args:
            repo_path: Path to the repository
            port: Port number to check

        Returns:
            True if port is likely used
        """
        # Simple heuristic: search for the port number in Python files
        for py_file in repo_path.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if str(port) in content:
                    return True
            except Exception:
                continue
        return False
