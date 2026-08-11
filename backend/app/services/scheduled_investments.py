from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    AuditLog,
    DataSource,
    LedgerEntry,
    ScheduledInvestment,
    ScheduledInvestmentRun,
)
from app.services.audit import json_safe
from app.services.datasources import execute_data_source
from app.services.notifications import dispatch_event


def _local_due(plan: ScheduledInvestment, moment: datetime) -> datetime:
    tz = ZoneInfo(plan.timezone or "Asia/Shanghai")
    local_now = moment.astimezone(tz)
    hour, minute = (int(part) for part in plan.time_of_day.split(":"))
    if plan.frequency == "monthly":
        target_day = min(plan.day_of_month or 1, calendar.monthrange(local_now.year, local_now.month)[1])
        candidate = datetime.combine(local_now.date().replace(day=target_day), time(hour, minute), tz)
        if candidate <= local_now:
            year = local_now.year + (1 if local_now.month == 12 else 0)
            month = 1 if local_now.month == 12 else local_now.month + 1
            target_day = min(plan.day_of_month or 1, calendar.monthrange(year, month)[1])
            candidate = datetime(year, month, target_day, hour, minute, tzinfo=tz)
        return candidate.astimezone(timezone.utc)

    candidate_date = local_now.date()
    weekday = plan.weekday if plan.weekday is not None else 0
    candidate_date += timedelta(days=(weekday - candidate_date.weekday()) % 7)
    candidate = datetime.combine(candidate_date, time(hour, minute), tz)
    if candidate <= local_now:
        candidate += timedelta(days=7)
    if plan.frequency == "biweekly":
        anchor = plan.anchor_date or local_now.date()
        while ((candidate.date() - anchor).days // 7) % 2:
            candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc)


def set_next_due(plan: ScheduledInvestment, *, after: datetime | None = None) -> None:
    plan.next_run_at = _local_due(plan, after or datetime.now(timezone.utc))


