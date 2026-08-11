from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Asset,
    AuditLog,
    Basket,
    DataSource,
    DataSourceRun,
    Goal,
    LedgerEntry,
    NotificationRule,
    NotificationDelivery,
    Valuation,
)
from app.schemas import (
    AllocationPreviewRequest,
    AssetCreate,
    AssetRead,
    AssetUpdate,
    BasketUpdate,
    DataSourceCreate,
    DataSourceExecuteRequest,
    DataSourceUpdate,
    GoalCreate,
    LedgerCreate,
    NotificationRuleCreate,
    NotificationRuleUpdate,
    PlatformSettingsUpdate,
    ValuationCreate,
)
from app.security import require_platform_token
from app.services.allocation import calculate_allocation
from app.services.datasources import execute_data_source
from app.services.portfolio import calculate_totals, dashboard_payload, save_portfolio_snapshot
from app.services.notifications import deliver_event, evaluate_rules
from app.services.versioning import save_data_source_version
from app.services.settings import get_platform_settings


router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_platform_token)])


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _validate_asset_ids(db: Session, asset_ids: list[str]) -> None:
    if not asset_ids:
        return
    found = set(
        db.scalars(
            select(Asset.id).where(Asset.id.in_(asset_ids), Asset.deleted_at.is_(None))
        )
    )
    missing = set(asset_ids) - found
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown asset ids: {', '.join(sorted(missing))}")


def _get_active(db: Session, model: Any, entity_id: str) -> Any:
    entity = db.scalar(select(model).where(model.id == entity_id, model.deleted_at.is_(None)))
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return entity


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)) -> dict[str, object]:
    return dashboard_payload(db)


@router.get("/assets", response_model=list[AssetRead])
def list_assets(db: Session = Depends(get_db)) -> list[Asset]:
    return list(
        db.scalars(select(Asset).where(Asset.deleted_at.is_(None)).order_by(Asset.created_at))
    )


@router.patch("/baskets/{basket_code}")
def update_basket(
    basket_code: str, payload: BasketUpdate, db: Session = Depends(get_db)
) -> dict[str, object]:
    basket = db.scalar(
        select(Basket).where(Basket.code == basket_code, Basket.deleted_at.is_(None))
    )
    if basket is None:
        raise HTTPException(status_code=404, detail="Basket not found")
    changes = payload.model_dump(exclude_unset=True)
    before = {key: getattr(basket, key) for key in changes}
    for key, value in changes.items():
        setattr(basket, key, value)
    db.add(
        AuditLog(
            entity_type="basket",
            entity_id=basket.id,
            action="update",
            before_json={key: str(value) if isinstance(value, Decimal) else value for key, value in before.items()},
            after_json={key: str(value) if isinstance(value, Decimal) else value for key, value in changes.items()},
        )
    )
    db.commit()
    return {
        "id": basket.id,
        "code": basket.code,
        "targetRatio": float(basket.target_ratio),
        "emergencyTargetCny": (
            float(basket.emergency_target_cny) if basket.emergency_target_cny is not None else None
        ),
        "calculationNote": basket.calculation_note,
    }


