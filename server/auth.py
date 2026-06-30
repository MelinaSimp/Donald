import secrets
from fastapi import HTTPException, Request
from server.config import settings


def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return secrets.compare_digest(a, b)


def extract_bearer_token(request: Request) -> str | None:
    """Extract token from Authorization header (Bearer scheme)."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def extract_custom_header_token(request: Request) -> str | None:
    """Extract token from X-Auth-Token header."""
    return request.headers.get("X-Auth-Token")


def extract_query_param_token(request: Request) -> str | None:
    """Extract token from ?token= query parameter."""
    return request.query_params.get("token")


def validate_token(request: Request) -> bool:
    """
    Validate bearer token from any of three sources:
    1. Authorization: Bearer <token>
    2. X-Auth-Token: <token>
    3. ?token=<token>

    Returns True if token matches (via constant-time compare).
    """
    token = extract_bearer_token(request) or extract_custom_header_token(
        request
    ) or extract_query_param_token(request)

    if not token:
        return False

    return constant_time_compare(token, settings.bearer_token)


def require_auth(request: Request) -> None:
    """Dependency: raise 403 if token invalid."""
    if not validate_token(request):
        raise HTTPException(status_code=403, detail="Unauthorized")
