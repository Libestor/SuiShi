from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.auth import FailedLoginLimiter, _client_key
from app.config import Settings


STRONG_PLATFORM_TOKEN = "platform-token-0123456789abcdef012345"
STRONG_SESSION_SECRET = "session-secret-0123456789abcdef012345"
STRONG_RUNNER_SECRET = "runner-secret-0123456789abcdef01234567"


def _settings(**overrides: str) -> Settings:
    values = {
        "platform_token": STRONG_PLATFORM_TOKEN,
        "session_secret": STRONG_SESSION_SECRET,
        "runner_shared_secret": STRONG_RUNNER_SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def test_security_credentials_are_required(monkeypatch) -> None:
    for name in ("PLATFORM_TOKEN", "SESSION_SECRET", "RUNNER_SHARED_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("platform_token", "dev-investment-token"),
        ("session_secret", "dev-session-secret-change-me"),
        ("runner_shared_secret", "dev-runner-secret"),
    ],
)
def test_public_development_credentials_are_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_distinct_strong_credentials_are_accepted() -> None:
    settings = _settings()
    assert settings.platform_token == STRONG_PLATFORM_TOKEN


def test_untrusted_peer_cannot_spoof_forwarded_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.auth.get_settings",
        lambda: SimpleNamespace(trusted_proxy_cidrs="172.31.251.10/32"),
    )
    assert _client_key(_request("198.51.100.20", "203.0.113.50")) == "198.51.100.20"


def test_trusted_gateway_can_supply_one_canonical_client_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.auth.get_settings",
        lambda: SimpleNamespace(trusted_proxy_cidrs="172.31.251.10/32"),
    )
    assert _client_key(_request("172.31.251.10", "203.0.113.50")) == "203.0.113.50"
    assert _client_key(_request("172.31.251.10", "spoofed, 203.0.113.50")) == "172.31.251.10"


def test_failed_login_state_is_bounded_and_expires() -> None:
    limiter = FailedLoginLimiter(max_attempts=5, window_seconds=60, max_identities=3)
    limiter.record_failure("one", now=1)
    limiter.record_failure("two", now=2)
    limiter.record_failure("three", now=3)
    limiter.record_failure("four", now=4)
    for attempt in range(10):
        limiter.record_failure("four", now=5 + attempt)
    assert limiter.identity_count == 3
    assert limiter.is_limited("four", now=14)
    limiter.purge(now=75)
    assert limiter.identity_count == 0
