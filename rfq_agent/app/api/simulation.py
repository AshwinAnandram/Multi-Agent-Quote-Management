from fastapi import APIRouter, HTTPException

from app.models.quote import QuoteSimulationRequest
from app.services.bid_service import (
    get_bid_simulation_context_data,
    get_pricing_policy_data
)
from app.services.ml_prediction import MLPredictionService
from app.services.quote_simulation import (
    QuoteSimulationService
)


router = APIRouter(
    prefix="/bids",
    tags=["simulation"]
)


prediction_service = MLPredictionService()

simulation_service = QuoteSimulationService(
    prediction_service
)


@router.post("/{bid_id}/simulate")
def simulate_quote(bid_id: int, request: QuoteSimulationRequest):
    bid = get_bid_simulation_context_data(bid_id)

    if bid is None:
        raise HTTPException(
            status_code=404,
            detail="Bid not found"
        )

    pricing_policy = get_pricing_policy_data(
        bid["customer_id"]
    )

    if pricing_policy is None:
        raise HTTPException(
            status_code=422,
            detail="No applicable pricing policy was found."
        )

    try:
        simulation = simulation_service.simulate(
            bid=bid,
            proposed_quote_price=request.proposed_quote_price,
            pricing_policy=pricing_policy
        )

        return {
            "simulation": simulation,
            "pricing_policy": {
                "pricing_policy_id": pricing_policy[
                    "pricing_policy_id"
                ],
                "customer_id": pricing_policy[
                    "customer_id"
                ],
                "min_margin_pct": pricing_policy[
                    "min_margin_pct"
                ],
                "max_discount_pct": pricing_policy[
                    "max_discount_pct"
                ]
            }
        }

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e)
        )