from __future__ import annotations

import os
from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"
TEST_PLATFORM_TOKEN = "test-platform-token-0123456789abcdef"
TEST_SESSION_SECRET = "test-session-secret-0123456789abcdef"
TEST_RUNNER_SECRET = "test-runner-secret-0123456789abcdef"

os.environ["PLATFORM_TOKEN"] = TEST_PLATFORM_TOKEN
os.environ["SESSION_SECRET"] = TEST_SESSION_SECRET
os.environ["RUNNER_SHARED_SECRET"] = TEST_RUNNER_SECRET
os.environ["SCHEDULER_ENABLED"] = "false"

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Asset, Basket  # noqa: E402


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    session.add_all(
        [
            Basket(
                code="emergency",
                name="应急储备金",
                target_ratio=Decimal("0"),
                cash_balance_cny=Decimal("50000"),
                emergency_target_cny=Decimal("60000"),
            ),
            Basket(
                code="growth",
                name="成长性投资",
                target_ratio=Decimal("0.8"),
                cash_balance_cny=Decimal("0"),
            ),
            Basket(
                code="risk",
                name="高风险投资",
                target_ratio=Decimal("0.2"),
                cash_balance_cny=Decimal("100000"),
            ),
        ]
    )
    session.flush()
    growth = session.scalar(select(Basket).where(Basket.code == "growth"))
    risk = session.scalar(select(Basket).where(Basket.code == "risk"))
    session.add_all(
        [
            Asset(
                basket_id=growth.id,
                name="成长资产",
                units=Decimal("1"),
                unit_price=Decimal("80000"),
            ),
            Asset(
                basket_id=risk.id,
                name="风险资产",
                units=Decimal("1"),
                unit_price=Decimal("20000"),
            ),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"X-Platform-Token": TEST_PLATFORM_TOKEN}
