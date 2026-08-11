from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import NotificationDelivery, NotificationRule


def can_deliver(db: Session, rule: NotificationRule, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=rule.window_seconds)
    count = db.scalar(
        select(func.count(NotificationDelivery.id)).where(
            NotificationDelivery.rule_id == rule.id,
            NotificationDelivery.status == "sent",
            NotificationDelivery.delivered_at >= window_start,
            NotificationDelivery.deleted_at.is_(None),
        )
    )
    return int(count or 0) < rule.max_deliveries


def _compare(current: Decimal, operator: str, threshold: Decimal) -> bool:
    return {
        ">": current > threshold,
        ">=": current >= threshold,
        "<": current < threshold,
        "<=": current <= threshold,
        "=": current == threshold,
    }.get(operator, False)


def _resolve_metric(context: dict[str, Any], path: str) -> Any:
    value: Any = context
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _render(template: str, values: dict[str, object]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def deliver_event(
    db: Session,
    rule: NotificationRule,
    *,
    event_key: str,
    current_value: Decimal | None,
    title: str,
    message: str,
    permanent_once: bool = False,
    now: datetime | None = None,
) -> NotificationDelivery | None:
    """Render and send one webhook, preserving a delivery audit record."""
    now = now or datetime.now(timezone.utc)
    if not rule.webhook_url:
        return None
    if permanent_once:
        already_sent = db.scalar(
            select(func.count(NotificationDelivery.id)).where(
                NotificationDelivery.rule_id == rule.id,
                NotificationDelivery.event_key == event_key,
                NotificationDelivery.status == "sent",
                NotificationDelivery.deleted_at.is_(None),
            )
        )
        if already_sent:
            return None
    if not can_deliver(db, rule, now=now):
        return None

    replacements = {
        "event.title": title,
        "event.message": message,
        "event.triggeredAt": now.isoformat(),
        "event.currentValue": current_value if current_value is not None else "",
        "rule.name": rule.name,
        "rule.targetValue": rule.threshold if rule.threshold is not None else "",
    }
    rendered = _render(rule.body_template or "{}", replacements)
    delivery = NotificationDelivery(
        rule_id=rule.id,
        event_key=event_key,
        status="failed",
        delivered_at=now,
    )
    db.add(delivery)
    try:
        try:
            json_body = json.loads(rendered)
        except json.JSONDecodeError:
            json_body = None
        response = httpx.post(
            rule.webhook_url,
            headers=rule.headers_json or {},
            json=json_body,
            content=None if json_body is not None else rendered.encode(),
            timeout=10,
        )
        delivery.response_status = response.status_code
        delivery.response_excerpt = response.text[:1000]
        delivery.status = "sent" if response.is_success else "failed"
    except Exception as exc:
        delivery.response_excerpt = str(exc)[:1000]
        delivery.status = "failed"
    db.commit()
    db.refresh(delivery)
    return delivery


def dispatch_event(
    db: Session,
    *,
    event_type: str,
    event_key: str,
    title: str,
    message: str,
    current_value: Decimal | None = None,
) -> list[NotificationDelivery]:
    """Deliver an application event to rules explicitly subscribing to that event type."""

    deliveries: list[NotificationDelivery] = []
    rules = db.scalars(
        select(NotificationRule).where(
            NotificationRule.deleted_at.is_(None),
            NotificationRule.enabled.is_(True),
            NotificationRule.event_type == event_type,
        )
    )
    for rule in rules:
        delivery = deliver_event(
            db,
            rule,
            event_key=event_key,
            current_value=current_value,
            title=title,
            message=message,
        )
        if delivery is not None:
            deliveries.append(delivery)
    return deliveries


def evaluate_rules(db: Session, context: dict[str, Any]) -> list[NotificationDelivery]:
    deliveries: list[NotificationDelivery] = []
    rules = db.scalars(
        select(NotificationRule).where(
            NotificationRule.deleted_at.is_(None), NotificationRule.enabled.is_(True)
        )
    )
    for rule in rules:
        raw_value = _resolve_metric(context, rule.metric_path)
        if raw_value is None or rule.threshold is None:
            continue
        current = Decimal(str(raw_value))
        if not _compare(current, rule.operator, rule.threshold):
            continue
        event_key = f"{rule.event_type}:{rule.id}:{rule.threshold}"
        delivery = deliver_event(
            db,
            rule,
            event_key=event_key,
            current_value=current,
            title=rule.name,
            message=f"{rule.metric_path} 当前为 {current}，已满足 {rule.operator} {rule.threshold}",
            permanent_once=rule.event_type == "milestone",
        )
        if delivery is not None:
            deliveries.append(delivery)
    return deliveries
