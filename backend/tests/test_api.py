from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import (
    Asset,
    Basket,
    DataSource,
    DataSourceRun,
    LedgerEntry,
    NotificationRule,
    PortfolioSnapshot,
    Valuation,
)
from app.services import datasources

from conftest import TEST_PLATFORM_TOKEN


def test_api_requires_platform_token(client) -> None:
    response = client.get("/api/v1/assets")
    assert response.status_code == 401


def test_browser_login_creates_http_only_session_and_logout_revokes_it(client) -> None:
    wrong = client.post("/api/v1/auth/login", json={"token": "wrong-token"})
    assert wrong.status_code == 401

    login = client.post("/api/v1/auth/login", json={"token": TEST_PLATFORM_TOKEN})
    assert login.status_code == 204
    set_cookie = login.headers["set-cookie"]
    assert "investment_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    captured_cookie = login.cookies.get("investment_session")
    assert captured_cookie

    dashboard = client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    assert client.get("/api/v1/auth/session").json() == {"authenticated": True}

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/v1/dashboard").status_code == 401
    replay = client.get(
        "/api/v1/dashboard",
        headers={"Cookie": f"investment_session={captured_cookie}"},
    )
    assert replay.status_code == 401


def test_asset_and_valuation_flow(client, db, auth_headers) -> None:
    create = client.post(
        "/api/v1/assets",
        headers=auth_headers,
        json={
            "basket_code": "growth",
            "name": "测试指数基金",
            "platform": "测试平台",
            "symbol": "TEST100",
            "currency": "CNY",
            "units": "100",
            "unit_price": "2.5",
            "fx_rate": "1",
        },
    )
    assert create.status_code == 201
    asset_id = create.json()["id"]
    assert Decimal(create.json()["value_cny"]) == Decimal("250")
    opening_entry = db.scalar(
        select(LedgerEntry).where(
            LedgerEntry.asset_id == asset_id,
            LedgerEntry.kind == "asset_opening",
        )
    )
    assert opening_entry is not None
    assert opening_entry.amount == Decimal("250")
    assert opening_entry.basket_id == db.scalar(select(Asset.basket_id).where(Asset.id == asset_id))

    dashboard = client.get("/api/v1/dashboard", headers=auth_headers).json()
    growth = next(item for item in dashboard["baskets"] if item["code"] == "growth")
    assert growth["principalCny"] == 250.0
    assert growth["cashBalanceCny"] == 0.0

    update = client.post(
        f"/api/v1/assets/{asset_id}/valuations",
        headers=auth_headers,
        json={"unit_price": "2.8", "source": "manual"},
    )
    assert update.status_code == 201
    assert update.json()["valueCny"] == 280.0
    assert db.scalar(select(func.count(Valuation.id))) == 2

    deleted = client.delete(f"/api/v1/assets/{asset_id}", headers=auth_headers)
    assert deleted.status_code == 204
    assert db.scalar(select(Asset.deleted_at).where(Asset.id == asset_id)) is not None


def test_selling_asset_moves_proceeds_to_pending_cash_and_can_liquidate(
    client, db, auth_headers
) -> None:
    asset = db.scalar(select(Asset).where(Asset.name == "风险资产"))
    risk = db.scalar(select(Basket).where(Basket.code == "risk"))
    assert asset is not None
    assert risk is not None

    partial = client.post(
        f"/api/v1/assets/{asset.id}/sell",
        headers=auth_headers,
        json={"units": "0.25", "unit_price": "20000", "note": "调仓到待投资资产"},
    )
    assert partial.status_code == 201
    assert partial.json() == {
        "id": partial.json()["id"],
        "proceedsCny": 5000.0,
        "remainingUnits": 0.75,
        "assetLiquidated": False,
    }
    assert asset.units == Decimal("0.75")
    assert risk.cash_balance_cny == Decimal("105000")

    full = client.post(
        f"/api/v1/assets/{asset.id}/sell",
        headers=auth_headers,
        json={"units": "0.75", "unit_price": "20000"},
    )
    assert full.status_code == 201
    assert full.json()["assetLiquidated"] is True
    assert risk.cash_balance_cny == Decimal("120000")
    assert asset.deleted_at is not None
    assert db.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == "sell")) == 2


def test_sale_rejects_units_above_current_holding(client, db, auth_headers) -> None:
    asset = db.scalar(select(Asset).where(Asset.name == "风险资产"))
    response = client.post(
        f"/api/v1/assets/{asset.id}/sell",
        headers=auth_headers,
        json={"units": "1.01", "unit_price": "20000"},
    )
    assert response.status_code == 422
    assert asset.units == Decimal("1")


