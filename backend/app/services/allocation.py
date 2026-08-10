from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_allocation(
    *,
    contribution: Decimal,
    emergency_current: Decimal,
    emergency_target: Decimal,
    growth_current: Decimal,
    risk_current: Decimal,
    growth_ratio: Decimal,
    risk_ratio: Decimal,
    mode: str,
) -> dict[str, Decimal | str]:
    if contribution <= 0:
        raise ValueError("contribution must be positive")
    if abs((growth_ratio + risk_ratio) - Decimal("1")) > Decimal("0.000001"):
        raise ValueError("target ratios must sum to one")

    emergency_gap = max(Decimal("0"), emergency_target - emergency_current)
    emergency_allocation = min(contribution, emergency_gap)
    remainder = contribution - emergency_allocation

    if remainder <= 0:
        growth_allocation = Decimal("0")
        risk_allocation = Decimal("0")
    elif mode == "fixed":
        growth_allocation = money(remainder * growth_ratio)
        risk_allocation = remainder - growth_allocation
    elif mode == "dynamic":
        final_investment_total = growth_current + risk_current + remainder
        desired_growth = final_investment_total * growth_ratio
        desired_risk = final_investment_total * risk_ratio
        growth_need = max(Decimal("0"), desired_growth - growth_current)
        risk_need = max(Decimal("0"), desired_risk - risk_current)

        if growth_need >= remainder:
            growth_allocation = remainder
            risk_allocation = Decimal("0")
        elif risk_need >= remainder:
            growth_allocation = Decimal("0")
            risk_allocation = remainder
        else:
            growth_allocation = money(growth_need)
            risk_allocation = remainder - growth_allocation
    else:
        raise ValueError("unknown allocation mode")

    final_growth = growth_current + growth_allocation
    final_risk = risk_current + risk_allocation
    final_total = final_growth + final_risk

    return {
        "mode": mode,
        "contribution_cny": money(contribution),
        "emergency_cny": money(emergency_allocation),
        "growth_cny": money(growth_allocation),
        "risk_cny": money(risk_allocation),
        "remaining_emergency_gap_cny": money(max(Decimal("0"), emergency_gap - emergency_allocation)),
        "projected_growth_ratio": money(final_growth / final_total * 100) if final_total else Decimal("0"),
        "projected_risk_ratio": money(final_risk / final_total * 100) if final_total else Decimal("0"),
    }
