import math


def get_policy_limits(
    pricing_policy: dict | None
) -> tuple[float, float]:
    if pricing_policy is None:
        raise ValueError(
            "No applicable pricing policy was found."
        )

    min_margin_pct = pricing_policy.get("min_margin_pct")
    max_discount_pct = pricing_policy.get("max_discount_pct")

    if min_margin_pct is None:
        raise ValueError(
            "Applicable pricing policy does not define a minimum margin."
        )

    if max_discount_pct is None:
        raise ValueError(
            "Applicable pricing policy does not define a maximum discount."
        )

    try:
        min_margin_pct = float(min_margin_pct)
        max_discount_pct = float(max_discount_pct)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Applicable pricing policy contains invalid margin or discount thresholds."
        ) from error

    if not math.isfinite(min_margin_pct) or not math.isfinite(max_discount_pct):
        raise ValueError(
            "Applicable pricing policy contains invalid margin or discount thresholds."
        )

    return min_margin_pct, max_discount_pct


def validate_quote_policy(
    margin_pct: float,
    discount_pct: float,
    pricing_policy: dict | None
) -> None:
    min_margin_pct, max_discount_pct = get_policy_limits(
        pricing_policy
    )

    if margin_pct < min_margin_pct:
        raise ValueError(
            f"Proposed quote does not meet the minimum "
            f"margin requirement of {min_margin_pct:.2f}%."
        )

    if discount_pct > max_discount_pct:
        raise ValueError(
            f"Proposed quote exceeds the maximum "
            f"discount requirement of {max_discount_pct:.2f}%."
        )
