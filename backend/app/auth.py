from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.security import SESSION_COOKIE_NAME, create_session_token, validate_session_token


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
_failed_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempt_window_seconds = 15 * 60
_max_attempts = 5


class LoginRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _check_rate_limit(client_key: str) -> None:
    now = time.monotonic()
    attempts = _failed_attempts[client_key]
    while attempts and now - attempts[0] > _attempt_window_seconds:
        attempts.popleft()
    if len(attempts) >= _max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(_attempt_window_seconds)},
        )


@router.get("/session")
def session_status(request: Request) -> dict[str, bool]:
    return {"authenticated": validate_session_token(request.cookies.get(SESSION_COOKIE_NAME))}


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(payload: LoginRequest, request: Request, response: Response) -> None:
    client_key = _client_key(request)
    _check_rate_limit(client_key)
    settings = get_settings()
    if not secrets.compare_digest(payload.token, settings.platform_token):
        _failed_attempts[client_key].append(time.monotonic())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    _failed_attempts.pop(client_key, None)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
