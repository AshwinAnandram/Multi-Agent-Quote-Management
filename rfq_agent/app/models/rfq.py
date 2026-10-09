from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class RFQCustomer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    email: Optional[str]


class RFQLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_name: str
    quantity: float
    unit: Optional[str]
    requirements: Optional[str]


class RFQDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    delivery_location: Optional[str]
    required_by_date: Optional[str]
    currency: Optional[str]
    payment_terms: Optional[str]
    quote_validity_days: Optional[int]
    submission_deadline: Optional[str]


class StructuredRFQ(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: RFQCustomer
    rfq: RFQDetails
    line_items: List[RFQLineItem]
    special_requirements: List[str]