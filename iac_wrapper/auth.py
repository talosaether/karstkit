"""Authentication module for Supabase JWT validation."""

import jwt
import requests
from typing import Optional, Dict, Any
from functools import wraps
from flask import request, jsonify, current_app
from .config import config


class SupabaseAuth:
    """Supabase authentication handler."""

    def __init__(self, supabase_url: str, service_role_key: str):
        self.supabase_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key
        self.jwks_url = f"{self.supabase_url}/rest/v1/auth/jwks"

    def validate_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a JWT token against Supabase."""
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith("Bearer "):
                token = token[7:]

            # Decode the token without verification first to get the key ID
            unverified_header = jwt.get_unverified_header(token)
            key_id = unverified_header.get("kid")

            if not key_id:
                return None

            # Fetch the public key from Supabase
            response = requests.get(self.jwks_url)
            response.raise_for_status()
            jwks = response.json()

            # Find the matching key
            public_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == key_id:
                    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                    break

            if not public_key:
                return None

            # Verify and decode the token
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience="authenticated",
                issuer=self.supabase_url,
            )

            return payload

        except (jwt.InvalidTokenError, requests.RequestException, KeyError) as e:
            current_app.logger.warning(f"JWT validation failed: {e}")
            return None

    def require_auth(self, f):
        """Decorator to require authentication."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get("Authorization")

            if not auth_header:
                return jsonify({"error": "Missing Authorization header"}), 401

            payload = self.validate_jwt(auth_header)
            if not payload:
                return jsonify({"error": "Invalid or expired token"}), 401

            # Add user info to request context
            request.user = payload
            return f(*args, **kwargs)

        return decorated_function


def create_auth_handler() -> SupabaseAuth:
    """Create an authentication handler instance."""
    config.validate()
    return SupabaseAuth(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


# Global auth handler - will be created when needed
auth_handler = None


def get_auth_handler():
    """Get the global auth handler, creating it if necessary."""
    global auth_handler
    if auth_handler is None:
        auth_handler = create_auth_handler()
    return auth_handler