def test_asset_sync_runs_only_its_bound_source(client, db, auth_headers, monkeypatch) -> None:
    asset = db.scalar(select(Asset).where(Asset.name == "成长资产"))
    source = DataSource(
        name="单资产报价", code="def fetch(payload): return {'items': []}",
        input_mapping={"code": "symbol"}, output_mapping={"unit_price": "price"},
        asset_ids=[asset.id], packages=[],
    )
    db.add(source)
    db.commit()
    received: dict[str, object] = {}

    def execute_one(session, selected_source, *, asset_ids=None, **_kwargs):
        received["source_id"] = selected_source.id
        received["asset_ids"] = asset_ids
        asset.unit_price = Decimal("9.9")
        asset.price_updated_at = datetime.now(timezone.utc)
        run = DataSourceRun(
            data_source_id=selected_source.id, status="success",
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
            input_payload={}, output_payload={}, duration_ms=12,
        )
        session.add(run)
        session.commit()
        return run

    monkeypatch.setattr("app.api.execute_data_source", execute_one)
    response = client.post(f"/api/v1/assets/{asset.id}/sync", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["unitPrice"] == 9.9
    assert received == {"source_id": source.id, "asset_ids": [asset.id]}


def test_allocation_preview_uses_current_basket_values(client, auth_headers) -> None:
    response = client.post(
        "/api/v1/allocations/preview",
        headers=auth_headers,
        json={
            "contribution_cny": "15000",
            "mode": "dynamic",
            "growth_ratio": "0.8",
            "risk_ratio": "0.2",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["emergency_cny"] == "10000.00"
    # 高风险篮子的待投资资产也计入当前配置，因此剩余资金优先补成长。
    assert payload["growth_cny"] == "5000.00"
    assert payload["risk_cny"] == "0.00"


def test_pending_cash_is_included_in_growth_and_risk_compass(client, db, auth_headers) -> None:
    growth = db.scalar(select(Basket).where(Basket.code == "growth"))
    risk = db.scalar(select(Basket).where(Basket.code == "risk"))
    assert growth is not None
    assert risk is not None
    growth.cash_balance_cny = Decimal("20000")
    risk.cash_balance_cny = Decimal("10000")
    db.commit()

    response = client.get("/api/v1/dashboard", headers=auth_headers)
    assert response.status_code == 200
    allocation = response.json()["allocation"]
    # 应急储备金的 50,000 不参与；成长和高风险均包含各自待投资资产。
    assert allocation["growthRatio"] == pytest.approx(100000 / 130000 * 100)
    assert allocation["riskRatio"] == pytest.approx(30000 / 130000 * 100)


def test_dashboard_reports_principal_and_profit_for_each_basket(
    client, db, auth_headers
) -> None:
    baskets = {item.code: item for item in db.scalars(select(Basket))}
    db.add_all(
        [
            LedgerEntry(
                kind="opening",
                basket_id=baskets["emergency"].id,
                amount=Decimal("50000"),
                occurred_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            ),
            LedgerEntry(
                kind="opening",
                basket_id=baskets["growth"].id,
                amount=Decimal("70000"),
                occurred_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            ),
            LedgerEntry(
                kind="opening",
                basket_id=baskets["risk"].id,
                amount=Decimal("125000"),
                occurred_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            ),
        ]
    )
    db.commit()

    dashboard = client.get("/api/v1/dashboard", headers=auth_headers).json()
    by_code = {item["code"]: item for item in dashboard["baskets"]}

    assert by_code["emergency"]["principalCny"] == 50000.0
    assert by_code["emergency"]["profitCny"] == 0.0
    assert by_code["growth"]["principalCny"] == 70000.0
    assert by_code["growth"]["profitCny"] == 10000.0
    assert by_code["risk"]["principalCny"] == 125000.0
    assert by_code["risk"]["profitCny"] == -5000.0


def test_dashboard_curve_keeps_last_snapshot_for_each_month(client, db, auth_headers) -> None:
    snapshots = [
        PortfolioSnapshot(
            total_asset_cny=Decimal("100"),
            principal_cny=Decimal("90"),
            profit_cny=Decimal("10"),
            basket_values={"growth": 100},
            basket_principals={"growth": 90},
            observed_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
            source="test",
        ),
        PortfolioSnapshot(
            total_asset_cny=Decimal("120"),
            principal_cny=Decimal("100"),
            profit_cny=Decimal("20"),
            basket_values={"growth": 120},
            basket_principals={"growth": 100},
            observed_at=datetime(2026, 7, 31, 15, tzinfo=timezone.utc),
            source="test",
        ),
        PortfolioSnapshot(
            total_asset_cny=Decimal("150"),
            principal_cny=Decimal("125"),
            profit_cny=Decimal("25"),
            basket_values={"growth": 150},
            basket_principals={"growth": 125},
            observed_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            source="test",
        ),
    ]
    db.add_all(snapshots)
    db.commit()

    curve = client.get("/api/v1/dashboard", headers=auth_headers).json()["curve"]

    assert [point["month"] for point in curve] == ["2026-07", "2026-08"]
    assert curve[0]["total"] == 120.0
    assert curve[1]["netContribution"] == 25.0
    assert curve[1]["valueChange"] == 30.0
    assert curve[1]["baskets"]["growth"]["profit"] == 25.0
    assert curve[1]["baskets"]["growth"]["profitRatio"] == 20.0


def test_emergency_target_can_be_saved_with_calculation_note(client, auth_headers) -> None:
    response = client.patch(
        "/api/v1/baskets/emergency",
        headers=auth_headers,
        json={
            "emergency_target_cny": "72000",
            "calculation_note": "每月必要支出 12000 元，保留 6 个月。",
        },
    )
    assert response.status_code == 200
    assert response.json()["emergencyTargetCny"] == 72000.0
    dashboard = client.get("/api/v1/dashboard", headers=auth_headers).json()
    emergency = next(item for item in dashboard["baskets"] if item["code"] == "emergency")
    assert emergency["emergencyTargetCny"] == 72000.0


def test_human_asset_edit_updates_units_price_and_valuation(client, db, auth_headers) -> None:
    asset = db.scalar(select(Asset).where(Asset.name == "成长资产"))
    before = db.scalar(select(func.count(Valuation.id)))
    response = client.patch(
        f"/api/v1/assets/{asset.id}",
        headers=auth_headers,
        json={"units": "2.5", "unit_price": "36000", "platform": "新平台"},
    )
    assert response.status_code == 200
    assert Decimal(response.json()["units"]) == Decimal("2.5")
    assert Decimal(response.json()["unit_price"]) == Decimal("36000")
    assert response.json()["platform"] == "新平台"
    assert db.scalar(select(func.count(Valuation.id))) == before + 1


def test_platform_allocation_settings_update_basket_targets(client, auth_headers) -> None:
    response = client.patch(
        "/api/v1/settings",
        headers=auth_headers,
        json={
            "allocation_mode": "fixed",
            "growth_ratio": "0.7",
            "risk_ratio": "0.3",
            "default_contribution_cny": "15000",
        },
    )
    assert response.status_code == 200
    assert response.json()["allocationMode"] == "fixed"
    dashboard = client.get("/api/v1/dashboard", headers=auth_headers).json()
    assert dashboard["allocation"]["mode"] == "fixed"
    assert dashboard["allocation"]["targetGrowthRatio"] == 70.0


def test_data_source_can_bind_assets_and_update_mapping(client, db, auth_headers) -> None:
    assets = list(db.scalars(select(Asset).order_by(Asset.created_at)))
    source = DataSource(
        name="基金渠道",
        code="def fetch(payload):\n    return {'items': []}\n",
        input_mapping={},
        output_mapping={},
        asset_ids=[],
        packages=[],
    )
    db.add(source)
    db.commit()
    response = client.patch(
        f"/api/v1/data-sources/{source.id}",
        headers=auth_headers,
        json={
            "asset_ids": [assets[0].id],
            "input_mapping": {"fund_code": "symbol"},
            "output_mapping": {"unit_price": "price"},
            "enabled": True,
        },
    )
    assert response.status_code == 200
    listed = client.get("/api/v1/data-sources", headers=auth_headers).json()
    saved = next(item for item in listed if item["id"] == source.id)
    assert saved["assetIds"] == [assets[0].id]
    assert saved["inputMapping"] == {"fund_code": "symbol"}


def test_data_source_surfaces_runner_validation_detail(
    client, db, auth_headers, monkeypatch
) -> None:
    source = DataSource(
        name="错误详情测试",
        code="def fetch(payload): return {}",
        input_mapping={},
        output_mapping={},
        asset_ids=[],
        packages=["httpx"],
    )
    db.add(source)
    db.commit()

    class RunnerResponse:
        is_error = True

        def json(self):
            return {"detail": "Failed to create virtual environment"}

        def raise_for_status(self):
            raise AssertionError("structured Runner errors should be handled first")

    monkeypatch.setattr(datasources.httpx, "post", lambda *args, **kwargs: RunnerResponse())

    response = client.post(
        f"/api/v1/data-sources/{source.id}/execute",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Runner 执行失败：Failed to create virtual environment"
    )


def test_data_source_and_notification_rule_can_be_deleted(client, db, auth_headers) -> None:
    source = DataSource(
        name="待删除数据源",
        code="def fetch(payload):\n    return {'items': []}\n",
        input_mapping={},
        output_mapping={},
        asset_ids=[],
        packages=[],
    )
    rule = NotificationRule(
        name="待删除推送",
        event_type="generic_metric",
        metric_path="portfolio.total_asset_cny",
        operator=">=",
        threshold=Decimal("1"),
        webhook_url="https://example.com/webhook",
    )
    db.add_all([source, rule])
    db.commit()

    assert client.delete(f"/api/v1/data-sources/{source.id}", headers=auth_headers).status_code == 204
    assert client.delete(f"/api/v1/notification-rules/{rule.id}", headers=auth_headers).status_code == 204

    assert db.scalar(select(DataSource.deleted_at).where(DataSource.id == source.id)) is not None
    assert db.scalar(select(NotificationRule.deleted_at).where(NotificationRule.id == rule.id)) is not None
    assert source.id not in {item["id"] for item in client.get("/api/v1/data-sources", headers=auth_headers).json()}
    assert rule.id not in {item["id"] for item in client.get("/api/v1/notification-rules", headers=auth_headers).json()}
