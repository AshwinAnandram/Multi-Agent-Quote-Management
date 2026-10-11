from app.services.bid_service import (
    get_bid_detail,
    get_bid_simulation_context_data,
    get_customer_history_data,
    get_pricing_policy_data
)

from app.services.ml_prediction import MLPredictionService
from app.services.quote_simulation import QuoteSimulationService
from app.services.quote_optimization import QuoteOptimizationService
from app.services.risk_evidence import RiskEvidenceService
from app.services.pricing_policy import (
    evaluate_quote_policy,
    minimum_quote_price_for_discount,
    minimum_quote_price_for_margin,
    validate_quote_policy,
)

prediction_service = MLPredictionService()

simulation_service = QuoteSimulationService(
    prediction_service
)

optimization_service = QuoteOptimizationService(
    simulation_service
)

risk_evidence_service = RiskEvidenceService(
    simulation_service
)

def get_bid(bid_id: int) -> dict:
    bid = get_bid_detail(bid_id)

    if bid is None:
        return {
            "status": "NOT_FOUND",
            "message": f"Bid {bid_id} was not found."
        }

    if (
        bid.get("current_margin_pct") is not None
        and bid.get("current_discount_pct") is not None
    ):
        bid["policy_decision"] = evaluate_quote_policy(
            {
                "margin_pct": bid["current_margin_pct"],
                "discount_pct": bid["current_discount_pct"],
            },
            bid.get("pricing_policy"),
        )
    else:
        bid["policy_decision"] = {
            "status": "NO_CURRENT_QUOTE",
            "reasons": ["The bid has no current quote to evaluate."],
        }

    pricing_policy = bid.get("pricing_policy")
    min_margin_pct = (
        pricing_policy.get("min_margin_pct")
        if pricing_policy
        else None
    )
    minimum_quote_price = minimum_quote_price_for_margin(
        total_cost=bid["total_cost"],
        min_margin_pct=min_margin_pct,
    )

    if pricing_policy is None:
        margin_boundary = {
            "status": "NO_POLICY",
            "reason": "No applicable active pricing policy was found.",
        }
    elif min_margin_pct is None or minimum_quote_price is None:
        margin_boundary = {
            "status": "UNAVAILABLE",
            "reason": "The applicable policy does not define a usable minimum margin.",
        }
    elif (
        bid.get("deal_size") is not None
        and minimum_quote_price > float(bid["deal_size"])
    ):
        margin_boundary = {
            "status": "NO_FEASIBLE_PRICE",
            "min_margin_pct": float(min_margin_pct),
            "minimum_quote_price_for_margin": minimum_quote_price,
            "reason": "The minimum-margin price exceeds the bid's deal size.",
        }
    else:
        margin_boundary = {
            "status": "AVAILABLE",
            "min_margin_pct": float(min_margin_pct),
            "minimum_quote_price_for_margin": minimum_quote_price,
            "first_cent_below_margin_boundary": round(
                minimum_quote_price - 0.01,
                2,
            ),
            "interpretation": (
                "The boundary price meets the minimum margin; any lower "
                "cent-denominated quote price falls below it."
            ),
        }

    bid["margin_boundary"] = margin_boundary

    max_discount_pct = (
        pricing_policy.get("max_discount_pct")
        if pricing_policy
        else None
    )
    reference_quote_price = bid.get("current_quote_price")
    minimum_quote_price = (
        minimum_quote_price_for_discount(
            reference_quote_price=reference_quote_price,
            max_discount_pct=max_discount_pct,
        )
        if reference_quote_price is not None
        else None
    )

    if pricing_policy is None:
        discount_boundary = {
            "status": "NO_POLICY",
            "reason": "No applicable active pricing policy was found.",
        }
    elif max_discount_pct is None:
        discount_boundary = {
            "status": "UNAVAILABLE",
            "reason": "The applicable policy does not define a usable maximum discount.",
        }
    elif reference_quote_price is None or minimum_quote_price is None:
        discount_boundary = {
            "status": "UNAVAILABLE",
            "reason": "The current quote price required to calculate discount is unavailable.",
        }
    elif (
        bid.get("deal_size") is not None
        and minimum_quote_price > float(bid["deal_size"])
    ):
        discount_boundary = {
            "status": "NO_FEASIBLE_PRICE",
            "max_discount_pct": float(max_discount_pct),
            "minimum_quote_price_within_discount_limit": minimum_quote_price,
            "reason": "The minimum price within the discount limit exceeds the bid's deal size.",
        }
    else:
        discount_boundary = {
            "status": "AVAILABLE",
            "max_discount_pct": float(max_discount_pct),
            "reference_quote_price": float(reference_quote_price),
            "minimum_quote_price_within_discount_limit": minimum_quote_price,
            "first_cent_below_discount_boundary": round(
                minimum_quote_price - 0.01,
                2,
            ),
            "interpretation": (
                "The boundary price is within the maximum discount; any lower "
                "cent-denominated quote price exceeds it."
            ),
        }

    bid["discount_boundary"] = discount_boundary

    return {
        "status": "FOUND",
        "bid": bid
    }


def simulate_quote(
    bid_id: int,
    proposed_quote_price: float
) -> dict:

    bid = get_bid_simulation_context_data(bid_id)

    if bid is None:
        return {
            "status": "REJECTED",
            "message": f"Bid {bid_id} was not found."
        }

    pricing_policy = get_pricing_policy_data(bid["customer_id"])
    if pricing_policy is None:
        return {
            "status": "REJECTED",
            "message": "No applicable pricing policy was found for this customer or globally."
        }

    try:
        result = simulation_service.simulate(
            bid=bid,
            proposed_quote_price=proposed_quote_price
        )
        validate_quote_policy(result, pricing_policy)

        return {
            "status": "VALID",
            "result": result,
            "pricing_policy": pricing_policy
        }

    except ValueError as e:
        return {
            "status": "REJECTED",
            "message": str(e)
        }

def compare_prices(
    bid_id: int,
    proposed_quote_prices: list[float]
) -> dict:

    if not proposed_quote_prices:
        return {
            "status": "REJECTED",
            "message": "At least one proposed quote price is required."
        }

    results = []

    for price in proposed_quote_prices:

        result = simulate_quote(
            bid_id=bid_id,
            proposed_quote_price=float(price)
        )

        results.append({
            "proposed_quote_price": float(price),
            **result
        })

    return {
        "status": "COMPLETED",
        "bid_id": bid_id,
        "comparisons": results
    }

def optimize_price(
    bid_id: int,
    step: float = 500.0,
    top_n: int = 1
) -> dict:

    bid = get_bid_simulation_context_data(bid_id)

    if bid is None:
        return {
            "status": "NOT_FOUND",
            "message": f"Bid {bid_id} was not found."
        }

    pricing_policy = get_pricing_policy_data(
        bid["customer_id"]
    )

    if pricing_policy is None:
        return {
            "status": "REJECTED",
            "message": (
                "No applicable pricing policy was found "
                "for this customer or globally."
            )
        }

    try:
        result = optimization_service.optimize(
            bid=bid,
            pricing_policy=pricing_policy,
            step=step,
            top_n = top_n
        )

        return result

    except ValueError as e:
        return {
            "status": "REJECTED",
            "message": str(e)
        }

def lookup_customer_history(bid_id: int) -> dict:

    history = get_customer_history_data(bid_id)

    if history is None:
        return {
            "status": "NOT_FOUND",
            "message": (
                f"Customer history for bid "
                f"{bid_id} was not found."
            )
        }

    return {
        "status": "FOUND",
        "history": history
    }
