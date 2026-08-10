from decimal import Decimal

from app.services.allocation import calculate_allocation


def test_emergency_gap_is_filled_before_other_baskets() -> None:
    result = calculate_allocation(
        contribution=Decimal("15000"),
        emergency_current=Decimal("50000"),
        emergency_target=Decimal("60000"),
        growth_current=Decimal("70000"),
        risk_current=Decimal("30000"),
        growth_ratio=Decimal("0.8"),
        risk_ratio=Decimal("0.2"),
        mode="dynamic",
    )

    assert result["emergency_cny"] == Decimal("10000.00")
    assert result["growth_cny"] == Decimal("5000.00")
    assert result["risk_cny"] == Decimal("0.00")


def test_dynamic_mode_corrects_overweight_risk_with_new_cash() -> None:
    result = calculate_allocation(
        contribution=Decimal("10000"),
        emergency_current=Decimal("60000"),
        emergency_target=Decimal("60000"),
        growth_current=Decimal("70000"),
        risk_current=Decimal("30000"),
        growth_ratio=Decimal("0.8"),
        risk_ratio=Decimal("0.2"),
        mode="dynamic",
    )

    assert result["growth_cny"] == Decimal("10000.00")
    assert result["risk_cny"] == Decimal("0.00")


def test_fixed_mode_ignores_existing_drift() -> None:
    result = calculate_allocation(
        contribution=Decimal("10000"),
        emergency_current=Decimal("60000"),
        emergency_target=Decimal("60000"),
        growth_current=Decimal("70000"),
        risk_current=Decimal("30000"),
        growth_ratio=Decimal("0.8"),
        risk_ratio=Decimal("0.2"),
        mode="fixed",
    )

    assert result["growth_cny"] == Decimal("8000.00")
    assert result["risk_cny"] == Decimal("2000.00")
