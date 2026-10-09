from fastapi import APIRouter, HTTPException

from app.models.quote import ApplyPriceRequest
from app.services.quote_service import apply_price


router = APIRouter(
    prefix="/bids",
    tags=["quotes"]
)


@router.post("/{bid_id}/apply-price")
def apply_bid_price(
    bid_id: int,
    request: ApplyPriceRequest
):
    try:
        return apply_price(
            bid_id=bid_id,
            proposed_quote_price=request.proposed_quote_price,
            source=request.source,
            created_by=request.created_by
        )

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e)
        )