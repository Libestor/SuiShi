from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import func, select

from app import seed as seed_module
from app.database import Base
from app.models import Asset, Basket, LedgerEntry, PlatformSettings, PortfolioSnapshot
from conftest import TestingSession, engine


def test_fresh_install_seeds_only_empty_fixed_baskets(monkeypatch) -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(seed_module, "SessionLocal", TestingSession)
    monkeypatch.setattr(seed_module, "get_settings", lambda: SimpleNamespace(seed_demo_data=False))

    seed_module.seed()

    with TestingSession() as db:
        assert db.scalar(select(func.count(Basket.id))) == 3
        assert db.scalar(select(func.count(Asset.id))) == 0
        assert db.scalar(select(func.count(LedgerEntry.id))) == 0
        assert db.scalar(select(func.count(PortfolioSnapshot.id))) == 0
        settings = db.scalar(select(PlatformSettings))
        assert settings is not None
        assert settings.default_contribution_cny == 12000
