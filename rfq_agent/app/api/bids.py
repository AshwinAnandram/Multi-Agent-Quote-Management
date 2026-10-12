from fastapi import APIRouter, HTTPException
from typing import Literal

from app.services.bid_service import (
    list_bids,
    get_bid_detail,
    finalize_open_bid,
    BidFinalizationError,
)

router = APIRouter(
    prefix="/bids",
    tags=["bids"]
)


@router.get("")
def get_bid_list(
    status: Literal["OPEN", "CLOSED", "WON", "LOST", "ALL"] = "OPEN",
    page: int = 1,
    page_size: int = 25
):
    if page < 1:
        raise HTTPException(
            status_code=400,
            detail="Page must be greater than or equal to 1."
        )

    if page_size not in [25, 50, 100]:
        raise HTTPException(
            status_code=400,
            detail="Page size must be one of 25, 50, or 100."
        )

    result = list_bids(
        status=status,
        page=page,
        page_size=page_size
    )

    total = result["total"]

    total_pages = (
        (total + page_size - 1) // page_size
        if total > 0
        else 0
    )

    return {
        "status": status,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "bids": result["bids"]
    }


@router.get("/{bid_id}")
def get_bid(bid_id: int):
    bid = get_bid_detail(bid_id)

    if bid is None:
        raise HTTPException(
            status_code=404,
            detail="Bid not found"
        )

    return bid


@router.post("/{bid_id}/finalize")
def finalize_bid(bid_id: int):
    try:
        return finalize_open_bid(bid_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except BidFinalizationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
