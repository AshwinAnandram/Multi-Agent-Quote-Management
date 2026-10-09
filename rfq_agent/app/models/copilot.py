from pydantic import BaseModel


class CopilotRequest(BaseModel):
    message: str


class CopilotResponse(BaseModel):
    bid_id: int
    message: str