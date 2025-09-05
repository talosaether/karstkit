"""Flask admin API with HTTP and Unix domain socket support."""

import json
import os
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify, Response
from .config import config
from .auth import get_auth_handler
from .slug import parse_slug
from .gitops import GitOps
from .dockerize import DockerOps
from .envoy import EnvoyConfig
from .controlplane import HealthChecker


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.urandom(24)

    # Initialize components
    git_ops = GitOps()
    docker_ops = DockerOps()
    envoy_config = EnvoyConfig()
    health_checker = HealthChecker()

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify(
            {
                "status": "healthy",
                "timestamp": "2024-01-01T00:00:00Z",
                "version": "0.1.0",
            }
        )

    @app.route("/deploy", methods=["POST"])
    @get_auth_handler().require_auth
    def deploy():
        """Deploy services from repository slugs."""
        try:
            data = request.get_json()
            if not data or "slugs" not in data:
                return jsonify({"error": "Missing slugs in request body"}), 400

            slugs = data["slugs"]
            if not isinstance(slugs, list):
                return jsonify({"error": "Slugs must be a list"}), 400

            wait_for_ready = data.get("wait_for_ready", True)

            def deploy_stream():
                """Stream deployment progress."""
                results = []

                for i, slug_str in enumerate(slugs):
                    try:
                        # Parse slug
                        slug = parse_slug(slug_str)
                        service_name = slug.service_name

                        yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'parsing'})}\n\n"

                        # Fetch repository
                        yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'fetching'})}\n\n"
                        repo_path = git_ops.fetch_repo(slug)

                        # Detect entrypoint
                        yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'detecting_entrypoint'})}\n\n"
                        entrypoint = git_ops.detect_entrypoint(repo_path)

                        if not entrypoint:
                            yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'error', 'message': 'No entrypoint detected'})}\n\n"
                            results.append(
                                {
                                    "slug": slug_str,
                                    "service_name": service_name,
                                    "deployed": False,
                                    "error": "No entrypoint detected",
                                }
                            )
                            continue

                        # Build Docker image
                        yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'building'})}\n\n"
                        image_name = docker_ops.build_image(repo_path, slug, entrypoint)

                        # Generate Envoy config
                        yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'configuring_envoy'})}\n\n"
                        envoy_config_content = envoy_config.generate_config(
                            service_name
                        )

                        # Run containers
                        yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'starting_containers'})}\n\n"

                        # Stop existing containers if they exist
                        if docker_ops.container_exists(service_name):
                            docker_ops.stop_container(service_name)
                            docker_ops.remove_container(service_name)

                        if docker_ops.container_exists(f"{service_name}-envoy"):
                            docker_ops.stop_container(f"{service_name}-envoy")
                            docker_ops.remove_container(f"{service_name}-envoy")

                        # Start new containers
                        container_id = docker_ops.run_container(
                            image_name,
                            service_name,
                            environment={
                                "OTEL_EXPORTER_OTLP_ENDPOINT": config.OTEL_EXPORTER_OTLP_ENDPOINT,
                                "GRPC_PORT": str(config.GRPC_PORT),
                            },
                        )

                        envoy_container_id = docker_ops.run_envoy_sidecar(
                            service_name, envoy_config_content
                        )

                        # Check health if requested
                        health_status = None
                        if wait_for_ready:
                            yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'health_check'})}\n\n"
                            try:
                                health_status = health_checker.check_service_health(
                                    service_name
                                )
                                # Convert protobuf to dict for JSON serialization
                                if hasattr(health_status, "status"):
                                    health_status = {
                                        "status": health_status.status,
                                        "message": health_status.message,
                                        "timestamp": health_status.timestamp,
                                    }
                            except Exception as e:
                                health_status = {
                                    "status": "UNKNOWN",
                                    "message": f"Health check failed: {str(e)}",
                                }

                        yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'completed'})}\n\n"

                        results.append(
                            {
                                "slug": slug_str,
                                "service_name": service_name,
                                "deployed": True,
                                "image_name": image_name,
                                "container_id": container_id,
                                "envoy_container_id": envoy_container_id,
                                "health_status": health_status,
                            }
                        )

                    except Exception as e:
                        yield f"data: {json.dumps({'step': i+1, 'total': len(slugs), 'slug': slug_str, 'status': 'error', 'message': str(e)})}\n\n"
                        results.append(
                            {
                                "slug": slug_str,
                                "service_name": slug_str.split(":")[1].split("/")[1]
                                if ":" in slug_str
                                else slug_str,
                                "deployed": False,
                                "error": str(e),
                            }
                        )

                # Final result
                yield f"data: {json.dumps({'status': 'completed', 'results': results})}\n\n"

            return Response(deploy_stream(), mimetype="text/plain")

        except Exception as e:
            return jsonify({"error": f"Deployment failed: {str(e)}"}), 500

    @app.route("/services", methods=["GET"])
    @get_auth_handler().require_auth
    def list_services():
        """List deployed services."""
        try:
            # Get running containers
            cmd = ["docker", "ps", "--filter", "name=iac-", "--format", "{{.Names}}"]
            result = subprocess.run(cmd, capture_output=True, text=True)

            services = []
            if result.returncode == 0:
                container_names = result.stdout.strip().split("\n")
                for name in container_names:
                    if name and not name.endswith("-envoy"):
                        services.append(
                            {
                                "name": name,
                                "status": "running"
                                if docker_ops.container_running(name)
                                else "stopped",
                            }
                        )

            return jsonify({"services": services})

        except Exception as e:
            return jsonify({"error": f"Failed to list services: {str(e)}"}), 500

    @app.route("/services/<service_name>/logs", methods=["GET"])
    @get_auth_handler().require_auth
    def get_service_logs(service_name: str):
        """Get logs for a service."""
        try:
            tail = request.args.get("tail", 100, type=int)
            follow = request.args.get("follow", False, type=bool)

            if follow:

                def log_stream():
                    cmd = ["docker", "logs", "-f", "--tail", str(tail), service_name]
                    process = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                    )

                    try:
                        for line in process.stdout:
                            yield f"data: {json.dumps({'log': line.rstrip()})}\n\n"
                    finally:
                        process.terminate()

                return Response(log_stream(), mimetype="text/plain")
            else:
                logs = docker_ops.get_container_logs(service_name, tail)
                return jsonify({"logs": logs})

        except Exception as e:
            return jsonify({"error": f"Failed to get logs: {str(e)}"}), 500

    @app.route("/services/<service_name>/health", methods=["GET"])
    @get_auth_handler().require_auth
    def get_service_health(service_name: str):
        """Get health status for a service."""
        try:
            health_status = health_checker.check_service_health(service_name)
            return jsonify(
                {
                    "service_name": service_name,
                    "health_status": {
                        "status": health_status.status,
                        "message": health_status.message,
                        "timestamp": health_status.timestamp,
                    },
                }
            )

        except Exception as e:
            return jsonify({"error": f"Failed to get health: {str(e)}"}), 500

    @app.route("/destroy", methods=["POST"])
    @get_auth_handler().require_auth
    def destroy():
        """Destroy all deployed services."""
        try:
            # Get all iac containers
            cmd = [
                "docker",
                "ps",
                "-a",
                "--filter",
                "name=iac-",
                "--format",
                "{{.Names}}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            destroyed = []
            if result.returncode == 0:
                container_names = result.stdout.strip().split("\n")
                for name in container_names:
                    if name:
                        try:
                            docker_ops.stop_container(name)
                            docker_ops.remove_container(name)
                            destroyed.append(name)
                        except Exception as e:
                            # Continue with other containers
                            pass

            return jsonify({"destroyed": destroyed})

        except Exception as e:
            return jsonify({"error": f"Failed to destroy services: {str(e)}"}), 500

    return app


def run_app():
    """Run the Flask application."""
    app = create_app()

    # Ensure directories exist
    config.ensure_directories()

    # Create Unix domain socket directory if needed
    socket_path = Path(config.FLASK_SOCKET_PATH)
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    # Run with both HTTP and Unix domain socket
    if config.DEBUG:
        app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=True)
    else:
        # In production, you might want to use a proper WSGI server
        app.run(host=config.FLASK_HOST, port=config.FLASK_PORT)


if __name__ == "__main__":
    run_app()