@router.post("/assets", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db)) -> Asset:
    basket = db.scalar(
        select(Basket).where(Basket.code == payload.basket_code, Basket.deleted_at.is_(None))
    )
    if basket is None:
        raise HTTPException(status_code=400, detail="Unknown basket")
    now = datetime.now(timezone.utc)
    asset = Asset(
        basket_id=basket.id,
        name=payload.name,
        platform=payload.platform,
        symbol=payload.symbol,
        currency=payload.currency.upper(),
        units=payload.units,
        unit_price=payload.unit_price,
        fx_rate=payload.fx_rate,
        source_attributes=payload.source_attributes,
        note=payload.note,
        price_updated_at=now,
        fx_updated_at=now,
    )
    db.add(asset)
    db.flush()
    db.add(
        Valuation(
            asset_id=asset.id,
            units=asset.units,
            unit_price=asset.unit_price,
            fx_rate=asset.fx_rate,
            value_cny=asset.value_cny,
            observed_at=now,
            source="opening",
        )
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.patch("/assets/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: str, payload: AssetUpdate, db: Session = Depends(get_db)) -> Asset:
    asset = _get_active(db, Asset, asset_id)
    changes = payload.model_dump(exclude_unset=True)
    basket_code = changes.pop("basket_code", None)
    tracked = [
        "basket_id", "name", "platform", "symbol", "currency", "units", "unit_price",
        "fx_rate", "source_attributes", "note",
    ]
    before = {key: getattr(asset, key) for key in tracked}
    if basket_code is not None:
        basket = db.scalar(
            select(Basket).where(Basket.code == basket_code, Basket.deleted_at.is_(None))
        )
        if basket is None:
            raise HTTPException(status_code=400, detail="Unknown basket")
        asset.basket_id = basket.id
    valuation_changed = any(key in changes for key in ("units", "unit_price", "fx_rate"))
    for key, value in changes.items():
        if key == "currency" and value is not None:
            value = value.upper()
        setattr(asset, key, value)
    now = datetime.now(timezone.utc)
    if "unit_price" in changes:
        asset.price_updated_at = now
    if "fx_rate" in changes:
        asset.fx_updated_at = now
    if valuation_changed:
        asset.update_source = "manual"
        db.add(
            Valuation(
                asset_id=asset.id,
                units=asset.units,
                unit_price=asset.unit_price,
                fx_rate=asset.fx_rate,
                value_cny=asset.value_cny,
                observed_at=now,
                source="manual-edit",
            )
        )
    db.add(
        AuditLog(
            entity_type="asset",
            entity_id=asset.id,
            action="update",
            before_json=_json_safe(before),
            after_json=_json_safe({**changes, **({"basket_code": basket_code} if basket_code else {})}),
        )
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: str, db: Session = Depends(get_db)) -> None:
    asset = _get_active(db, Asset, asset_id)
    asset.deleted_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            entity_type="asset",
            entity_id=asset.id,
            action="soft_delete",
            before_json={"deleted_at": None},
            after_json={"deleted_at": asset.deleted_at.isoformat()},
        )
    )
    db.commit()


@router.post("/assets/{asset_id}/valuations", status_code=status.HTTP_201_CREATED)
def create_valuation(
    asset_id: str, payload: ValuationCreate, db: Session = Depends(get_db)
) -> dict[str, object]:
    asset = _get_active(db, Asset, asset_id)
    observed_at = payload.observed_at or datetime.now(timezone.utc)
    asset.unit_price = payload.unit_price
    asset.price_updated_at = observed_at
    asset.update_source = payload.source
    if payload.fx_rate is not None:
        asset.fx_rate = payload.fx_rate
        asset.fx_updated_at = observed_at
    valuation = Valuation(
        asset_id=asset.id,
        units=asset.units,
        unit_price=asset.unit_price,
        fx_rate=asset.fx_rate,
        value_cny=asset.value_cny,
        observed_at=observed_at,
        source=payload.source,
        raw_payload=payload.raw_payload,
    )
    db.add(valuation)
    db.commit()
    return {"id": valuation.id, "valueCny": float(valuation.value_cny), "observedAt": observed_at}


