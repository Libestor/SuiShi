from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import (
    ArchivedAuditRecord,
    Asset,
    AuditLog,
    DataSource,
    DataSourceRun,
    LedgerEntry,
    ScheduledInvestment,
    ScheduledInvestmentRun,
)
from app.services.audit import archive_expired_audit_records
from app.services.scheduled_investments import run_scheduled_investment, set_next_due


def test_scheduled_investment_fetches_quote_records_four_decimal_units_and_allows_negative_cash(
    db, monkeypatch
) -> None:
    asset = db.scalar(select(Asset).where(Asset.name == "成长资产"))
    source = DataSource(
        name="最新报价",
        code="def fetch(payload): return {'items': []}",
        input_mapping={},
        output_mapping={"unit_price": "price"},
        asset_ids=[asset.id],
        packages=[],
    )
    db.add(source)
    db.flush()
    plan = ScheduledInvestment(
        name="成长定投",
        asset_id=asset.id,
        data_source_id=source.id,
        amount_cny=Decimal("100"),
        frequency="weekly",
        weekday=0,
        time_of_day="09:30",
        retry_attempts=3,
    )
    set_next_due(plan)
    db.add(plan)
    db.commit()

    def fresh_quote(session, selected_source, **kwargs):
        asset.unit_price = Decimal("13")
        asset.fx_rate = Decimal("1")
        asset.price_updated_at = datetime.now(timezone.utc)
        source_run = DataSourceRun(
            data_source_id=selected_source.id,
            status="success",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            input_payload={"items": [{"asset_id": asset.id}]},
            output_payload={"items": [{"asset_id": asset.id, "price": 13}]},
        )
        session.add(source_run)
        session.commit()
        return source_run

    monkeypatch.setattr("app.services.scheduled_investments.execute_data_source", fresh_quote)
    result = run_scheduled_investment(db, plan)

    assert result.status == "success"
    assert result.units_delta == Decimal("7.6923")
    assert asset.units == Decimal("8.6923")
    assert asset.basket.cash_balance_cny == Decimal("-100")
    entry = db.scalar(select(LedgerEntry).where(LedgerEntry.id == result.ledger_entry_id))
    assert entry is not None
    assert entry.amount == Decimal("100")
    assert entry.metadata_json["calculation"]["unitsRoundedDownTo"] == "0.0001"


def test_archive_moves_old_operational_data_to_cold_audit_table(db) -> None:
    old = datetime.now(timezone.utc) - timedelta(days=31)
    item = AuditLog(
        entity_type="asset",
        entity_id="asset-1",
        action="update",
        before_json={"unitPrice": "1"},
        after_json={"unitPrice": "2"},
        created_at=old,
    )
    db.add(item)
    db.commit()

    assert archive_expired_audit_records(db) == 1
    assert db.scalar(select(AuditLog).where(AuditLog.id == item.id)) is None
    archived = db.scalar(select(ArchivedAuditRecord).where(ArchivedAuditRecord.source_id == item.id))
    assert archived is not None
    assert archived.source_type == "audit_log"
    assert archived.payload_json["after"] == {"unitPrice": "2"}


def test_scheduled_investment_uses_last_known_quote_after_retries(db, monkeypatch) -> None:
    asset = db.scalar(select(Asset).where(Asset.name == "成长资产"))
    source = DataSource(
        name="不稳定报价", code="def fetch(payload): return {}", input_mapping={},
        output_mapping={"unit_price": "price"}, asset_ids=[asset.id], packages=[],
    )
    db.add(source)
    db.flush()
    plan = ScheduledInvestment(
        name="降级定投", asset_id=asset.id, data_source_id=source.id,
        amount_cny=Decimal("80"), frequency="weekly", weekday=0, retry_attempts=2,
    )
    db.add(plan)
    db.commit()

    def failed_quote(session, selected_source, **kwargs):
        source_run = DataSourceRun(
            data_source_id=selected_source.id, status="failed", started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc), input_payload={}, output_payload={}, error_message="provider down",
        )
        session.add(source_run)
        session.commit()
        return source_run

    monkeypatch.setattr("app.services.scheduled_investments.execute_data_source", failed_quote)
    result = run_scheduled_investment(db, plan)

    assert result.status == "fallback"
    assert result.ledger_entry_id is not None
    assert result.error_message == "provider down"
    assert result.quote_payload["fallback"] is True


def test_scheduled_investment_api_requires_schedule_fields(client, db, auth_headers) -> None:
    asset = db.scalar(select(Asset).where(Asset.name == "成长资产"))
    source = DataSource(
        name="报价脚本",
        code="def fetch(payload): return {'items': []}",
        input_mapping={}, output_mapping={"unit_price": "price"}, asset_ids=[asset.id], packages=[],
    )
    db.add(source)
    db.commit()
    response = client.post(
        "/api/v1/scheduled-investments",
        headers=auth_headers,
        json={
            "name": "每周定投", "asset_id": asset.id, "data_source_id": source.id,
            "amount_cny": "100", "frequency": "weekly", "time_of_day": "10:00",
        },
    )
    assert response.status_code == 422


def test_scheduled_investment_api_accepts_valid_time_and_mapped_quote_source(
    client, db, auth_headers
) -> None:
    asset = db.scalar(select(Asset).where(Asset.name == "成长资产"))
    source = DataSource(
        name="报价脚本", code="def fetch(payload): return {'items': []}",
        input_mapping={"code": "symbol"}, output_mapping={"unit_price": "price"},
        asset_ids=[asset.id], packages=[],
    )
    db.add(source)
    db.commit()

    response = client.post(
        "/api/v1/scheduled-investments",
        headers=auth_headers,
        json={
            "name": "每周定投", "asset_id": asset.id, "data_source_id": source.id,
            "amount_cny": "100", "frequency": "weekly", "weekday": 0,
            "time_of_day": "09:30",
        },
    )

    assert response.status_code == 201
    assert response.json()["dataSourceId"] == source.id
    assert response.json()["timeOfDay"] == "09:30"
