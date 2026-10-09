from pydantic import BaseModel, Field


class QuoteSimulationRequest(BaseModel):
    proposed_quote_price: float = Field(gt=0)


class ApplyPriceRequest(BaseModel):
    proposed_quote_price: float = Field(gt=0)
    source: str = Field(min_length=1, max_length=30)
    created_by: str = Field(min_length=1, max_length=100)