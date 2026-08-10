from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Asset, Basket, Goal, LedgerEntry, PortfolioSnapshot, Valuation
from app.services.freshness import freshness_label
from app.services.settings import get_platform_settings


ZERO = Decimal("0")


def active_baskets(db: Session) -> list[Basket]:
    return list(
        db.scalars(
            select(Basket)
            .where(Basket.deleted_at.is_(None))
            .options(selectinload(Basket.assets))
            .order_by(Basket.code)
        )
    )


def calculate_totals(db: Session) -> dict[str, object]:
    baskets = active_baskets(db)
    basket_values: dict[str, Decimal] = {}
    basket_asset_values: dict[str, Decimal] = {}
    assets: list[dict[str, object]] = []

    for basket in baskets:
        asset_total = ZERO
        for asset in basket.assets:
            if asset.deleted_at is not None:
                continue
            value = asset.value_cny
            asset_total += value
            label, age_hours = freshness_label(asset.price_updated_at)
            assets.append(
                {
                    "id": asset.id,
                    "basketCode": basket.code,
                    "basketName": basket.name,
                    "name": asset.name,
                    "platform": asset.platform,
                    "symbol": asset.symbol,
                    "currency": asset.currency,
                    "units": float(asset.units),
                    "unitPrice": float(asset.unit_price),
                    "fxRate": float(asset.fx_rate),
                    "valueCny": float(value),
                    "updatedAt": asset.price_updated_at.isoformat(),
                    "freshnessLabel": label,
                    "ageHours": age_hours,
                    "source": asset.update_source,
                    "sourceAttributes": asset.source_attributes,
                    "note": asset.note,
                }
            )
        basket_asset_values[basket.code] = asset_total
        basket_values[basket.code] = asset_total + basket.cash_balance_cny

    total = sum(basket_values.values(), ZERO)
    entries = db.scalars(
        select(LedgerEntry).where(
            LedgerEntry.deleted_at.is_(None), LedgerEntry.status == "confirmed"
        )
    )
    principal = ZERO
    for entry in entries:
        if entry.kind in {"opening", "external_deposit"}:
            principal += entry.amount * entry.fx_rate
        elif entry.kind == "external_withdrawal":
            principal -= entry.amount * entry.fx_rate

    return {
        "total": total,
        "principal": principal,
        "profit": total - principal,
        "basket_values": basket_values,
        "basket_asset_values": basket_asset_values,
        "baskets": baskets,
        "assets": assets,
    }


def save_portfolio_snapshot(db: Session, source: str = "manual") -> PortfolioSnapshot:
    totals = calculate_totals(db)
    observed_at = datetime.now(timezone.utc)
    basket_values = {key: float(value) for key, value in totals["basket_values"].items()}

    snapshot = PortfolioSnapshot(
        total_asset_cny=totals["total"],
        principal_cny=totals["principal"],
        profit_cny=totals["profit"],
        basket_values=basket_values,
        observed_at=observed_at,
        source=source,
    )
    db.add(snapshot)

    assets = db.scalars(select(Asset).where(Asset.deleted_at.is_(None)))
    for asset in assets:
        db.add(
            Valuation(
                asset_id=asset.id,
                units=asset.units,
                unit_price=asset.unit_price,
                fx_rate=asset.fx_rate,
                value_cny=asset.value_cny,
                observed_at=observed_at,
                source=source,
                raw_payload={},
            )
        )

    active_goals = db.scalars(
        select(Goal).where(Goal.deleted_at.is_(None), Goal.achieved_at.is_(None))
    )
    for goal in active_goals:
        if totals["total"] >= goal.target_amount_cny:
            goal.achieved_at = observed_at
            goal.achieved_snapshot = {
                "totalAssetCny": float(totals["total"]),
                "principalCny": float(totals["principal"]),
                "basketValues": basket_values,
            }

    db.commit()
    db.refresh(snapshot)
    return snapshot


def dashboard_payload(db: Session) -> dict[str, object]:
    totals = calculate_totals(db)
    platform_settings = get_platform_settings(db)
    total = totals["total"]
    basket_values: dict[str, Decimal] = totals["basket_values"]
    basket_asset_values: dict[str, Decimal] = totals["basket_asset_values"]
    baskets: list[Basket] = totals["baskets"]

    basket_payload = []
    for basket in baskets:
        value = basket_values.get(basket.code, ZERO)
        basket_payload.append(
            {
                "id": basket.id,
                "code": basket.code,
                "name": basket.name,
                "description": basket.description,
                "color": basket.color,
                "icon": basket.icon,
                "valueCny": float(value),
                "investedValueCny": float(basket_asset_values.get(basket.code, ZERO)),
                "ratio": float(value / total * 100) if total else 0,
                "targetRatio": float(basket.target_ratio * 100),
                "cashBalanceCny": float(basket.cash_balance_cny),
                "emergencyTargetCny": (
                    float(basket.emergency_target_cny) if basket.emergency_target_cny else None
                ),
                "calculationNote": basket.calculation_note,
            }
        )

    # 待购买现金属于篮子总资产，但不参与成长/高风险的风险比例。
    growth = basket_asset_values.get("growth", ZERO)
    risk = basket_asset_values.get("risk", ZERO)
    investment_total = growth + risk
    allocation = {
        "mode": platform_settings.allocation_mode,
        "defaultContributionCny": float(platform_settings.default_contribution_cny),
        "growthRatio": float(growth / investment_total * 100) if investment_total else 0,
        "riskRatio": float(risk / investment_total * 100) if investment_total else 0,
        "targetGrowthRatio": next(
            (float(b.target_ratio * 100) for b in baskets if b.code == "growth"), 80
        ),
        "targetRiskRatio": next(
            (float(b.target_ratio * 100) for b in baskets if b.code == "risk"), 20
        ),
    }

    snapshots = list(
        db.scalars(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.deleted_at.is_(None))
            .order_by(PortfolioSnapshot.observed_at.desc())
            .limit(48)
        )
    )
    snapshots.reverse()
    curve = [
        {
            "at": row.observed_at.isoformat(),
            "total": float(row.total_asset_cny),
            "principal": float(row.principal_cny),
            "profit": float(row.profit_cny),
        }
        for row in snapshots
    ]

    goals = list(
        db.scalars(
            select(Goal).where(Goal.deleted_at.is_(None)).order_by(Goal.created_at.desc())
        )
    )
    goal_payload = [
        {
            "id": goal.id,
            "title": goal.title,
            "targetAmountCny": float(goal.target_amount_cny),
            "progress": min(100, float(total / goal.target_amount_cny * 100)),
            "remainingCny": float(max(ZERO, goal.target_amount_cny - total)),
            "rewardTitle": goal.reward_title,
            "rewardDescription": goal.reward_description,
            "targetDate": goal.target_date.isoformat() if goal.target_date else None,
            "achievedAt": goal.achieved_at.isoformat() if goal.achieved_at else None,
        }
        for goal in goals
    ]

    return {
        "asOf": datetime.now(timezone.utc).isoformat(),
        "totalAssetCny": float(total),
        "principalCny": float(totals["principal"]),
        "profitCny": float(totals["profit"]),
        "profitRatio": (
            float(totals["profit"] / totals["principal"] * 100)
            if totals["principal"]
            else 0
        ),
        "baskets": basket_payload,
        "allocation": allocation,
        "assets": totals["assets"],
        "curve": curve,
        "goals": goal_payload,
    }
