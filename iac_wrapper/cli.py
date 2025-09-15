"""Command-line interface for the IAC wrapper."""

import json
import subprocess
import sys
import yaml
from typing import Optional
import click
from .config import config
from .slug import parse_slug, validate_slug
from .gitops import GitOps
from .dockerize import DockerOps
from .envoy import EnvoyConfig
from .controlplane import HealthChecker


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Infrastructure-as-Code deployment wrapper for containerized runtimes."""
    pass


@main.command()
@click.option(
    "--file",
    "-f",
    "file_path",
    type=click.Path(exists=True),
    help="Path to YAML/JSON file with slugs",
)
@click.option(
    "--slug", "-s", "slugs", multiple=True, help="Repository slug(s) to deploy"
)
@click.option(
    "--wait", "-w", is_flag=True, default=True, help="Wait for services to be ready"
)
@click.option("--timeout", "-t", default=300, help="Timeout in seconds for deployment")
def deploy(file_path: Optional[str], slugs: tuple, wait: bool, timeout: int):
    """Deploy services from repository slugs."""
    try:
        # Parse slugs
        slug_list = []

        if file_path:
            with open(file_path, "r") as f:
                if file_path.endswith(".yaml") or file_path.endswith(".yml"):
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)

                if isinstance(data, list):
                    slug_list.extend(data)
                elif isinstance(data, dict) and "slugs" in data:
                    slug_list.extend(data["slugs"])
                else:
                    click.echo(f"Error: Invalid file format in {file_path}", err=True)
                    sys.exit(1)

        if slugs:
            slug_list.extend(slugs)

        if not slug_list:
            click.echo(
                "Error: No slugs provided. Use --file or --slug options.", err=True
            )
            sys.exit(1)

        # Validate slugs
        for slug_str in slug_list:
            if not validate_slug(slug_str):
                click.echo(f"Error: Invalid slug format: {slug_str}", err=True)
                sys.exit(1)

        click.echo(f"Deploying {len(slug_list)} service(s)...")

        # Initialize components
        git_ops = GitOps()
        docker_ops = DockerOps()
        envoy_config = EnvoyConfig()
        health_checker = HealthChecker()

        results = []

        for i, slug_str in enumerate(slug_list, 1):
            click.echo(f"[{i}/{len(slug_list)}] Processing {slug_str}...")

            try:
                # Parse slug
                slug = parse_slug(slug_str)
                service_name = slug.service_name

                click.echo(f"  Fetching repository...")
                repo_path = git_ops.fetch_repo(slug)

                click.echo(f"  Detecting entrypoint...")
                entrypoint = git_ops.detect_entrypoint(repo_path)

                if not entrypoint:
                    click.echo(f"  Error: No entrypoint detected", err=True)
                    results.append(
                        {
                            "slug": slug_str,
                            "service_name": service_name,
                            "deployed": False,
                            "error": "No entrypoint detected",
                        }
                    )
                    continue

                click.echo(f"  Building Docker image...")
                image_name = docker_ops.build_image(repo_path, slug, entrypoint)

                click.echo(f"  Configuring Envoy...")
                envoy_config_content = envoy_config.generate_config(service_name)

                click.echo(f"  Starting containers (Envoy first, then app)...")

                # Start service with Envoy in correct order (Envoy first, then app)
                try:
                    (
                        container_id,
                        envoy_container_id,
                    ) = docker_ops.start_service_with_envoy(
                        image_name,
                        service_name,
                        envoy_config_content,
                        environment={
                            "OTEL_EXPORTER_OTLP_ENDPOINT": (
                                config.OTEL_EXPORTER_OTLP_ENDPOINT
                            ),
                            "GRPC_PORT": str(config.GRPC_PORT),
                        },
                    )
                    click.echo(f"  ✅ Service {service_name} started successfully")
                except RuntimeError as e:
                    click.echo(f"  ❌ Failed to start {service_name}: {e}", err=True)
                    continue

                # Check health if requested
                health_status = None
                if wait:
                    click.echo(f"  Checking health...")
                    try:
                        health_status = health_checker.check_service_health(
                            service_name
                        )
                        if health_status.status == 1:  # SERVING
                            click.echo(f"  ✓ Service is healthy")
                        else:
                            click.echo(f"  ⚠ Service health: {health_status.message}")
                    except Exception as e:
                        click.echo(f"  ⚠ Health check failed: {e}")
                        health_status = {
                            "status": "UNKNOWN",
                            "message": f"Health check failed: {str(e)}",
                        }

                click.echo(f"  ✓ Deployed successfully")

                # Get container IP addresses
                app_ip = docker_ops.get_container_ip(service_name)
                envoy_ip = docker_ops.get_container_ip(f"{service_name}-envoy")

                results.append(
                    {
                        "slug": slug_str,
                        "service_name": service_name,
                        "deployed": True,
                        "image_name": image_name,
                        "container_id": container_id,
                        "envoy_container_id": envoy_container_id,
                        "health_status": health_status,
                        "app_ip": app_ip,
                        "envoy_ip": envoy_ip,
                    }
                )

            except Exception as e:
                click.echo(f"  Error: {e}", err=True)
                results.append(
                    {
                        "slug": slug_str,
                        "service_name": (
                            slug_str.split(":")[1].split("/")[1]
                            if ":" in slug_str
                            else slug_str
                        ),
                        "deployed": False,
                        "error": str(e),
                    }
                )

        # Summary
        click.echo("\nDeployment Summary:")
        successful = sum(1 for r in results if r.get("deployed", False))
        click.echo(f"  Successful: {successful}/{len(results)}")
        click.echo(f"  Network: {config.DOCKER_NETWORK_NAME} (172.20.0.0/16)")

        for result in results:
            status = "✓" if result.get("deployed", False) else "✗"
            click.echo(f"  {status} {result['slug']}")
            if result.get("deployed", False):
                # Show IP addresses for successful deployments
                if result.get("app_ip"):
                    click.echo(f"    App IP: {result['app_ip']}")
                if result.get("envoy_ip"):
                    click.echo(f"    Envoy IP: {result['envoy_ip']}")
            else:
                click.echo(f"    Error: {result.get('error', 'Unknown error')}")

        if successful < len(results):
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def plan():
    """Show Terraform plan."""
    try:
        click.echo("Running Terraform plan...")
        result = subprocess.run(
            ["terraform", "plan"], cwd="infra", capture_output=True, text=True
        )

        if result.returncode == 0:
            click.echo(result.stdout)
        else:
            click.echo(f"Error: {result.stderr}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def apply():
    """Apply Terraform configuration."""
    try:
        click.echo("Applying Terraform configuration...")
        result = subprocess.run(
            ["terraform", "apply", "-auto-approve"],
            cwd="infra",
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            click.echo("✓ Terraform applied successfully")
            click.echo(result.stdout)
        else:
            click.echo(f"Error: {result.stderr}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def destroy():
    """Destroy all deployed resources."""
    try:
        if not click.confirm(
            "Are you sure you want to destroy all deployed resources?"
        ):
            return

        click.echo("Destroying all resources...")

        # Stop and remove containers
        docker_ops = DockerOps()
        cmd = ["docker", "ps", "-a", "--filter", "name=iac-", "--format", "{{.Names}}"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            container_names = result.stdout.strip().split("\n")
            for name in container_names:
                if name:
                    try:
                        docker_ops.stop_container(name)
                        docker_ops.remove_container(name)
                        click.echo(f"  Removed container: {name}")
                    except Exception as e:
                        click.echo(f"  Warning: Failed to remove {name}: {e}")

        # Run Terraform destroy
        result = subprocess.run(
            ["terraform", "destroy", "-auto-approve"],
            cwd="infra",
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            click.echo("✓ All resources destroyed successfully")
        else:
            click.echo(f"Warning: Terraform destroy failed: {result.stderr}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--service", "-s", help="Check health of specific service")
def health(service: Optional[str]):
    """Check health of deployed services."""
    try:
        health_checker = HealthChecker()

        if service:
            # Check specific service
            click.echo(f"Checking health of {service}...")
            health_status = health_checker.check_service_health(service)

            status_map = {
                0: "UNKNOWN",
                1: "SERVING",
                2: "NOT_SERVING",
                3: "SERVICE_UNKNOWN",
            }

            click.echo(f"Status: {status_map.get(health_status.status, 'UNKNOWN')}")
            click.echo(f"Message: {health_status.message}")
            click.echo(f"Timestamp: {health_status.timestamp}")

        else:
            # Check all services
            cmd = ["docker", "ps", "--filter", "name=iac-", "--format", "{{.Names}}"]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                container_names = result.stdout.strip().split("\n")
                service_names = [
                    name
                    for name in container_names
                    if name and not name.endswith("-envoy")
                ]

                if not service_names:
                    click.echo("No services found")
                    return

                click.echo(f"Checking health of {len(service_names)} service(s)...")

                health_results = health_checker.check_all_services(service_names)

                for service_name, health_status in health_results.items():
                    status_map = {
                        0: "UNKNOWN",
                        1: "SERVING",
                        2: "NOT_SERVING",
                        3: "SERVICE_UNKNOWN",
                    }

                    status = status_map.get(health_status.status, "UNKNOWN")
                    symbol = "✓" if health_status.status == 1 else "✗"

                    click.echo(f"  {symbol} {service_name}: {status}")
                    if health_status.message:
                        click.echo(f"    {health_status.message}")
            else:
                click.echo("No services found")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--service", "-s", help="Show logs for specific service")
@click.option("--tail", "-t", default=100, help="Number of lines to show")
@click.option("--follow", "-f", is_flag=True, help="Follow logs")
def logs(service: Optional[str], tail: int, follow: bool):
    """Show logs for deployed services."""
    try:
        docker_ops = DockerOps()

        if service:
            # Show logs for specific service
            logs = docker_ops.get_container_logs(service, tail)
            click.echo(logs)
        else:
            # Show logs for all services
            cmd = ["docker", "ps", "--filter", "name=iac-", "--format", "{{.Names}}"]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                container_names = result.stdout.strip().split("\n")
                service_names = [
                    name
                    for name in container_names
                    if name and not name.endswith("-envoy")
                ]

                if not service_names:
                    click.echo("No services found")
                    return

                for service_name in service_names:
                    click.echo(f"\n=== Logs for {service_name} ===")
                    logs = docker_ops.get_container_logs(service_name, tail)
                    click.echo(logs)
            else:
                click.echo("No services found")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
