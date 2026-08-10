from datetime import datetime, timedelta, timezone

from app.models import NotificationDelivery, NotificationRule
from decimal import Decimal

from app.services.notifications import can_deliver, deliver_event, evaluate_rules


def test_delivery_limit_uses_rolling_window(db) -> None:
    now = datetime.now(timezone.utc)
    rule = NotificationRule(
        name="测试规则",
        window_seconds=3600,
        max_deliveries=2,
        body_template="{}",
    )
    db.add(rule)
    db.flush()
    db.add_all(
        [
            NotificationDelivery(
                rule_id=rule.id,
                event_key="one",
                status="sent",
                delivered_at=now - timedelta(minutes=30),
            ),
            NotificationDelivery(
                rule_id=rule.id,
                event_key="two",
                status="sent",
                delivered_at=now - timedelta(minutes=10),
            ),
        ]
    )
    db.commit()

    assert can_deliver(db, rule, now=now) is False
    assert can_deliver(db, rule, now=now + timedelta(hours=2)) is True


def test_webhook_renders_template_and_records_delivery(db, monkeypatch) -> None:
    class Response:
        status_code = 202
        text = "accepted"
        is_success = True

    sent = {}

    def fake_post(url, **kwargs):
        sent["url"] = url
        sent["json"] = kwargs["json"]
        sent["headers"] = kwargs["headers"]
        return Response()

    monkeypatch.setattr("app.services.notifications.httpx.post", fake_post)
    rule = NotificationRule(
        name="达到目标",
        event_type="milestone",
        metric_path="portfolio.total_asset_cny",
        operator=">=",
        threshold=Decimal("300000"),
        webhook_url="https://notify.example.test/hook",
        headers_json={"Authorization": "Bearer local"},
        body_template='{"title":"{{event.title}}","value":"{{event.currentValue}}"}',
        window_seconds=86400,
        max_deliveries=1,
    )
    db.add(rule)
    db.commit()

    deliveries = evaluate_rules(db, {"portfolio": {"total_asset_cny": Decimal("310000")}})
    assert len(deliveries) == 1
    assert deliveries[0].status == "sent"
    assert sent == {
        "url": "https://notify.example.test/hook",
        "json": {"title": "达到目标", "value": "310000"},
        "headers": {"Authorization": "Bearer local"},
    }
    assert evaluate_rules(db, {"portfolio": {"total_asset_cny": Decimal("320000")}}) == []


def test_delivery_failure_is_audited(db, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr("app.services.notifications.httpx.post", fail)
    rule = NotificationRule(
        name="测试失败",
        webhook_url="https://notify.example.test/hook",
        body_template="{}",
        max_deliveries=2,
    )
    db.add(rule)
    db.commit()
    delivery = deliver_event(
        db,
        rule,
        event_key="failure-test",
        current_value=None,
        title="测试",
        message="测试失败日志",
    )
    assert delivery is not None
    assert delivery.status == "failed"
    assert "network unavailable" in delivery.response_excerpt