@router.post("/ledger", status_code=status.HTTP_201_CREATED)
def create_ledger_entry(payload: LedgerCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    occurred_at = payload.occurred_at or datetime.now(timezone.utc)
    basket = _get_active(db, Basket, payload.basket_id) if payload.basket_id else None
    destination = (
        _get_active(db, Basket, payload.destination_basket_id)
        if payload.destination_basket_id
        else None
    )
    asset = _get_active(db, Asset, payload.asset_id) if payload.asset_id else None
    amount_cny = payload.amount * payload.fx_rate

    if payload.kind in {"opening", "external_deposit", "dividend", "interest"} and basket:
        basket.cash_balance_cny += amount_cny
    elif payload.kind in {"external_withdrawal", "fee", "tax"} and basket:
        basket.cash_balance_cny -= amount_cny
    elif payload.kind == "basket_transfer" and basket and destination:
        basket.cash_balance_cny -= amount_cny
        destination.cash_balance_cny += amount_cny
    elif payload.kind == "buy" and basket and asset:
        basket.cash_balance_cny -= amount_cny
        asset.units += payload.units_delta
        if payload.unit_price is not None:
            asset.unit_price = payload.unit_price
            asset.price_updated_at = occurred_at
    elif payload.kind == "sell" and basket and asset:
        basket.cash_balance_cny += amount_cny
        asset.units += payload.units_delta

    entry = LedgerEntry(
        kind=payload.kind,
        basket_id=payload.basket_id,
        destination_basket_id=payload.destination_basket_id,
        asset_id=payload.asset_id,
        amount=payload.amount,
        currency=payload.currency,
        units_delta=payload.units_delta,
        unit_price=payload.unit_price,
        fx_rate=payload.fx_rate,
        occurred_at=occurred_at,
        note=payload.note,
        reverses_entry_id=payload.reverses_entry_id,
        metadata_json=payload.metadata_json,
    )
    db.add(entry)
    db.commit()
    return {"id": entry.id, "kind": entry.kind, "occurredAt": entry.occurred_at}


@router.post("/allocations/preview")
def preview_allocation(
    payload: AllocationPreviewRequest, db: Session = Depends(get_db)
) -> dict[str, object]:
    totals = calculate_totals(db)
    basket_values = totals["basket_values"]
    basket_asset_values = totals["basket_asset_values"]
    baskets = {basket.code: basket for basket in totals["baskets"]}
    emergency = baskets["emergency"]
    return calculate_allocation(
        contribution=payload.contribution_cny,
        emergency_current=basket_values.get("emergency", Decimal("0")),
        emergency_target=emergency.emergency_target_cny or Decimal("0"),
        growth_current=basket_asset_values.get("growth", Decimal("0")),
        risk_current=basket_asset_values.get("risk", Decimal("0")),
        growth_ratio=payload.growth_ratio,
        risk_ratio=payload.risk_ratio,
        mode=payload.mode,
    )


@router.post("/snapshots", status_code=status.HTTP_201_CREATED)
def create_snapshot(db: Session = Depends(get_db)) -> dict[str, object]:
    snapshot = save_portfolio_snapshot(db, source="manual")
    evaluate_rules(db, {"portfolio": {"total_asset_cny": snapshot.total_asset_cny}})
    return {"id": snapshot.id, "observedAt": snapshot.observed_at}


@router.post("/goals", status_code=status.HTTP_201_CREATED)
def create_goal(payload: GoalCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    goal = Goal(**payload.model_dump())
    db.add(goal)
    db.commit()
    return {"id": goal.id, "title": goal.title, "targetAmountCny": float(goal.target_amount_cny)}


@router.get("/data-sources")
def list_data_sources(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    sources = db.scalars(
        select(DataSource).where(DataSource.deleted_at.is_(None)).order_by(DataSource.created_at)
    )
    return [
        {
            "id": source.id,
            "name": source.name,
            "description": source.description,
            "code": source.code,
            "functionName": source.function_name,
            "inputMapping": source.input_mapping,
            "outputMapping": source.output_mapping,
            "assetIds": source.asset_ids,
            "packages": source.packages,
            "scheduleMinutes": source.schedule_minutes,
            "enabled": source.enabled,
            "lastRunAt": source.last_run_at,
            "lastStatus": source.last_status,
            "gitRevision": source.git_revision,
        }
        for source in sources
    ]


@router.post("/data-sources", status_code=status.HTTP_201_CREATED)
def create_data_source(payload: DataSourceCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    _validate_asset_ids(db, payload.asset_ids)
    source = DataSource(**payload.model_dump())
    db.add(source)
    db.flush()
    try:
        source.git_revision = save_data_source_version(
            source.id, source.name, source.code, source.packages
        )
    except Exception as exc:
        source.git_revision = f"versioning-failed:{str(exc)[:32]}"
    db.commit()
    return {"id": source.id, "name": source.name, "gitRevision": source.git_revision}


@router.patch("/data-sources/{source_id}")
def update_data_source(
    source_id: str, payload: DataSourceUpdate, db: Session = Depends(get_db)
) -> dict[str, object]:
    source = _get_active(db, DataSource, source_id)
    changes = payload.model_dump(exclude_unset=True)
    if "asset_ids" in changes and changes["asset_ids"] is not None:
        _validate_asset_ids(db, changes["asset_ids"])
    before = {key: getattr(source, key) for key in changes}
    for key, value in changes.items():
        setattr(source, key, value)
    if any(key in changes for key in ("name", "code", "packages")):
        try:
            source.git_revision = save_data_source_version(
                source.id, source.name, source.code, source.packages
            )
        except Exception as exc:
            source.git_revision = f"versioning-failed:{str(exc)[:32]}"
    db.add(
        AuditLog(
            entity_type="data_source",
            entity_id=source.id,
            action="update",
            before_json=_json_safe(before),
            after_json=_json_safe(changes),
        )
    )
    db.commit()
    return {"id": source.id, "name": source.name, "gitRevision": source.git_revision}


@router.delete("/data-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_data_source(source_id: str, db: Session = Depends(get_db)) -> None:
    source = _get_active(db, DataSource, source_id)
    source.deleted_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            entity_type="data_source",
            entity_id=source.id,
            action="soft_delete",
            before_json={"deleted_at": None},
            after_json={"deleted_at": source.deleted_at.isoformat()},
        )
    )
    db.commit()


@router.post("/data-sources/{source_id}/execute")
def run_data_source(
    source_id: str,
    payload: DataSourceExecuteRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    source = _get_active(db, DataSource, source_id)
    run = execute_data_source(
        db, source, asset_ids=payload.asset_ids, explicit_payload=payload.payload
    )
    if run.status == "failed":
        raise HTTPException(status_code=422, detail=run.error_message)
    return {
        "id": run.id,
        "status": run.status,
        "durationMs": run.duration_ms,
        "output": run.output_payload,
    }


@router.get("/data-sources/{source_id}/runs")
def list_data_source_runs(source_id: str, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    _get_active(db, DataSource, source_id)
    runs = db.scalars(
        select(DataSourceRun)
        .where(DataSourceRun.data_source_id == source_id, DataSourceRun.deleted_at.is_(None))
        .order_by(DataSourceRun.started_at.desc())
        .limit(30)
    )
    return [
        {
            "id": run.id,
            "status": run.status,
            "startedAt": run.started_at,
            "finishedAt": run.finished_at,
            "durationMs": run.duration_ms,
            "errorMessage": run.error_message,
        }
        for run in runs
    ]


@router.get("/notification-rules")
def list_notification_rules(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rules = db.scalars(
        select(NotificationRule)
        .where(NotificationRule.deleted_at.is_(None))
        .order_by(NotificationRule.created_at)
    )
    return [
        {
            "id": rule.id,
            "name": rule.name,
            "eventType": rule.event_type,
            "metricPath": rule.metric_path,
            "operator": rule.operator,
            "threshold": float(rule.threshold) if rule.threshold is not None else None,
            "windowSeconds": rule.window_seconds,
            "maxDeliveries": rule.max_deliveries,
            "enabled": rule.enabled,
            "webhookUrl": rule.webhook_url,
            "headersJson": rule.headers_json,
            "bodyTemplate": rule.body_template,
            "headersConfigured": bool(rule.headers_json),
        }
        for rule in rules
    ]


@router.post("/notification-rules", status_code=status.HTTP_201_CREATED)
def create_notification_rule(
    payload: NotificationRuleCreate, db: Session = Depends(get_db)
) -> dict[str, object]:
    rule = NotificationRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    return {"id": rule.id, "name": rule.name}


@router.patch("/notification-rules/{rule_id}")
def update_notification_rule(
    rule_id: str, payload: NotificationRuleUpdate, db: Session = Depends(get_db)
) -> dict[str, object]:
    rule = _get_active(db, NotificationRule, rule_id)
    changes = payload.model_dump(exclude_unset=True)
    before = {key: getattr(rule, key) for key in changes}
    for key, value in changes.items():
        setattr(rule, key, value)
    db.add(
        AuditLog(
            entity_type="notification_rule",
            entity_id=rule.id,
            action="update",
            before_json=_json_safe(before),
            after_json=_json_safe(changes),
        )
    )
    db.commit()
    return {"id": rule.id, "name": rule.name, "enabled": rule.enabled}


@router.delete("/notification-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification_rule(rule_id: str, db: Session = Depends(get_db)) -> None:
    rule = _get_active(db, NotificationRule, rule_id)
    rule.deleted_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            entity_type="notification_rule",
            entity_id=rule.id,
            action="soft_delete",
            before_json={"deleted_at": None},
            after_json={"deleted_at": rule.deleted_at.isoformat()},
        )
    )
    db.commit()


@router.get("/settings")
def get_settings_view(db: Session = Depends(get_db)) -> dict[str, object]:
    settings = get_platform_settings(db)
    emergency = db.scalar(select(Basket).where(Basket.code == "emergency"))
    return {
        "allocationMode": settings.allocation_mode,
        "growthRatio": float(settings.growth_ratio),
        "riskRatio": float(settings.risk_ratio),
        "defaultContributionCny": float(settings.default_contribution_cny),
        "emergencyTargetCny": (
            float(emergency.emergency_target_cny) if emergency and emergency.emergency_target_cny else 0
        ),
        "emergencyCalculationNote": emergency.calculation_note if emergency else "",
    }


@router.patch("/settings")
def update_settings_view(
    payload: PlatformSettingsUpdate, db: Session = Depends(get_db)
) -> dict[str, object]:
    settings = get_platform_settings(db)
    changes = payload.model_dump(exclude_unset=True)
    growth = changes.get("growth_ratio", settings.growth_ratio)
    risk = changes.get("risk_ratio", settings.risk_ratio)
    if abs((growth + risk) - Decimal("1")) > Decimal("0.000001"):
        raise HTTPException(status_code=422, detail="成长与高风险比例之和必须为 100%")
    before = {key: getattr(settings, key) for key in changes}
    for key, value in changes.items():
        setattr(settings, key, value)
    growth_basket = db.scalar(select(Basket).where(Basket.code == "growth"))
    risk_basket = db.scalar(select(Basket).where(Basket.code == "risk"))
    if growth_basket:
        growth_basket.target_ratio = growth
    if risk_basket:
        risk_basket.target_ratio = risk
    db.add(
        AuditLog(
            entity_type="platform_settings",
            entity_id=settings.id,
            action="update",
            before_json=_json_safe(before),
            after_json=_json_safe(changes),
        )
    )
    db.commit()
    return get_settings_view(db)


@router.post("/notification-rules/{rule_id}/test")
def test_notification_rule(rule_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    rule = _get_active(db, NotificationRule, rule_id)
    delivery = deliver_event(
        db,
        rule,
        event_key=f"test:{rule.id}:{datetime.now(timezone.utc).isoformat()}",
        current_value=rule.threshold,
        title=f"测试：{rule.name}",
        message="这是一条由投资总览发出的 Webhook 测试消息。",
    )
    if delivery is None:
        raise HTTPException(status_code=422, detail="Webhook URL 为空或已达到推送频率上限")
    return {
        "id": delivery.id,
        "status": delivery.status,
        "responseStatus": delivery.response_status,
        "responseExcerpt": delivery.response_excerpt,
    }


@router.get("/notification-deliveries")
def list_notification_deliveries(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    deliveries = db.scalars(
        select(NotificationDelivery)
        .where(NotificationDelivery.deleted_at.is_(None))
        .order_by(NotificationDelivery.delivered_at.desc())
        .limit(100)
    )
    return [
        {
            "id": item.id,
            "ruleId": item.rule_id,
            "eventKey": item.event_key,
            "status": item.status,
            "deliveredAt": item.delivered_at,
            "responseStatus": item.response_status,
            "responseExcerpt": item.response_excerpt,
        }
        for item in deliveries
    ]
