"""Tests for API authentication functionality."""

import pytest
from unittest.mock import Mock, patch
from flask import Flask, request
from iac_wrapper.auth import SupabaseAuth, create_auth_handler


class TestSupabaseAuth:
    """Test SupabaseAuth class."""

    def test_init(self):
        """Test SupabaseAuth initialization."""
        auth = SupabaseAuth("https://test.supabase.co", "test-key")
        assert auth.supabase_url == "https://test.supabase.co"
        assert auth.service_role_key == "test-key"
        assert auth.jwks_url == "https://test.supabase.co/rest/v1/auth/jwks"

    def test_init_with_trailing_slash(self):
        """Test SupabaseAuth initialization with trailing slash."""
        auth = SupabaseAuth("https://test.supabase.co/", "test-key")
        assert auth.supabase_url == "https://test.supabase.co"
        assert auth.jwks_url == "https://test.supabase.co/rest/v1/auth/jwks"

    @patch("requests.get")
    def test_validate_jwt_success(self, mock_get):
        """Test successful JWT validation."""
        # Mock JWKS response
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "keys": [{"kid": "test-key-id", "kty": "RSA", "n": "test-n", "e": "AQAB"}]
        }

        # Mock JWT decode
        with patch("jwt.decode") as mock_decode:
            mock_decode.return_value = {
                "sub": "user123",
                "email": "test@example.com",
                "aud": "authenticated",
            }

            auth = SupabaseAuth("https://test.supabase.co", "test-key")
            result = auth.validate_jwt("Bearer valid.jwt.token")

            assert result is not None
            assert result["sub"] == "user123"
            assert result["email"] == "test@example.com"

    @patch("requests.get")
    def test_validate_jwt_without_bearer(self, mock_get):
        """Test JWT validation without Bearer prefix."""
        # Mock JWKS response
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "keys": [{"kid": "test-key-id", "kty": "RSA", "n": "test-n", "e": "AQAB"}]
        }

        # Mock JWT decode
        with patch("jwt.decode") as mock_decode:
            mock_decode.return_value = {"sub": "user123", "email": "test@example.com"}

            auth = SupabaseAuth("https://test.supabase.co", "test-key")
            result = auth.validate_jwt("valid.jwt.token")

            assert result is not None
            assert result["sub"] == "user123"

    @patch("requests.get")
    def test_validate_jwt_no_kid(self, mock_get):
        """Test JWT validation with no key ID."""
        # Mock JWT header without kid
        with patch("jwt.get_unverified_header") as mock_header:
            mock_header.return_value = {}

            auth = SupabaseAuth("https://test.supabase.co", "test-key")
            result = auth.validate_jwt("Bearer valid.jwt.token")

            assert result is None

    @patch("requests.get")
    def test_validate_jwt_jwks_failure(self, mock_get):
        """Test JWT validation when JWKS fetch fails."""
        # Mock failed JWKS request
        mock_get.side_effect = Exception("Network error")

        auth = SupabaseAuth("https://test.supabase.co", "test-key")
        result = auth.validate_jwt("Bearer valid.jwt.token")

        assert result is None

    @patch("requests.get")
    def test_validate_jwt_no_matching_key(self, mock_get):
        """Test JWT validation when no matching key is found."""
        # Mock JWKS response with different key ID
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "keys": [
                {"kid": "different-key-id", "kty": "RSA", "n": "test-n", "e": "AQAB"}
            ]
        }

        # Mock JWT header with different key ID
        with patch("jwt.get_unverified_header") as mock_header:
            mock_header.return_value = {"kid": "test-key-id"}

            auth = SupabaseAuth("https://test.supabase.co", "test-key")
            result = auth.validate_jwt("Bearer valid.jwt.token")

            assert result is None

    @patch("requests.get")
    def test_validate_jwt_decode_failure(self, mock_get):
        """Test JWT validation when decode fails."""
        # Mock JWKS response
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "keys": [{"kid": "test-key-id", "kty": "RSA", "n": "test-n", "e": "AQAB"}]
        }

        # Mock JWT decode failure
        with patch("jwt.decode") as mock_decode:
            mock_decode.side_effect = Exception("Invalid token")

            auth = SupabaseAuth("https://test.supabase.co", "test-key")
            result = auth.validate_jwt("Bearer invalid.jwt.token")

            assert result is None

    def test_require_auth_decorator_missing_header(self):
        """Test require_auth decorator with missing Authorization header."""
        app = Flask(__name__)
        auth = SupabaseAuth("https://test.supabase.co", "test-key")

        @app.route("/test")
        @auth.require_auth
        def test_endpoint():
            return {"status": "success"}

        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 401
            assert b"Missing Authorization header" in response.data

    def test_require_auth_decorator_invalid_token(self):
        """Test require_auth decorator with invalid token."""
        app = Flask(__name__)
        auth = SupabaseAuth("https://test.supabase.co", "test-key")

        @app.route("/test")
        @auth.require_auth
        def test_endpoint():
            return {"status": "success"}

        # Mock validate_jwt to return None (invalid token)
        with patch.object(auth, "validate_jwt", return_value=None):
            with app.test_client() as client:
                response = client.get(
                    "/test", headers={"Authorization": "Bearer invalid.token"}
                )
                assert response.status_code == 401
                assert b"Invalid or expired token" in response.data

    def test_require_auth_decorator_valid_token(self):
        """Test require_auth decorator with valid token."""
        app = Flask(__name__)
        auth = SupabaseAuth("https://test.supabase.co", "test-key")

        @app.route("/test")
        @auth.require_auth
        def test_endpoint():
            return {"status": "success", "user": request.user}

        # Mock validate_jwt to return valid user data
        user_data = {"sub": "user123", "email": "test@example.com"}
        with patch.object(auth, "validate_jwt", return_value=user_data):
            with app.test_client() as client:
                response = client.get(
                    "/test", headers={"Authorization": "Bearer valid.token"}
                )
                assert response.status_code == 200
                assert b"success" in response.data


class TestCreateAuthHandler:
    """Test create_auth_handler function."""

    @patch("iac_wrapper.config.config")
    def test_create_auth_handler_success(self, mock_config):
        """Test successful auth handler creation."""
        mock_config.SUPABASE_URL = "https://test.supabase.co"
        mock_config.SUPABASE_SERVICE_ROLE_KEY = "test-key"

        auth_handler = create_auth_handler()

        assert isinstance(auth_handler, SupabaseAuth)
        assert auth_handler.supabase_url == "https://test.supabase.co"
        assert auth_handler.service_role_key == "test-key"

    @patch("iac_wrapper.config.config")
    def test_create_auth_handler_missing_url(self, mock_config):
        """Test auth handler creation with missing URL."""
        mock_config.SUPABASE_URL = ""
        mock_config.SUPABASE_SERVICE_ROLE_KEY = "test-key"

        with pytest.raises(ValueError, match="Missing required environment variables"):
            create_auth_handler()

    @patch("iac_wrapper.config.config")
    def test_create_auth_handler_missing_key(self, mock_config):
        """Test auth handler creation with missing key."""
        mock_config.SUPABASE_URL = "https://test.supabase.co"
        mock_config.SUPABASE_SERVICE_ROLE_KEY = ""

        with pytest.raises(ValueError, match="Missing required environment variables"):
            create_auth_handler()
