from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Asset, Basket, Goal, LedgerEntry, PortfolioSnapshot, Valuation
from app.services.freshness import freshness_label
from app.services.settings import get_platform_settings


ZERO = Decimal("0")
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


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
    basket_ids = {basket.id: basket.code for basket in baskets}
    basket_principals = {basket.code: ZERO for basket in baskets}
    entries = db.scalars(
        select(LedgerEntry).where(
            LedgerEntry.deleted_at.is_(None), LedgerEntry.status == "confirmed"
        )
    )
    principal = ZERO
    for entry in entries:
        principal_delta = ZERO
        if entry.kind in {"opening", "asset_opening", "external_deposit"}:
            principal_delta = entry.amount * entry.fx_rate
        elif entry.kind == "external_withdrawal":
            principal_delta = -(entry.amount * entry.fx_rate)
        principal += principal_delta
        basket_code = basket_ids.get(entry.basket_id or "")
        if basket_code:
            basket_principals[basket_code] += principal_delta

    return {
        "total": total,
        "principal": principal,
        "profit": total - principal,
        "basket_values": basket_values,
        "basket_principals": basket_principals,
        "basket_asset_values": basket_asset_values,
        "baskets": baskets,
        "assets": assets,
    }


def save_portfolio_snapshot(db: Session, source: str = "manual") -> PortfolioSnapshot:
    totals = calculate_totals(db)
    observed_at = datetime.now(timezone.utc)
    basket_values = {key: float(value) for key, value in totals["basket_values"].items()}
    basket_principals = {
        key: float(value) for key, value in totals["basket_principals"].items()
    }

    snapshot = PortfolioSnapshot(
        total_asset_cny=totals["total"],
        principal_cny=totals["principal"],
        profit_cny=totals["profit"],
        basket_values=basket_values,
        basket_principals=basket_principals,
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
                "basketPrincipals": basket_principals,
            }

    db.commit()
    db.refresh(snapshot)
    return snapshot


def dashboard_payload(db: Session) -> dict[str, object]:
    totals = calculate_totals(db)
    platform_settings = get_platform_settings(db)
    total = totals["total"]
    basket_values: dict[str, Decimal] = totals["basket_values"]
    basket_principals: dict[str, Decimal] = totals["basket_principals"]
    basket_asset_values: dict[str, Decimal] = totals["basket_asset_values"]
    baskets: list[Basket] = totals["baskets"]

    basket_payload = []
    for basket in baskets:
        value = basket_values.get(basket.code, ZERO)
        principal = basket_principals.get(basket.code, ZERO)
        profit = value - principal
        active_assets = [asset for asset in basket.assets if asset.deleted_at is None]
        oldest_price_at = min(
            (asset.price_updated_at for asset in active_assets), default=None
        )
        stale_asset_count = sum(
            1 for asset in active_assets if freshness_label(asset.price_updated_at)[1] >= 24
        )
        basket_payload.append(
            {
                "id": basket.id,
                "code": basket.code,
                "name": basket.name,
                "description": basket.description,
                "color": basket.color,
                "icon": basket.icon,
                "valueCny": float(value),
                "principalCny": float(principal),
                "profitCny": float(profit),
                "profitRatio": float(profit / principal * 100) if principal else 0,
                "investedValueCny": float(basket_asset_values.get(basket.code, ZERO)),
                "ratio": float(value / total * 100) if total else 0,
                "targetRatio": float(basket.target_ratio * 100),
                "cashBalanceCny": float(basket.cash_balance_cny),
                "oldestPriceUpdatedAt": (
                    oldest_price_at.isoformat() if oldest_price_at else None
                ),
                "staleAssetCount": stale_asset_count,
                "emergencyTargetCny": (
                    float(basket.emergency_target_cny) if basket.emergency_target_cny else None
                ),
                "calculationNote": basket.calculation_note,
            }
        )

    # 配置罗盘只比较成长与高风险两个篮子；两者的待投资资产同样属于可配置资金，
    # 因此纳入比例，应急储备金始终排除。
    growth = basket_values.get("growth", ZERO)
    risk = basket_values.get("risk", ZERO)
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
            .order_by(PortfolioSnapshot.observed_at.asc())
        )
    )
    monthly_snapshots: dict[str, PortfolioSnapshot] = {}
    for snapshot in snapshots:
        observed_at = snapshot.observed_at
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        month_key = observed_at.astimezone(SHANGHAI_TZ).strftime("%Y-%m")
        monthly_snapshots[month_key] = snapshot

    curve = []
    previous_total: Decimal | None = None
    previous_principal: Decimal | None = None
    previous_baskets: dict[str, dict[str, float]] = {}
    for month_key, row in monthly_snapshots.items():
        point_baskets: dict[str, dict[str, float]] = {}
        row_basket_values = row.basket_values or {}
        row_basket_principals = row.basket_principals or {}
        for basket_code, raw_value in row_basket_values.items():
            if basket_code not in row_basket_principals:
                continue
            value = Decimal(str(raw_value))
            principal = Decimal(str(row_basket_principals[basket_code]))
            profit = value - principal
            previous = previous_baskets.get(basket_code)
            point_baskets[basket_code] = {
                "total": float(value),
                "principal": float(principal),
                "profit": float(profit),
                "profitRatio": float(profit / principal * 100) if principal else 0,
                "netContribution": (
                    float(principal - Decimal(str(previous["principal"])))
                    if previous
                    else 0
                ),
                "valueChange": (
                    float(value - Decimal(str(previous["total"]))) if previous else 0
                ),
            }
        curve.append(
            {
                "month": month_key,
                "at": row.observed_at.isoformat(),
                "total": float(row.total_asset_cny),
                "principal": float(row.principal_cny),
                "profit": float(row.profit_cny),
                "profitRatio": (
                    float(row.profit_cny / row.principal_cny * 100)
                    if row.principal_cny
                    else 0
                ),
                "netContribution": (
                    float(row.principal_cny - previous_principal)
                    if previous_principal is not None
                    else 0
                ),
                "valueChange": (
                    float(row.total_asset_cny - previous_total)
                    if previous_total is not None
                    else 0
                ),
                "baskets": point_baskets,
            }
        )
        previous_total = row.total_asset_cny
        previous_principal = row.principal_cny
        previous_baskets = point_baskets

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
