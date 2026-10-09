from fastapi import APIRouter, HTTPException

from app.azure_client import (
    create_azure_openai_client
)
from app.config import (
    get_required_setting
)
from app.agents.quoting_agent import (
    QuotingAgent
)
from app.models.copilot import (
    CopilotRequest,
    CopilotResponse
)


router = APIRouter(
    prefix="/bids",
    tags=["copilot"]
)


client = create_azure_openai_client()

quoting_agent = QuotingAgent(
    client=client,
    deployment_name=get_required_setting(
        "AZURE_OPENAI_DEPLOYMENT"
    )
)


@router.post(
    "/{bid_id}/copilot",
    response_model=CopilotResponse
)
def copilot(
    bid_id: int,
    request: CopilotRequest
):

    if not request.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Copilot message cannot be empty."
        )

    try:

        response = quoting_agent.run(
            bid_id=bid_id,
            user_message=request.message
        )

        return CopilotResponse(
            bid_id=bid_id,
            message=response
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )