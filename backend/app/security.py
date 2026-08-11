import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AuthSession


SESSION_COOKIE_NAME = "investment_session"


def _signed_session_payload(session_id: str, issued_at: int, expires_at: int) -> str:
    return f"v2.{session_id}.{issued_at}.{expires_at}"


def _parse_session_token(token: str | None) -> tuple[str, int, int] | None:
    if not token:
        return None
    try:
        version, session_id, issued_at_raw, expires_at_raw, signature = token.split(".", 4)
        issued_at = int(issued_at_raw)
        expires_at = int(expires_at_raw)
        payload = _signed_session_payload(session_id, issued_at, expires_at)
        expected = hmac.new(
            get_settings().session_secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        now = int(time.time())
        if (
            version != "v2"
            or not session_id
            or issued_at > now
            or expires_at <= now
            or not secrets.compare_digest(signature, expected)
        ):
            return None
        return session_id, issued_at, expires_at
    except (TypeError, ValueError):
        return None


def create_session_token(db: Session) -> str:
    settings = get_settings()
    issued_at = int(time.time())
    expires_at = issued_at + settings.session_ttl_hours * 3600
    session_id = secrets.token_urlsafe(32)
    payload = _signed_session_payload(session_id, issued_at, expires_at)
    signature = hmac.new(
        settings.session_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    now = datetime.now(timezone.utc)
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    db.add(
        AuthSession(
            id=session_id,
            issued_at=datetime.fromtimestamp(issued_at, timezone.utc),
            expires_at=datetime.fromtimestamp(expires_at, timezone.utc),
        )
    )
    return f"{payload}.{signature}"


def validate_session_token(db: Session, token: str | None) -> bool:
    parsed = _parse_session_token(token)
    if parsed is None:
        return False
    session_id, _, expires_at = parsed
    now = datetime.now(timezone.utc)
    return (
        db.scalar(
            select(AuthSession.id).where(
                AuthSession.id == session_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        is not None
        and expires_at > int(time.time())
    )


def revoke_session_token(db: Session, token: str | None) -> None:
    parsed = _parse_session_token(token)
    if parsed is None:
        return
    session = db.get(AuthSession, parsed[0])
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)


def require_platform_token(
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> None:
    expected = get_settings().platform_token
    header_valid = bool(x_platform_token) and secrets.compare_digest(x_platform_token, expected)
    if not header_valid and not validate_session_token(db, session_cookie):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
