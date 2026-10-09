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

    try:
        result = simulation_service.simulate(
            bid=bid,
            proposed_quote_price=proposed_quote_price
        )

        return {
            "status": "VALID",
            "result": result
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