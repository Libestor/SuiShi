from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Asset, DataSource, DataSourceRun, Valuation
from app.services.notifications import dispatch_event


SCRIPT_WRITABLE_FIELDS = {"unit_price", "fx_rate"}


def _asset_field(asset: Asset, path: str) -> Any:
    if path.startswith("source_attributes."):
        return asset.source_attributes.get(path.split(".", 1)[1])
    value = getattr(asset, path)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _build_payload(source: DataSource, assets: list[Asset]) -> dict[str, Any]:
    items = []
    for asset in assets:
        item = {"asset_id": asset.id}
        for input_key, asset_path in source.input_mapping.items():
            item[input_key] = _asset_field(asset, asset_path)
        items.append(item)
    return {"items": items}


def _normalize_output(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("items"), list):
        return payload["items"]
    return [dict({"asset_id": key}, **value) for key, value in payload.items() if isinstance(value, dict)]


def execute_data_source(
    db: Session,
    source: DataSource,
    *,
    asset_ids: list[str] | None = None,
    explicit_payload: dict[str, Any] | None = None,
    notify_failure: bool = True,
) -> DataSourceRun:
    started = datetime.now(timezone.utc)
    start_perf = time.perf_counter()
    query = select(Asset).where(Asset.deleted_at.is_(None))
    selected_ids = asset_ids or source.asset_ids
    if selected_ids:
        query = query.where(Asset.id.in_(selected_ids))
    assets = list(db.scalars(query))
    input_payload = explicit_payload or _build_payload(source, assets)

    run = DataSourceRun(
        data_source_id=source.id,
        status="running",
        started_at=started,
        input_payload=input_payload,
    )
    db.add(run)
    db.flush()

    settings = get_settings()
    try:
        response = httpx.post(
            f"{settings.runner_url}/execute",
            headers={"X-Runner-Secret": settings.runner_shared_secret},
            json={
                "code": source.code,
                "function_name": source.function_name,
                "payload": input_payload,
                "packages": source.packages,
                "timeout_seconds": 45,
            },
            timeout=60,
        )
        response.raise_for_status()
        runner_result = response.json()
        output_payload = runner_result["result"]

        assets_by_id = {asset.id: asset for asset in assets}
        for item in _normalize_output(output_payload):
            asset = assets_by_id.get(str(item.get("asset_id", "")))
            if asset is None:
                continue
            custom = dict(asset.source_attributes or {})
            changed = False
            for target_field, output_key in source.output_mapping.items():
                if output_key not in item:
                    continue
                if target_field in SCRIPT_WRITABLE_FIELDS:
                    setattr(asset, target_field, Decimal(str(item[output_key])))
                    changed = True
                elif target_field.startswith("source_attributes."):
                    custom[target_field.split(".", 1)[1]] = item[output_key]
            asset.source_attributes = custom
            if changed:
                now = datetime.now(timezone.utc)
                asset.price_updated_at = now
                asset.fx_updated_at = now
                asset.update_source = f"data-source:{source.name}"
                db.add(
                    Valuation(
                        asset_id=asset.id,
                        units=asset.units,
                        unit_price=asset.unit_price,
                        fx_rate=asset.fx_rate,
                        value_cny=asset.value_cny,
                        observed_at=now,
                        source=f"data-source:{source.id}",
                        raw_payload=item,
                    )
                )

        finished = datetime.now(timezone.utc)
        run.status = "success"
        run.output_payload = output_payload
        run.finished_at = finished
        run.duration_ms = int((time.perf_counter() - start_perf) * 1000)
        source.last_status = "success"
        source.last_run_at = finished
        source.next_run_at = finished + timedelta(minutes=source.schedule_minutes)
    except Exception as exc:
        finished = datetime.now(timezone.utc)
        run.status = "failed"
        run.error_message = str(exc)[:4000]
        run.finished_at = finished
        run.duration_ms = int((time.perf_counter() - start_perf) * 1000)
        source.last_status = "failed"
        source.last_run_at = finished
        source.next_run_at = finished + timedelta(minutes=source.schedule_minutes)

    db.commit()
    db.refresh(run)
    if run.status == "failed" and notify_failure:
        dispatch_event(
            db,
            event_type="data_source_failed",
            event_key=f"data-source:{source.id}:{run.id}",
            title=f"数据源拉取失败：{source.name}",
            message=f"数据源“{source.name}”执行失败：{run.error_message[:500]}",
        )
    return run
