from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_str() -> str:
    return str(uuid.uuid4())


class RecordMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Basket(RecordMixin, Base):
    __tablename__ = "baskets"

    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(16), default="#68876f")
    icon: Mapped[str] = mapped_column(String(24), default="leaf")
    target_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))
    cash_balance_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0"))
    emergency_target_cny: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    calculation_note: Mapped[str] = mapped_column(Text, default="")

    assets: Mapped[list[Asset]] = relationship(back_populates="basket")


class Asset(RecordMixin, Base):
    __tablename__ = "assets"

    basket_id: Mapped[str] = mapped_column(ForeignKey("baskets.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    platform: Mapped[str] = mapped_column(String(120), default="")
    symbol: Mapped[str] = mapped_column(String(80), default="")
    currency: Mapped[str] = mapped_column(String(12), default="CNY")
    units: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=Decimal("0"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=Decimal("0"))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(20, 10), default=Decimal("1"))
    price_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    fx_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    update_source: Mapped[str] = mapped_column(String(40), default="manual")
    source_attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")

    basket: Mapped[Basket] = relationship(back_populates="assets")
    valuations: Mapped[list[Valuation]] = relationship(back_populates="asset")

    @property
    def value_original(self) -> Decimal:
        return self.units * self.unit_price

    @property
    def value_cny(self) -> Decimal:
        return self.value_original * self.fx_rate


class Valuation(RecordMixin, Base):
    __tablename__ = "valuations"

    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    units: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    value_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    asset: Mapped[Asset] = relationship(back_populates="valuations")


class LedgerEntry(RecordMixin, Base):
    __tablename__ = "ledger_entries"

    kind: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    basket_id: Mapped[str | None] = mapped_column(ForeignKey("baskets.id"), nullable=True)
    destination_basket_id: Mapped[str | None] = mapped_column(
        ForeignKey("baskets.id"), nullable=True
    )
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(12), default="CNY")
    units_delta: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=Decimal("0"))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(20, 10), default=Decimal("1"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    reverses_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("ledger_entries.id"), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Goal(RecordMixin, Base):
    __tablename__ = "goals"

    title: Mapped[str] = mapped_column(String(160))
    target_amount_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    description: Mapped[str] = mapped_column(Text, default="")
    reward_title: Mapped[str] = mapped_column(String(160), default="")
    reward_description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(32), default="seedling")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    achieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    achieved_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class InvestmentPlan(RecordMixin, Base):
    __tablename__ = "investment_plans"

    name: Mapped[str] = mapped_column(String(160))
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    day_of_month: Mapped[int] = mapped_column(Integer, default=10)
    allocation_mode: Mapped[str] = mapped_column(String(20), default="dynamic")
    growth_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0.8"))
    risk_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0.2"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScheduledInvestment(RecordMixin, Base):
    """A recurring, internal purchase record for one existing asset.

    It intentionally records a purchase in SuiShi only; it never places a broker order.
    """

    __tablename__ = "scheduled_investments"

    name: Mapped[str] = mapped_column(String(160))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"), index=True)
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    frequency: Mapped[str] = mapped_column(String(16))  # weekly | biweekly | monthly
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_of_day: Mapped[str] = mapped_column(String(5), default="16:00")
    anchor_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    timezone: Mapped[str] = mapped_column(String(48), default="Asia/Shanghai")
    retry_attempts: Mapped[int] = mapped_column(Integer, default=3)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_status: Mapped[str] = mapped_column(String(24), default="never")


class ScheduledInvestmentRun(RecordMixin, Base):
    __tablename__ = "scheduled_investment_runs"

    scheduled_investment_id: Mapped[str] = mapped_column(
        ForeignKey("scheduled_investments.id"), index=True
    )
    ledger_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("ledger_entries.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_source_run_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    quote_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    units_delta: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    error_message: Mapped[str] = mapped_column(Text, default="")


class PendingTask(RecordMixin, Base):
    __tablename__ = "pending_tasks"

    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PortfolioSnapshot(RecordMixin, Base):
    __tablename__ = "portfolio_snapshots"

    total_asset_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    principal_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    profit_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    basket_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    basket_principals: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=dict, nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(40), default="scheduler")


class DataSource(RecordMixin, Base):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    code: Mapped[str] = mapped_column(Text)
    function_name: Mapped[str] = mapped_column(String(80), default="fetch")
    input_mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    packages: Mapped[list[str]] = mapped_column(JSON, default=list)
    schedule_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(24), default="never")
    git_revision: Mapped[str] = mapped_column(String(64), default="")


class PlatformSettings(RecordMixin, Base):
    __tablename__ = "platform_settings"

    allocation_mode: Mapped[str] = mapped_column(String(20), default="dynamic")
    growth_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0.8"))
    risk_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0.2"))
    default_contribution_cny: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), default=Decimal("12000")
    )


class DataSourceRun(RecordMixin, Base):
    __tablename__ = "data_source_runs"

    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class NotificationRule(RecordMixin, Base):
    __tablename__ = "notification_rules"

    name: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(60), default="generic_metric")
    metric_path: Mapped[str] = mapped_column(String(160), default="portfolio.total_asset_cny")
    operator: Mapped[str] = mapped_column(String(8), default=">=")
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    webhook_url: Mapped[str] = mapped_column(Text, default="")
    headers_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    body_template: Mapped[str] = mapped_column(Text, default="")
    window_seconds: Mapped[int] = mapped_column(Integer, default=86400)
    max_deliveries: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class NotificationDelivery(RecordMixin, Base):
    __tablename__ = "notification_deliveries"

    rule_id: Mapped[str] = mapped_column(ForeignKey("notification_rules.id"), index=True)
    event_key: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(24), default="sent")
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_excerpt: Mapped[str] = mapped_column(Text, default="")
    suppressed_reason: Mapped[str] = mapped_column(String(120), default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(40))
    before_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    after_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ArchivedAuditRecord(Base):
    """Cold audit data, kept queryable without slowing the operational tables."""

    __tablename__ = "archived_audit_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    source_type: Mapped[str] = mapped_column(String(48), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
