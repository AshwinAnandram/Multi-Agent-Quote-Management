"""Deterministic acceptance checks for an evaluated quote."""

from decimal import Decimal, ROUND_CEILING


def minimum_quote_price_for_margin(
    total_cost: float,
    min_margin_pct: float | None,
) -> float | None:
    """Return the lowest cent-denominated price meeting minimum margin."""
    if min_margin_pct is None:
        return None

    cost = Decimal(str(total_cost))
    margin = Decimal(str(min_margin_pct))
    if cost <= 0 or margin >= 100:
        return None

    denominator = Decimal("1") - margin / Decimal("100")
    if denominator <= 0:
        return None

    threshold = max(cost, cost / denominator)
    return float(threshold.quantize(Decimal("0.01"), rounding=ROUND_CEILING))


def minimum_quote_price_for_discount(
    reference_quote_price: float,
    max_discount_pct: float | None,
) -> float | None:
    """Return the lowest cent-denominated price within the discount limit."""
    if max_discount_pct is None:
        return None

    reference_price = Decimal(str(reference_quote_price))
    max_discount = Decimal(str(max_discount_pct))
    if reference_price <= 0:
        return None

    threshold = reference_price * (
        Decimal("1") - max_discount / Decimal("100")
    )
    threshold = max(Decimal("0.01"), threshold)
    return float(threshold.quantize(Decimal("0.01"), rounding=ROUND_CEILING))


def evaluate_quote_policy(result: dict, pricing_policy: dict | None) -> dict:
    """Return an auditable policy decision without involving an LLM."""
    if pricing_policy is None:
        return {
            "status": "NO_POLICY",
            "reasons": ["No applicable active pricing policy was found."],
        }

    min_margin_pct = pricing_policy.get("min_margin_pct")
    max_discount_pct = pricing_policy.get("max_discount_pct")
    margin_pct = float(result["margin_pct"])
    discount_pct = float(result["discount_pct"])

    if min_margin_pct is None or max_discount_pct is None:
        return {
            "status": "POLICY_INCOMPLETE",
            "pricing_policy_id": pricing_policy.get("pricing_policy_id"),
            "min_margin_pct": min_margin_pct,
            "max_discount_pct": max_discount_pct,
            "margin_pct": margin_pct,
            "discount_pct": discount_pct,
            "reasons": ["The applicable pricing policy is missing a required limit."],
        }

    reasons = []
    if margin_pct < float(min_margin_pct):
        reasons.append(
            f"Proposed quote does not meet the minimum margin requirement "
            f"of {float(min_margin_pct):.2f}%."
        )

    if discount_pct > float(max_discount_pct):
        reasons.append(
            f"Proposed quote exceeds the maximum discount requirement "
            f"of {float(max_discount_pct):.2f}%."
        )

    return {
        "status": "REJECTED" if reasons else "COMPLIANT",
        "pricing_policy_id": pricing_policy.get("pricing_policy_id"),
        "min_margin_pct": float(min_margin_pct),
        "max_discount_pct": float(max_discount_pct),
        "margin_pct": margin_pct,
        "discount_pct": discount_pct,
        "reasons": reasons,
    }


def validate_quote_policy(result: dict, pricing_policy: dict) -> None:
    """Raise unless quote metrics comply with the selected active policy."""
    decision = evaluate_quote_policy(result, pricing_policy)

    if decision["status"] in {"NO_POLICY", "POLICY_INCOMPLETE"}:
        raise ValueError(decision["reasons"][0])

    if decision["reasons"]:
        raise ValueError(decision["reasons"][0])
