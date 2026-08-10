from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Basket, PlatformSettings


def get_platform_settings(db: Session) -> PlatformSettings:
    settings = db.scalar(
        select(PlatformSettings).where(PlatformSettings.deleted_at.is_(None)).limit(1)
    )
    if settings is not None:
        return settings

    growth = db.scalar(select(Basket).where(Basket.code == "growth"))
    risk = db.scalar(select(Basket).where(Basket.code == "risk"))
    settings = PlatformSettings(
        allocation_mode="dynamic",
        growth_ratio=growth.target_ratio if growth else Decimal("0.8"),
        risk_ratio=risk.target_ratio if risk else Decimal("0.2"),
        default_contribution_cny=Decimal("12000"),
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings
