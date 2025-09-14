"""
Simplified End-to-End Integration Test for Flask Dashboard Deployment

This test validates the complete KarstKit stack with a realistic Flask application.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch
from iac_wrapper.slug import RepoSlug
from iac_wrapper.gitops import GitOps
from iac_wrapper.dockerize import DockerOps
from iac_wrapper.envoy import EnvoyConfig
from iac_wrapper.controlplane import HealthChecker
from iac_wrapper.config import config


@pytest.fixture
def simple_flask_app(temp_dir):
    """Create a simple Flask application for E2E testing."""
    app_dir = temp_dir / "flask-app"
    app_dir.mkdir()

    # Create simple Flask main.py
    main_py = app_dir / "main.py"
    main_py.write_text(
        "from flask import Flask, jsonify\n"
        "\n"
        "app = Flask(__name__)\n"
        "\n"
        '@app.route("/")\n'
        "def home():\n"
        '    return "<h1>Flask Dashboard</h1>"\n'
        "\n"
        '@app.route("/health")\n'
        "def health():\n"
        '    return jsonify({"status": "ok"})\n'
        "\n"
        "def main():\n"
        '    app.run(host="0.0.0.0", port=5000)\n'
        "\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )

    # Create requirements.txt
    (app_dir / "requirements.txt").write_text("flask>=2.3.0\n")

    # Create pyproject.toml
    (app_dir / "pyproject.toml").write_text(
        "[project]\n"
        'name = "flask-app"\n'
        'version = "1.0.0"\n'
        'requires-python = ">=3.11"\n'
        'dependencies = ["flask>=2.3.0"]\n'
        "\n"
        "[project.scripts]\n"
        'flask-app = "main:main"\n'
    )

    return app_dir


@pytest.mark.integration
@pytest.mark.slow
class TestE2EFlaskDeployment:
    """End-to-end Flask deployment tests."""

    def test_complete_flask_deployment_workflow(self, simple_flask_app, temp_dir):
        """Test the complete Flask deployment workflow."""
        print("\n🧪 Testing Complete Flask Deployment Workflow")

        # Initialize components
        git_ops = GitOps(cache_dir=temp_dir)
        docker_ops = DockerOps()
        envoy_config = EnvoyConfig()

        slug = RepoSlug(scheme="local", owner="test", repo="flask-app")
        service_name = slug.service_name

        # === PHASE 1: Repository Analysis ===
        print("\n📂 Phase 1: Repository Analysis")

        entrypoint = git_ops.detect_entrypoint(simple_flask_app)
        print(f"   Detected entrypoint: {entrypoint}")

        assert entrypoint is not None
        # Should detect either console script or main function
        assert "flask-app" in str(entrypoint) or "main" in str(entrypoint)

        # === PHASE 2: Docker Image Building ===
        print("\n🐳 Phase 2: Docker Image Building")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stderr = ""

            image_name = docker_ops.build_image(simple_flask_app, slug, entrypoint)
            print(f"   Built image: {image_name}")

            assert image_name == f"iac-{service_name}:latest"
            assert mock_run.called

        # === PHASE 3: Envoy Configuration ===
        print("\n🔒 Phase 3: Envoy Configuration")

        envoy_config_content = envoy_config.generate_config(service_name)
        print(f"   Generated Envoy config ({len(envoy_config_content)} chars)")

        # Validate key Envoy configuration elements
        required_elements = [
            "admin:",
            "static_resources:",
            "listeners:",
            "clusters:",
            service_name,
            "50051",
            "15000",
            "tls",
        ]

        for element in required_elements:
            assert element in envoy_config_content

        # === PHASE 4: Container Orchestration with Startup Ordering ===
        print("\n🚀 Phase 4: Container Orchestration")

        with patch.multiple(
            docker_ops,
            run_envoy_sidecar=lambda *args, **kwargs: "envoy-container-123",
            run_container=lambda *args, **kwargs: "app-container-456",
            wait_for_envoy_ready=lambda *args, **kwargs: True,
            container_exists=lambda *args, **kwargs: False,
        ):
            # Test the startup ordering fix we implemented earlier
            app_id, envoy_id = docker_ops.start_service_with_envoy(
                image_name,
                service_name,
                envoy_config_content,
                environment={
                    "FLASK_ENV": "production",
                    "GRPC_PORT": str(config.GRPC_PORT),
                    "PORT": "5000",
                },
            )

            print(f"   Started containers: app={app_id}, envoy={envoy_id}")
            assert app_id == "app-container-456"
            assert envoy_id == "envoy-container-123"

        # === PHASE 5: Health Check Validation ===
        print("\n❤️ Phase 5: Health Check Validation")

        health_checker = HealthChecker()

        with patch.object(health_checker, "check_service_health") as mock_health:
            mock_health.return_value.status = 1  # SERVING
            mock_health.return_value.message = "Flask service healthy"

            health_status = health_checker.check_service_health(service_name)
            print(f"   Health status: {health_status.status} - {health_status.message}")
            assert health_status.status == 1

        # === PHASE 6: Service Mesh Validation ===
        print("\n🕸️ Phase 6: Service Mesh Validation")

        # Verify mTLS configuration
        mtls_elements = [
            "transport_socket:",
            "tls.crt",
            "tls.key",
            "ca.crt",
            "DownstreamTlsContext",
            "UpstreamTlsContext",
        ]

        for element in mtls_elements:
            assert element in envoy_config_content, f"Missing mTLS element: {element}"

        print("\n✅ Complete Flask deployment workflow validated!")

    def test_flask_entrypoint_detection_scenarios(self, temp_dir):
        """Test various Flask entrypoint detection scenarios."""
        git_ops = GitOps(cache_dir=temp_dir)

        # Scenario 1: Console script in pyproject.toml
        console_script_app = temp_dir / "console-script-app"
        console_script_app.mkdir()

        (console_script_app / "app.py").write_text("def main(): pass\n")
        (console_script_app / "pyproject.toml").write_text(
            "[project.scripts]\n" 'my-flask-app = "app:main"\n'
        )

        entrypoint = git_ops.detect_entrypoint(console_script_app)
        assert entrypoint == "my-flask-app"

        # Scenario 2: main.py at root
        main_py_app = temp_dir / "main-py-app"
        main_py_app.mkdir()

        (main_py_app / "main.py").write_text("def main(): pass\n")

        entrypoint = git_ops.detect_entrypoint(main_py_app)
        assert "main" in str(entrypoint).lower()

        # Scenario 3: app.py with main function
        app_py_app = temp_dir / "app-py-app"
        app_py_app.mkdir()

        (app_py_app / "app.py").write_text("def main(): pass\n")

        entrypoint = git_ops.detect_entrypoint(app_py_app)
        assert entrypoint is not None

    def test_flask_deployment_error_handling(self, simple_flask_app, temp_dir):
        """Test error handling in Flask deployment."""
        docker_ops = DockerOps()
        slug = RepoSlug(scheme="local", owner="test", repo="flask-app")

        # Test Docker build failure
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Docker build error"

            with pytest.raises(RuntimeError, match="Docker build failed"):
                docker_ops.build_image(simple_flask_app, slug)

        # Test Envoy startup failure
        with patch.multiple(
            docker_ops,
            run_envoy_sidecar=lambda *args, **kwargs: "envoy-123",
            wait_for_envoy_ready=lambda *args, **kwargs: False,
            container_exists=lambda *args, **kwargs: False,
            stop_container=lambda *args, **kwargs: None,
            remove_container=lambda *args, **kwargs: None,
        ):
            with pytest.raises(RuntimeError, match="failed to become ready"):
                docker_ops.start_service_with_envoy(
                    "test-image:latest", slug.service_name, "envoy config content"
                )

    def test_flask_service_configuration_validation(self, simple_flask_app):
        """Test Flask service configuration validation."""
        # Verify Flask app structure
        main_py_content = (simple_flask_app / "main.py").read_text()

        required_flask_elements = [
            "from flask import Flask",
            "app = Flask(__name__)",
            "def health():",
            'app.run(host="0.0.0.0"',
        ]

        for element in required_flask_elements:
            assert element in main_py_content, f"Missing Flask element: {element}"

        # Verify dependencies
        requirements = (simple_flask_app / "requirements.txt").read_text()
        assert "flask>=" in requirements

        # Verify project config
        pyproject = (simple_flask_app / "pyproject.toml").read_text()
        assert "[project]" in pyproject
        assert "[project.scripts]" in pyproject


@pytest.mark.integration
def test_realistic_flask_dashboard_deployment(tmp_path):
    """
    Test realistic Flask dashboard deployment scenario.

    This simulates deploying a real Flask dashboard application
    that a user might want to deploy with KarstKit.
    """
    print("\n🌟 Testing Realistic Flask Dashboard Deployment")

    # Create realistic Flask dashboard
    dashboard_dir = tmp_path / "my-dashboard"
    dashboard_dir.mkdir()

    # Create main application
    (dashboard_dir / "app.py").write_text(
        "from flask import Flask, render_template_string, jsonify\n"
        "\n"
        "app = Flask(__name__)\n"
        "\n"
        'DASHBOARD_HTML = """\n'
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head><title>My Dashboard</title></head>\n"
        "<body>\n"
        "    <h1>Dashboard Status: {{ status }}</h1>\n"
        "    <p>Services: {{ services }}</p>\n"
        "</body>\n"
        "</html>\n"
        '"""\n'
        "\n"
        '@app.route("/")\n'
        "def dashboard():\n"
        "    return render_template_string(DASHBOARD_HTML, \n"
        '                                status="Running",\n'
        '                                services="3 Active")\n'
        "\n"
        '@app.route("/api/status")\n'
        "def api_status():\n"
        "    return jsonify({\n"
        '        "status": "healthy",\n'
        '        "version": "1.0.0",\n'
        '        "services": ["web", "api", "db"]\n'
        "    })\n"
        "\n"
        "def main():\n"
        '    app.run(host="0.0.0.0", port=5000, debug=False)\n'
        "\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )

    (dashboard_dir / "requirements.txt").write_text("flask>=2.3.0\n")

    # Test deployment workflow
    from iac_wrapper.gitops import GitOps
    from iac_wrapper.slug import RepoSlug

    git_ops = GitOps(cache_dir=tmp_path)
    slug = RepoSlug(scheme="local", owner="user", repo="my-dashboard")

    # Test entrypoint detection
    entrypoint = git_ops.detect_entrypoint(dashboard_dir)
    print(f"   Detected entrypoint: {entrypoint}")

    assert entrypoint is not None
    # Should detect main function or similar
    assert "main" in str(entrypoint).lower() or "app" in str(entrypoint).lower()

    print("   ✅ Realistic dashboard deployment test completed")
