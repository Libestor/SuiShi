from decimal import Decimal

from sqlalchemy import func, select

from app.models import Asset, DataSource, Valuation


def test_api_requires_platform_token(client) -> None:
    response = client.get("/api/v1/assets")
    assert response.status_code == 401


def test_browser_login_creates_http_only_session_and_logout_revokes_it(client) -> None:
    wrong = client.post("/api/v1/auth/login", json={"token": "wrong-token"})
    assert wrong.status_code == 401

    login = client.post("/api/v1/auth/login", json={"token": "test-token"})
    assert login.status_code == 204
    cookie = login.headers["set-cookie"]
    assert "investment_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie

    dashboard = client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    assert client.get("/api/v1/auth/session").json() == {"authenticated": True}

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/v1/dashboard").status_code == 401


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
    assert payload["growth_cny"] == "4000.00"
    assert payload["risk_cny"] == "1000.00"


def test_pending_cash_does_not_change_invested_risk_ratio(client, auth_headers) -> None:
    response = client.get("/api/v1/dashboard", headers=auth_headers)
    assert response.status_code == 200
    allocation = response.json()["allocation"]
    assert allocation["growthRatio"] == 80.0
    assert allocation["riskRatio"] == 20.0


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
