"""Docker operations for building and managing containers."""

import os
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
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

        try:
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
                raise RuntimeError(f"Envoy container run failed: {result.stderr}")

            return result.stdout.strip()

        finally:
            # Clean up temporary config file
            os.unlink(config_path)

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
