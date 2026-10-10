from app.services.ml_prediction import MLPredictionService
from app.services.quote_simulation import QuoteSimulationService
from app.repositories.bid_repository import (
    get_bid,
    get_bid_simulation_context,
    get_pricing_policy,
    get_current_quote_version,
    create_quote_version
)


prediction_service = MLPredictionService()

simulation_service = QuoteSimulationService(
    prediction_service
)


def apply_price(
    bid_id: int,
    proposed_quote_price: float,
    source: str,
    created_by: str
):
    bid = get_bid(bid_id)

    if bid is None:
        raise ValueError(
            f"Bid {bid_id} was not found."
        )

    if bid["status"] != "OPEN":
        raise ValueError(
            f"Bid {bid_id} is not open for price changes."
        )

    current_version = get_current_quote_version(
        bid_id
    )

    if current_version is None:
        raise ValueError(
            f"Bid {bid_id} does not have a current quote version."
        )

    current_quote_price = float(
        current_version["quote_price"]
    )

    if proposed_quote_price == current_quote_price:
        raise ValueError(
            "Proposed quote price is already the current quote price."
        )

    simulation_context = get_bid_simulation_context(
        bid_id
    )

    if simulation_context is None:
        raise ValueError(
            f"Simulation context for bid {bid_id} was not found."
        )

    pricing_policy = get_pricing_policy(
        simulation_context["customer_id"]
    )

    if pricing_policy is None:
        raise ValueError(
            "No applicable pricing policy was found."
        )

    result = simulation_service.simulate(
        bid=simulation_context,
        proposed_quote_price=proposed_quote_price,
        pricing_policy=pricing_policy
    )

    quote_version = create_quote_version(
        bid_id=bid_id,
        quote_price=result["proposed_quote_price"],
        discount_pct=result["discount_pct"],
        margin_pct=result["margin_pct"],
        source=source,
        created_by=created_by
    )

    return {
        "status": "APPLIED",
        "bid_id": bid_id,
        "quote_version": quote_version,
        "simulation": result,
        "pricing_policy": {
            "pricing_policy_id": pricing_policy[
                "pricing_policy_id"
            ],
            "min_margin_pct": min_margin_pct,
            "max_discount_pct": max_discount_pct
        }
    }