from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RFQCustomer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: str | None = None


class RFQLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    requirements: str | None = None
    quoted_unit_price: float | None = None
    line_total: float | None = None


class RFQDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str | None = None
    delivery_location: str | None = None
    required_by_date: str | None = None
    currency: str | None = None
    payment_terms: str | None = None
    quote_validity_days: int | None = None
    submission_deadline: str | None = None
    quote_total: float | None = None
    deal_size: float | None = None
    quote_reference: str | None = None


class BidOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bid_id: int | None = Field(default=None, ge=1)
    status: Literal["WON", "LOST"] | None = None
    final_quote_price: float | None = Field(default=None, gt=0)
    lost_reason: str | None = None


class StructuredRFQ(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: RFQCustomer
    rfq: RFQDetails
    bid_outcome: BidOutcome = Field(default_factory=BidOutcome)
    line_items: list[RFQLineItem] = Field(default_factory=list)
    special_requirements: list[str] = Field(default_factory=list)