def run_scheduled_investment(
    db: Session,
    plan: ScheduledInvestment,
    *,
    scheduled_for: datetime | None = None,
) -> ScheduledInvestmentRun:
    """Fetch a fresh quote and record the resulting internal purchase.

    A quote is never inferred from an old asset value: a successful source execution must
    update the asset price during this run before a purchase can be recorded.
    """

    started = datetime.now(timezone.utc)
    scheduled_for = scheduled_for or started
    asset = db.scalar(select(Asset).where(Asset.id == plan.asset_id, Asset.deleted_at.is_(None)))
    source = db.scalar(
        select(DataSource).where(DataSource.id == plan.data_source_id, DataSource.deleted_at.is_(None))
    )
    run = ScheduledInvestmentRun(
        scheduled_investment_id=plan.id,
        status="running",
        scheduled_for=scheduled_for,
        started_at=started,
        amount_cny=plan.amount_cny,
    )
    db.add(run)
    db.flush()
    source_run_ids: list[str] = []
    last_error = ""
    using_fallback_quote = False

    if asset is None or source is None:
        last_error = "定投关联的资产或报价数据源不存在。"
    else:
        fresh_quote_received = False
        for _ in range(plan.retry_attempts):
            source_run = execute_data_source(
                db, source, asset_ids=[asset.id], notify_failure=False
            )
            source_run_ids.append(source_run.id)
            db.refresh(asset)
            price_updated_at = asset.price_updated_at
            if price_updated_at.tzinfo is None:
                price_updated_at = price_updated_at.replace(tzinfo=timezone.utc)
            if source_run.status == "success" and price_updated_at >= started and asset.unit_price > 0:
                run.quote_payload = source_run.output_payload
                fresh_quote_received = True
                break
            last_error = source_run.error_message or "数据源没有返回该资产的有效最新报价。"
        if not fresh_quote_received:
            if asset.unit_price > 0 and asset.fx_rate > 0:
                using_fallback_quote = True
                run.quote_payload = {
                    "fallback": True,
                    "reason": last_error,
                    "lastKnownUnitPrice": str(asset.unit_price),
                    "lastKnownFxRate": str(asset.fx_rate),
                    "lastPriceUpdatedAt": price_updated_at.isoformat(),
                }
            else:
                asset = None

    if asset is None:
        finished = datetime.now(timezone.utc)
        run.status = "failed"
        run.finished_at = finished
        run.data_source_run_ids = source_run_ids
        run.error_message = last_error or "未取得有效报价。"
        plan.last_status = "failed"
        plan.last_run_at = finished
        set_next_due(plan, after=finished)
        db.add(
            AuditLog(
                entity_type="scheduled_investment_run",
                entity_id=run.id,
                action="quote_failed",
                after_json=json_safe(
                    {"planId": plan.id, "sourceRunIds": source_run_ids, "error": run.error_message}
                ),
            )
        )
        db.commit()
        dispatch_event(
            db,
            event_type="scheduled_investment_quote_failed",
            event_key=f"scheduled-investment:{plan.id}:{run.id}",
            title=f"定投报价拉取失败：{plan.name}",
            message=f"已重试 {plan.retry_attempts} 次，未能为“{plan.name}”取得最新报价：{run.error_message}",
        )
        return run

    denominator = asset.unit_price * asset.fx_rate
    units_delta = (plan.amount_cny / denominator).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
    if units_delta <= 0:
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        run.data_source_run_ids = source_run_ids
        run.error_message = "定投金额不足以按当前报价买入 0.0001 份。"
        plan.last_status = "failed"
        plan.last_run_at = run.finished_at
        set_next_due(plan, after=run.finished_at)
        db.commit()
        dispatch_event(
            db,
            event_type="scheduled_investment_quote_failed",
            event_key=f"scheduled-investment:{plan.id}:{run.id}",
            title=f"定投份额计算失败：{plan.name}",
            message=run.error_message,
        )
        return run

    # Keep the ledger amount in CNY so the basket cash always decreases by the fixed plan amount.
    asset.basket.cash_balance_cny -= plan.amount_cny
    asset.units += units_delta
    finished = datetime.now(timezone.utc)
    entry = LedgerEntry(
        kind="buy",
        basket_id=asset.basket_id,
        asset_id=asset.id,
        amount=plan.amount_cny,
        currency="CNY",
        units_delta=units_delta,
        unit_price=asset.unit_price,
        fx_rate=Decimal("1"),
        occurred_at=finished,
        note=f"自动定投：{plan.name}",
        metadata_json=json_safe(
            {
                "scheduledInvestmentId": plan.id,
                "scheduledInvestmentRunId": run.id,
                "dataSourceRunIds": source_run_ids,
                "quote": {
                    "unitPrice": asset.unit_price,
                    "currency": asset.currency,
                    "fxRate": asset.fx_rate,
                    "priceUpdatedAt": asset.price_updated_at,
                    "fallback": using_fallback_quote,
                    "fallbackReason": last_error if using_fallback_quote else "",
                },
                "calculation": {
                    "amountCny": plan.amount_cny,
                    "formula": "amount_cny / (unit_price * fx_rate)",
                    "unitsRoundedDownTo": "0.0001",
                    "unitsDelta": units_delta,
                },
            }
        ),
    )
    db.add(entry)
    db.flush()
    run.status = "fallback" if using_fallback_quote else "success"
    run.finished_at = finished
    run.data_source_run_ids = source_run_ids
    run.unit_price = asset.unit_price
    run.fx_rate = asset.fx_rate
    run.units_delta = units_delta
    run.ledger_entry_id = entry.id
    run.error_message = last_error if using_fallback_quote else ""
    plan.last_status = run.status
    plan.last_run_at = finished
    set_next_due(plan, after=finished)
    db.add(
        AuditLog(
            entity_type="scheduled_investment_run",
            entity_id=run.id,
            action="buy_recorded_with_fallback" if using_fallback_quote else "buy_recorded",
            after_json=json_safe(
                {
                    "planId": plan.id,
                    "ledgerEntryId": entry.id,
                    "dataSourceRunIds": source_run_ids,
                    "quote": run.quote_payload,
                    "unitPrice": asset.unit_price,
                    "fxRate": asset.fx_rate,
                    "unitsDelta": units_delta,
                    "amountCny": plan.amount_cny,
                    "quoteFallback": using_fallback_quote,
                    "fallbackReason": last_error if using_fallback_quote else "",
                    "cashBalanceAfter": asset.basket.cash_balance_cny,
                }
            ),
        )
    )
    db.commit()
    if using_fallback_quote:
        dispatch_event(
            db,
            event_type="scheduled_investment_quote_failed",
            event_key=f"scheduled-investment-fallback:{plan.id}:{run.id}",
            title=f"定投使用最近报价：{plan.name}",
            message=(
                f"最新报价已重试 {plan.retry_attempts} 次但未成功；本次按最近有效报价 "
                f"{asset.unit_price} {asset.currency} 记账。原因：{last_error}"
            ),
        )
    if asset.basket.cash_balance_cny < 0:
        dispatch_event(
            db,
            event_type="scheduled_investment_cash_negative",
            event_key=f"scheduled-investment-negative-cash:{plan.id}:{run.id}",
            title=f"待购买金额为负：{plan.name}",
            message=(
                f"“{asset.basket.name}”完成自动定投 {plan.amount_cny} 元后，"
                f"待购买金额为 {asset.basket.cash_balance_cny} 元，请人工补记资金。"
            ),
            current_value=asset.basket.cash_balance_cny,
        )
    return run
