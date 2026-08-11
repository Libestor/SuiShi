from __future__ import annotations

import secrets
import time
from collections import OrderedDict, deque
from ipaddress import ip_address, ip_network
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.security import (
    SESSION_COOKIE_NAME,
    create_session_token,
    revoke_session_token,
    validate_session_token,
)


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
_attempt_window_seconds = 15 * 60
_max_attempts = 5


class FailedLoginLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int, max_identities: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_identities = max_identities
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    @property
    def identity_count(self) -> int:
        with self._lock:
            return len(self._attempts)

    def _purge_locked(self, now: float) -> None:
        expired_before = now - self.window_seconds
        for key in list(self._attempts):
            attempts = self._attempts[key]
            while attempts and attempts[0] <= expired_before:
                attempts.popleft()
            if not attempts:
                self._attempts.pop(key, None)
        while len(self._attempts) > self.max_identities:
            self._attempts.popitem(last=False)

    def purge(self, *, now: float | None = None) -> None:
        with self._lock:
            self._purge_locked(time.monotonic() if now is None else now)

    def is_limited(self, client_key: str, *, now: float | None = None) -> bool:
        with self._lock:
            current = time.monotonic() if now is None else now
            self._purge_locked(current)
            attempts = self._attempts.get(client_key)
            if attempts is None:
                return False
            self._attempts.move_to_end(client_key)
            return len(attempts) >= self.max_attempts

    def record_failure(self, client_key: str, *, now: float | None = None) -> None:
        with self._lock:
            current = time.monotonic() if now is None else now
            self._purge_locked(current)
            attempts = self._attempts.setdefault(client_key, deque())
            attempts.append(current)
            while len(attempts) > self.max_attempts:
                attempts.popleft()
            self._attempts.move_to_end(client_key)
            while len(self._attempts) > self.max_identities:
                self._attempts.popitem(last=False)

    def reset(self, client_key: str) -> None:
        with self._lock:
            self._attempts.pop(client_key, None)


_failed_login_limiter = FailedLoginLimiter(
    max_attempts=_max_attempts,
    window_seconds=_attempt_window_seconds,
    max_identities=get_settings().login_rate_limit_max_identities,
)


class LoginRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


def _client_key(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        peer_ip = ip_address(peer)
    except ValueError:
        return peer

    trusted_networks = []
    for value in get_settings().trusted_proxy_cidrs.split(","):
        value = value.strip()
        if value:
            trusted_networks.append(ip_network(value, strict=False))
    if not any(peer_ip in network for network in trusted_networks):
        return str(peer_ip)

    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if not forwarded or "," in forwarded:
        return str(peer_ip)
    try:
        return str(ip_address(forwarded))
    except ValueError:
        return str(peer_ip)


def _check_rate_limit(client_key: str) -> None:
    if _failed_login_limiter.is_limited(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(_attempt_window_seconds)},
        )


@router.get("/session")
def session_status(request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    return {
        "authenticated": validate_session_token(db, request.cookies.get(SESSION_COOKIE_NAME))
    }


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> None:
    client_key = _client_key(request)
    _check_rate_limit(client_key)
    settings = get_settings()
    if not secrets.compare_digest(payload.token, settings.platform_token):
        _failed_login_limiter.record_failure(client_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    _failed_login_limiter.reset(client_key)
    session_token = create_session_token(db)
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> None:
    settings = get_settings()
    revoke_session_token(db, request.cookies.get(SESSION_COOKIE_NAME))
    db.commit()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
