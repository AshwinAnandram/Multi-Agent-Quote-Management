from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI

from app.config import get_required_setting


AZURE_AI_SCOPE = "https://ai.azure.com/.default"


def create_azure_openai_client() -> OpenAI:
    project_endpoint = get_required_setting(
        "AZURE_PROJECT_ENDPOINT"
    )

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        AZURE_AI_SCOPE
    )

    return OpenAI(
        base_url=project_endpoint.rstrip("/") + "/openai/v1",
        api_key=token_provider
    )