"""Tests for Flask API functionality."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
from iac_wrapper.api import create_app


@pytest.fixture
def app():
    """Create test Flask application."""
    with patch("iac_wrapper.auth.create_auth_handler"):
        test_app = create_app()
        test_app.config["TESTING"] = True
        return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestFlaskAPI:
    """Test Flask API endpoints."""

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data

    def test_health_endpoint_with_service_check(self, client):
        """Test health endpoint with service health checks."""
        with patch("iac_wrapper.controlplane.HealthChecker") as mock_health_checker:
            # Mock health checker
            mock_checker = Mock()
            mock_health_status = Mock()
            mock_health_status.status = 1  # SERVING
            mock_health_status.message = "Service healthy"
            mock_checker.check_all_services.return_value = {
                "service1": mock_health_status
            }
            mock_health_checker.return_value = mock_checker

            response = client.get("/health?check_services=true")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert data["status"] == "healthy"
            assert "services" in data

    @patch("iac_wrapper.auth.SupabaseAuth.require_auth")
    def test_deploy_endpoint_success(self, mock_auth, client):
        """Test successful deployment endpoint."""

        # Mock authentication
        def auth_decorator(f):
            return f

        mock_auth.return_value = auth_decorator

        # Mock deployment components
        with patch("iac_wrapper.gitops.GitOps") as mock_gitops, patch(
            "iac_wrapper.dockerize.DockerOps"
        ) as mock_docker, patch("iac_wrapper.envoy.EnvoyConfig") as mock_envoy:
            # Setup mocks
            mock_git_instance = Mock()
            mock_git_instance.fetch_repo.return_value = "/tmp/repo"
            mock_git_instance.detect_entrypoint.return_value = "main"
            mock_gitops.return_value = mock_git_instance

            mock_docker_instance = Mock()
            mock_docker_instance.build_image.return_value = "test-image:latest"
            mock_docker_instance.run_container.return_value = "container123"
            mock_docker_instance.run_envoy_sidecar.return_value = "envoy123"
            mock_docker.return_value = mock_docker_instance

            mock_envoy_instance = Mock()
            mock_envoy_instance.generate_config.return_value = "envoy config"
            mock_envoy.return_value = mock_envoy_instance

            # Test deployment request
            deploy_data = {"slugs": ["gh:testuser/testrepo"]}
            response = client.post(
                "/deploy", data=json.dumps(deploy_data), content_type="application/json"
            )

            assert response.status_code == 202
            data = json.loads(response.data)
            assert data["status"] == "accepted"
            assert "deployment_id" in data

    def test_deploy_endpoint_missing_slugs(self, client):
        """Test deployment endpoint with missing slugs."""
        with patch("iac_wrapper.auth.SupabaseAuth.require_auth") as mock_auth:
            # Mock authentication
            def auth_decorator(f):
                return f

            mock_auth.return_value = auth_decorator

            deploy_data = {}
            response = client.post(
                "/deploy", data=json.dumps(deploy_data), content_type="application/json"
            )

            assert response.status_code == 400
            data = json.loads(response.data)
            assert "error" in data

    def test_deploy_endpoint_invalid_json(self, client):
        """Test deployment endpoint with invalid JSON."""
        with patch("iac_wrapper.auth.SupabaseAuth.require_auth") as mock_auth:
            # Mock authentication
            def auth_decorator(f):
                return f

            mock_auth.return_value = auth_decorator

            response = client.post(
                "/deploy", data="invalid json", content_type="application/json"
            )

            assert response.status_code == 400

    @patch("iac_wrapper.auth.SupabaseAuth.require_auth")
    def test_logs_endpoint(self, mock_auth, client):
        """Test logs endpoint."""

        # Mock authentication
        def auth_decorator(f):
            return f

        mock_auth.return_value = auth_decorator

        with patch("iac_wrapper.dockerize.DockerOps") as mock_docker:
            mock_docker_instance = Mock()
            mock_docker_instance.get_container_logs.return_value = "test log content"
            mock_docker.return_value = mock_docker_instance

            response = client.get("/logs/test-service")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "logs" in data
            assert data["logs"] == "test log content"

    @patch("iac_wrapper.auth.SupabaseAuth.require_auth")
    def test_logs_endpoint_service_not_found(self, mock_auth, client):
        """Test logs endpoint with service not found."""

        # Mock authentication
        def auth_decorator(f):
            return f

        mock_auth.return_value = auth_decorator

        with patch("iac_wrapper.dockerize.DockerOps") as mock_docker:
            mock_docker_instance = Mock()
            mock_docker_instance.get_container_logs.side_effect = Exception(
                "Container not found"
            )
            mock_docker.return_value = mock_docker_instance

            response = client.get("/logs/nonexistent-service")
            assert response.status_code == 404

    @patch("iac_wrapper.auth.SupabaseAuth.require_auth")
    def test_services_endpoint(self, mock_auth, client):
        """Test services listing endpoint."""

        # Mock authentication
        def auth_decorator(f):
            return f

        mock_auth.return_value = auth_decorator

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "service1\nservice2\nservice1-envoy"

            response = client.get("/services")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert "services" in data
            # Should filter out envoy sidecars
            assert len(data["services"]) == 2

    def test_unauthorized_access(self, client):
        """Test unauthorized access to protected endpoints."""
        with patch("iac_wrapper.auth.SupabaseAuth.require_auth") as mock_auth:
            # Mock authentication failure
            def auth_decorator(f):
                def wrapper(*args, **kwargs):
                    from flask import jsonify

                    return jsonify({"error": "Unauthorized"}), 401

                return wrapper

            mock_auth.return_value = auth_decorator

            response = client.post("/deploy", json={"slugs": ["gh:test/repo"]})
            assert response.status_code == 401

    def test_cors_headers(self, client):
        """Test CORS headers are present."""
        response = client.get("/health")
        assert response.status_code == 200
        # CORS headers should be present if configured
        # This would depend on the actual CORS configuration in the app

    def test_error_handling(self, client):
        """Test general error handling."""
        # Test 404
        response = client.get("/nonexistent")
        assert response.status_code == 404

    def test_json_error_response(self, client):
        """Test JSON error responses."""
        response = client.post(
            "/deploy", data="not json", content_type="application/json"
        )
        assert response.status_code == 400

        # Should return JSON error
        data = json.loads(response.data)
        assert "error" in data


class TestApplicationFactory:
    """Test application factory function."""

    @patch("iac_wrapper.auth.create_auth_handler")
    def test_create_app_default(self, mock_auth):
        """Test app creation with default configuration."""
        app = create_app()
        assert isinstance(app, Flask)
        assert app.config["JSON_SORT_KEYS"] is False

    @patch("iac_wrapper.auth.create_auth_handler")
    def test_create_app_with_config(self, mock_auth):
        """Test app creation with custom configuration."""
        config = {"TESTING": True, "DEBUG": True}
        app = create_app(config)
        assert app.config["TESTING"] is True
        assert app.config["DEBUG"] is True

    @patch("iac_wrapper.auth.create_auth_handler")
    def test_create_app_auth_handler_creation(self, mock_auth):
        """Test that auth handler is created during app initialization."""
        create_app()
        mock_auth.assert_called_once()

    @patch("iac_wrapper.auth.create_auth_handler", side_effect=Exception("Auth error"))
    def test_create_app_auth_error_handling(self, mock_auth):
        """Test app creation with auth error."""
        # Should handle auth creation errors gracefully
        app = create_app()
        assert isinstance(app, Flask)
