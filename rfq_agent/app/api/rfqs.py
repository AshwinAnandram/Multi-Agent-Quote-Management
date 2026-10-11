from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.repositories.rfq_repository import (
    get_review_options,
    get_rfq_review,
    create_or_find_customer,
    list_on_hold_rfqs,
    reject_rfq,
    save_rfq_review,
    accept_rfq,
    RFQAcceptanceError,
)


router = APIRouter(prefix="/rfqs", tags=["rfqs"])


class ReviewLineItem(BaseModel):
    line_item_id: int | None = None
    product_name_raw: str | None = None
    product_id: int | None = None
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    requirements: str | None = None


class ReviewRequest(BaseModel):
    customer_id: int | None = None
    sales_rep_id: int | None = None
    opening_quote_price: float | None = Field(default=None, gt=0)
    deal_size: float | None = Field(default=None, gt=0)
    delivery_location: str | None = None
    required_by_date: date | None = None
    currency: str | None = None
    payment_terms: str | None = None
    rfq_description: str | None = None
    line_items: list[ReviewLineItem]


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AcceptRequest(BaseModel):
    confirm_source_conflicts: bool = False


class CustomerCreateRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=255)
    industry: str | None = None
    country: str | None = None
    segment: str | None = None
    min_margin_pct: float | None = Field(default=None, ge=0, le=100)
    max_discount_pct: float | None = Field(default=None, ge=0, le=100)


@router.get("/on-hold")
def get_on_hold(page: int = 1, page_size: int = 25):
    if page < 1 or page_size not in {25, 50, 100}:
        raise HTTPException(status_code=400, detail="Invalid pagination values.")
    return list_on_hold_rfqs(page, page_size)


@router.get("/review-options")
def review_options():
    return get_review_options()


@router.post("/customers")
def create_customer(request: CustomerCreateRequest):
    try:
        return create_or_find_customer(**request.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{rfq_id}/review")
def get_review(rfq_id: int):
    result = get_rfq_review(rfq_id)
    if result is None:
        raise HTTPException(status_code=404, detail="RFQ not found.")
    return result


@router.put("/{rfq_id}/review")
def update_review(rfq_id: int, request: ReviewRequest):
    try:
        save_rfq_review(
            rfq_id=rfq_id,
            customer_id=request.customer_id,
            values={
                "delivery_location": request.delivery_location,
                "required_by_date": request.required_by_date.isoformat() if request.required_by_date else None,
                "currency": request.currency,
                "payment_terms": request.payment_terms,
                "rfq_description": request.rfq_description,
                "sales_rep_id": request.sales_rep_id,
                "opening_quote_price": request.opening_quote_price,
                "deal_size": request.deal_size,
            },
            line_items=[item.model_dump() for item in request.line_items],
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"rfq_id": rfq_id, "status": "REVIEW_SAVED"}


@router.post("/{rfq_id}/reject")
def reject(rfq_id: int, request: RejectRequest):
    if not reject_rfq(rfq_id, request.reason):
        raise HTTPException(status_code=404, detail="RFQ not found or no longer on hold.")
    return {"rfq_id": rfq_id, "status": "REJECTED"}


@router.post("/{rfq_id}/accept")
def accept(rfq_id: int, request: AcceptRequest):
    try:
        return accept_rfq(rfq_id, request.confirm_source_conflicts)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RFQAcceptanceError as error:
        detail = {"message": str(error), "policy_decision": error.decision} if error.decision else str(error)
        raise HTTPException(status_code=422, detail=detail) from error
