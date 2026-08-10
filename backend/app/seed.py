from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import (
    Asset,
    Basket,
    DataSource,
    Goal,
    InvestmentPlan,
    LedgerEntry,
    NotificationRule,
    PendingTask,
    PlatformSettings,
    PortfolioSnapshot,
)
from app.services.portfolio import calculate_totals
from app.services.versioning import save_data_source_version


def seed() -> None:
    with SessionLocal() as db:
        if (db.scalar(select(func.count(Basket.id))) or 0) > 0:
            return

        emergency = Basket(
            code="emergency",
            name="应急储备金",
            description="六个月必要支出，优先补足",
            color="#718b6b",
            icon="shield",
            target_ratio=Decimal("0"),
            cash_balance_cny=Decimal("12000"),
            emergency_target_cny=Decimal("60000"),
            calculation_note="房租、伙食、水电等必要支出约 1 万元/月，保留 6 个月。",
        )
        growth = Basket(
            code="growth",
            name="成长性投资",
            description="长期指数与基金投资",
            color="#bf7b53",
            icon="sprout",
            target_ratio=Decimal("0.8"),
            cash_balance_cny=Decimal("6400"),
        )
        risk = Basket(
            code="risk",
            name="高风险投资",
            description="严格控制比例的高波动资产",
            color="#8b6570",
            icon="flame",
            target_ratio=Decimal("0.2"),
            cash_balance_cny=Decimal("2200"),
        )
        db.add_all([emergency, growth, risk])
        db.flush()

        now = datetime.now(timezone.utc)
        assets = [
            Asset(
                basket_id=emergency.id,
                name="银行现金管理",
                platform="招商银行",
                symbol="CASH-RESERVE",
                currency="CNY",
                units=Decimal("1"),
                unit_price=Decimal("48000"),
                fx_rate=Decimal("1"),
                update_source="manual",
                price_updated_at=now - timedelta(hours=3),
                fx_updated_at=now,
                note="低波动、随时可取",
            ),
            Asset(
                basket_id=growth.id,
                name="沪深300指数基金",
                platform="支付宝",
                symbol="000300",
                currency="CNY",
                units=Decimal("25630.1229"),
                unit_price=Decimal("2.5731"),
                fx_rate=Decimal("1"),
                update_source="data-source:基金净值",
                price_updated_at=now - timedelta(hours=8),
                fx_updated_at=now,
                source_attributes={"fund_code": "000300"},
            ),
            Asset(
                basket_id=growth.id,
                name="标普500指数基金",
                platform="券商账户",
                symbol="VOO",
                currency="USD",
                units=Decimal("12.5"),
                unit_price=Decimal("518.42"),
                fx_rate=Decimal("7.18"),
                update_source="data-source:海外行情",
                price_updated_at=now - timedelta(minutes=42),
                fx_updated_at=now - timedelta(hours=1),
                source_attributes={"ticker": "VOO", "exchange": "NYSEARCA"},
            ),
            Asset(
                basket_id=risk.id,
                name="比特币",
                platform="数字资产账户",
                symbol="BTCUSDT",
                currency="USDT",
                units=Decimal("0.052"),
                unit_price=Decimal("93100"),
                fx_rate=Decimal("7.18"),
                update_source="data-source:数字资产行情",
                price_updated_at=now - timedelta(minutes=12),
                fx_updated_at=now - timedelta(hours=1),
                source_attributes={"pair": "BTCUSDT"},
            ),
            Asset(
                basket_id=risk.id,
                name="半导体行业基金",
                platform="天天基金",
                symbol="CHIP-FUND",
                currency="CNY",
                units=Decimal("8200"),
                unit_price=Decimal("1.924"),
                fx_rate=Decimal("1"),
                update_source="manual",
                price_updated_at=now - timedelta(days=3),
                fx_updated_at=now,
                source_attributes={"fund_code": "009999"},
            ),
        ]
        db.add_all(assets)

        db.add_all(
            [
                LedgerEntry(
                    kind="opening",
                    basket_id=emergency.id,
                    amount=Decimal("60000"),
                    currency="CNY",
                    fx_rate=Decimal("1"),
                    occurred_at=now - timedelta(days=180),
                    note="平台期初快照",
                ),
                LedgerEntry(
                    kind="opening",
                    basket_id=growth.id,
                    amount=Decimal("93000"),
                    currency="CNY",
                    fx_rate=Decimal("1"),
                    occurred_at=now - timedelta(days=180),
                    note="平台期初快照",
                ),
                LedgerEntry(
                    kind="opening",
                    basket_id=risk.id,
                    amount=Decimal("35000"),
                    currency="CNY",
                    fx_rate=Decimal("1"),
                    occurred_at=now - timedelta(days=180),
                    note="平台期初快照",
                ),
                LedgerEntry(
                    kind="external_deposit",
                    basket_id=growth.id,
                    amount=Decimal("24000"),
                    currency="CNY",
                    fx_rate=Decimal("1"),
                    occurred_at=now - timedelta(days=60),
                    note="近两月投入",
                ),
            ]
        )

        goal = Goal(
            title="第一片真正的树荫",
            target_amount_cny=Decimal("300000"),
            description="总资产达到 30 万，拥有更从容的选择空间。",
            reward_title="去山里住两晚",
            reward_description="关掉工作消息，好好庆祝这段积累。",
            icon="oak",
            target_date=date.today() + timedelta(days=240),
        )
        plan = InvestmentPlan(
            name="每月长期投入",
            amount_cny=Decimal("12000"),
            day_of_month=10,
            allocation_mode="dynamic",
            growth_ratio=Decimal("0.8"),
            risk_ratio=Decimal("0.2"),
            enabled=True,
            next_due_at=now + timedelta(days=9),
        )
        task = PendingTask(
            kind="data_freshness",
            title="更新半导体行业基金净值",
            description="该资产已 3 天没有更新，当前比例可能存在小幅偏差。",
            due_at=now,
            payload={"asset_symbol": "CHIP-FUND"},
        )
        db.add_all([goal, plan, task])
        db.add(
            PlatformSettings(
                allocation_mode="dynamic",
                growth_ratio=Decimal("0.8"),
                risk_ratio=Decimal("0.2"),
                default_contribution_cny=Decimal("12000"),
            )
        )

        sample_code = '''def fetch(payload):
    """示例：将输入中的模拟单价原样返回。替换为真实 HTTP 请求即可。"""
    results = []
    for item in payload.get("items", []):
        results.append({
            "asset_id": item["asset_id"],
            "price": item.get("fallback_price", 0),
        })
    return {"items": results}
'''
        source = DataSource(
            name="示例行情脚本",
            description="展示批量字典输入、输出和字段映射。默认关闭。",
            code=sample_code,
            function_name="fetch",
            input_mapping={"symbol": "symbol", "fallback_price": "unit_price"},
            output_mapping={"unit_price": "price"},
            packages=[],
            schedule_minutes=60,
            enabled=False,
        )
        db.add(source)

        db.add(
            NotificationRule(
                name="总资产跨越 30 万",
                event_type="milestone",
                metric_path="portfolio.total_asset_cny",
                operator=">=",
                threshold=Decimal("300000"),
                webhook_url="",
                body_template='{"title":"{{event.title}}","message":"{{event.message}}"}',
                window_seconds=86400,
                max_deliveries=1,
                enabled=True,
            )
        )

        db.commit()
        db.refresh(source)
        try:
            source.git_revision = save_data_source_version(
                source.id, source.name, source.code, source.packages
            )
            db.commit()
        except Exception:
            db.rollback()

        totals = calculate_totals(db)
        final_total = totals["total"]
        final_principal = totals["principal"]
        points = [
            (180, Decimal("188000"), Decimal("188000")),
            (150, Decimal("192400"), Decimal("188000")),
            (120, Decimal("199800"), Decimal("188000")),
            (90, Decimal("207600"), Decimal("188000")),
            (60, Decimal("218900"), Decimal("200000")),
            (30, Decimal("226300"), Decimal("212000")),
            (0, final_total, final_principal),
        ]
        for days_ago, total, principal in points:
            db.add(
                PortfolioSnapshot(
                    total_asset_cny=total,
                    principal_cny=principal,
                    profit_cny=total - principal,
                    basket_values={},
                    observed_at=now - timedelta(days=days_ago),
                    source="seed" if days_ago else "opening",
                )
            )
        db.commit()


if __name__ == "__main__":
    seed()
