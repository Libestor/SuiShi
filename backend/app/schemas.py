from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AssetCreate(BaseModel):
    basket_code: Literal["emergency", "growth", "risk"]
    name: str = Field(min_length=1, max_length=160)
    platform: str = Field(default="", max_length=120)
    symbol: str = Field(default="", max_length=80)
    currency: str = Field(default="CNY", min_length=3, max_length=12)
    units: Decimal = Field(ge=0)
    unit_price: Decimal = Field(ge=0)
    fx_rate: Decimal = Field(default=Decimal("1"), gt=0)
    source_attributes: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class AssetUpdate(BaseModel):
    basket_code: Literal["emergency", "growth", "risk"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    platform: str | None = None
    symbol: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=12)
    units: Decimal | None = Field(default=None, ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    fx_rate: Decimal | None = Field(default=None, gt=0)
    source_attributes: dict[str, Any] | None = None
    note: str | None = None


class BasketUpdate(BaseModel):
    target_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    emergency_target_cny: Decimal | None = Field(default=None, ge=0)
    calculation_note: str | None = None


class AssetRead(ORMModel):
    id: str
    basket_id: str
    name: str
    platform: str
    symbol: str
    currency: str
    units: Decimal
    unit_price: Decimal
    fx_rate: Decimal
    price_updated_at: datetime
    fx_updated_at: datetime
    update_source: str
    source_attributes: dict[str, Any]
    note: str
    created_at: datetime
    updated_at: datetime
    value_original: Decimal
    value_cny: Decimal


class ValuationCreate(BaseModel):
    unit_price: Decimal = Field(ge=0)
    fx_rate: Decimal | None = Field(default=None, gt=0)
    observed_at: datetime | None = None
    source: str = Field(default="manual", max_length=40)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class AssetSaleCreate(BaseModel):
    """Record a partial sale or full liquidation into the basket's pending cash."""

    units: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    fx_rate: Decimal | None = Field(default=None, gt=0)
    occurred_at: datetime | None = None
    note: str = ""


class LedgerCreate(BaseModel):
    kind: Literal[
        "opening",
        "asset_opening",
        "external_deposit",
        "external_withdrawal",
        "basket_transfer",
        "buy",
        "sell",
        "dividend",
        "interest",
        "fee",
        "tax",
        "correction",
    ]
    basket_id: str | None = None
    destination_basket_id: str | None = None
    asset_id: str | None = None
    amount: Decimal = Decimal("0")
    currency: str = "CNY"
    units_delta: Decimal = Decimal("0")
    unit_price: Decimal | None = None
    fx_rate: Decimal = Decimal("1")
    occurred_at: datetime | None = None
    note: str = ""
    reverses_entry_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class LedgerUpdate(BaseModel):
    amount: Decimal | None = None
    units_delta: Decimal | None = None
    unit_price: Decimal | None = Field(default=None, ge=0)
    fx_rate: Decimal | None = Field(default=None, gt=0)
    occurred_at: datetime | None = None
    note: str | None = None


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    target_amount_cny: Decimal = Field(gt=0)
    description: str = ""
    reward_title: str = ""
    reward_description: str = ""
    icon: str = "seedling"
    target_date: date | None = None


class AllocationPreviewRequest(BaseModel):
    contribution_cny: Decimal = Field(gt=0)
    mode: Literal["dynamic", "fixed"] = "dynamic"
    growth_ratio: Decimal = Decimal("0.8")
    risk_ratio: Decimal = Decimal("0.2")

    @field_validator("risk_ratio")
    @classmethod
    def ratios_sum_to_one(cls, value: Decimal, info: Any) -> Decimal:
        growth = info.data.get("growth_ratio", Decimal("0"))
        if abs((growth + value) - Decimal("1")) > Decimal("0.000001"):
            raise ValueError("growth_ratio and risk_ratio must sum to 1")
        return value


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    code: str = Field(min_length=1)
    function_name: str = "fetch"
    input_mapping: dict[str, str] = Field(default_factory=dict)
    output_mapping: dict[str, str] = Field(default_factory=dict)
    asset_ids: list[str] = Field(default_factory=list)
    packages: list[str] = Field(default_factory=list)
    schedule_minutes: int = Field(default=60, ge=1, le=525600)
    enabled: bool = False


class DataSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    code: str | None = Field(default=None, min_length=1)
    function_name: str | None = None
    input_mapping: dict[str, str] | None = None
    output_mapping: dict[str, str] | None = None
    asset_ids: list[str] | None = None
    packages: list[str] | None = None
    schedule_minutes: int | None = Field(default=None, ge=1, le=525600)
    enabled: bool | None = None


class DataSourceExecuteRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] | None = None


class ScheduledInvestmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    asset_id: str
    data_source_id: str
    amount_cny: Decimal = Field(gt=0)
    frequency: Literal["weekly", "biweekly", "monthly"]
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    time_of_day: str = Field(default="16:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    anchor_date: date | None = None
    retry_attempts: int = Field(default=3, ge=1, le=5)
    enabled: bool = True

    @field_validator("day_of_month")
    @classmethod
    def require_monthly_day(cls, value: int | None, info: Any) -> int | None:
        if info.data.get("frequency") == "monthly" and value is None:
            raise ValueError("monthly frequency requires day_of_month")
        return value


class ScheduledInvestmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    data_source_id: str | None = None
    amount_cny: Decimal | None = Field(default=None, gt=0)
    frequency: Literal["weekly", "biweekly", "monthly"] | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    time_of_day: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    anchor_date: date | None = None
    retry_attempts: int | None = Field(default=None, ge=1, le=5)
    enabled: bool | None = None


class NotificationRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    event_type: str = "generic_metric"
    metric_path: str = "portfolio.total_asset_cny"
    operator: Literal[">", ">=", "<", "<=", "="] = ">="
    threshold: Decimal | None = None
    webhook_url: str = ""
    headers_json: dict[str, str] = Field(default_factory=dict)
    body_template: str = (
        '{"title":"{{event.title}}","message":"{{event.message}}",'
        '"triggeredAt":"{{event.triggeredAt}}"}'
    )
    window_seconds: int = Field(default=86400, ge=1)
    max_deliveries: int = Field(default=1, ge=1, le=1000)
    enabled: bool = True


class NotificationRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    event_type: str | None = None
    metric_path: str | None = None
    operator: Literal[">", ">=", "<", "<=", "="] | None = None
    threshold: Decimal | None = None
    webhook_url: str | None = None
    headers_json: dict[str, str] | None = None
    body_template: str | None = None
    window_seconds: int | None = Field(default=None, ge=1)
    max_deliveries: int | None = Field(default=None, ge=1, le=1000)
    enabled: bool | None = None


class PlatformSettingsUpdate(BaseModel):
    allocation_mode: Literal["dynamic", "fixed"] | None = None
    growth_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    risk_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    default_contribution_cny: Decimal | None = Field(default=None, ge=0)

    @field_validator("risk_ratio")
    @classmethod
    def optional_ratios_sum_to_one(cls, value: Decimal | None, info: Any) -> Decimal | None:
        growth = info.data.get("growth_ratio")
        if value is not None and growth is not None:
            if abs((growth + value) - Decimal("1")) > Decimal("0.000001"):
                raise ValueError("growth_ratio and risk_ratio must sum to 1")
        return value
