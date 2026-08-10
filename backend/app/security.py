import hashlib
import hmac
import secrets
import time

from fastapi import Cookie, Header, HTTPException, status

from app.config import get_settings


SESSION_COOKIE_NAME = "investment_session"


def create_session_token() -> str:
    settings = get_settings()
    issued_at = int(time.time())
    expires_at = issued_at + settings.session_ttl_hours * 3600
    payload = f"v1.{issued_at}.{expires_at}"
    signature = hmac.new(
        settings.session_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{signature}"


def validate_session_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        version, issued_at, expires_at, signature = token.split(".", 3)
        payload = f"{version}.{issued_at}.{expires_at}"
        expected = hmac.new(
            get_settings().session_secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        return (
            version == "v1"
            and int(issued_at) <= int(time.time())
            and int(expires_at) > int(time.time())
            and secrets.compare_digest(signature, expected)
        )
    except (TypeError, ValueError):
        return False


def require_platform_token(
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> None:
    expected = get_settings().platform_token
    header_valid = bool(x_platform_token) and secrets.compare_digest(x_platform_token, expected)
    if not header_valid and not validate_session_token(session_cookie):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
