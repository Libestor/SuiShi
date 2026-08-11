from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ArchivedAuditRecord,
    AuditLog,
    DataSourceRun,
    NotificationDelivery,
    ScheduledInvestmentRun,
)


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def _archive(db: Session, source_type: str, source: Any, occurred_at: datetime, payload: dict[str, Any]) -> None:
    db.add(
        ArchivedAuditRecord(
            source_type=source_type,
            source_id=source.id,
            occurred_at=occurred_at,
            payload_json=json_safe(payload),
        )
    )
    db.delete(source)


def archive_expired_audit_records(db: Session, *, now: datetime | None = None) -> int:
    """Move verbose operational history to the cold, queryable archive after 30 days."""

    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=30)
    archived = 0
    for item in db.scalars(select(AuditLog).where(AuditLog.created_at < cutoff)):
        _archive(
            db,
            "audit_log",
            item,
            item.created_at,
            {
                "entityType": item.entity_type,
                "entityId": item.entity_id,
                "action": item.action,
                "before": item.before_json,
                "after": item.after_json,
            },
        )
        archived += 1
    for item in db.scalars(select(DataSourceRun).where(DataSourceRun.started_at < cutoff)):
        _archive(
            db,
            "data_source_run",
            item,
            item.started_at,
            {
                "dataSourceId": item.data_source_id,
                "status": item.status,
                "startedAt": item.started_at,
                "finishedAt": item.finished_at,
                "input": item.input_payload,
                "output": item.output_payload,
                "error": item.error_message,
                "durationMs": item.duration_ms,
            },
        )
        archived += 1
    for item in db.scalars(select(ScheduledInvestmentRun).where(ScheduledInvestmentRun.started_at < cutoff)):
        _archive(
            db,
            "scheduled_investment_run",
            item,
            item.started_at,
            {
                "scheduledInvestmentId": item.scheduled_investment_id,
                "ledgerEntryId": item.ledger_entry_id,
                "status": item.status,
                "scheduledFor": item.scheduled_for,
                "dataSourceRunIds": item.data_source_run_ids,
                "quote": item.quote_payload,
                "unitPrice": item.unit_price,
                "fxRate": item.fx_rate,
                "unitsDelta": item.units_delta,
                "amountCny": item.amount_cny,
                "error": item.error_message,
            },
        )
        archived += 1
    for item in db.scalars(select(NotificationDelivery).where(NotificationDelivery.delivered_at < cutoff)):
        _archive(
            db,
            "notification_delivery",
            item,
            item.delivered_at,
            {
                "ruleId": item.rule_id,
                "eventKey": item.event_key,
                "status": item.status,
                "responseStatus": item.response_status,
                "responseExcerpt": item.response_excerpt,
                "suppressedReason": item.suppressed_reason,
            },
        )
        archived += 1
    db.commit()
    return archived
