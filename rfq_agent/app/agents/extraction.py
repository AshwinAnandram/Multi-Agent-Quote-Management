import json

from openai import OpenAI
from pydantic import TypeAdapter

from app.models.rfq import StructuredRFQ


class RFQExtractionAgent:
    def __init__(
        self,
        client: OpenAI,
        deployment_name: str
    ):
        self.client = client
        self.deployment_name = deployment_name
        self.rfq_schema = TypeAdapter(
            StructuredRFQ
        ).json_schema()

    def extract(self, email_text: str) -> StructuredRFQ:
        response = self.client.responses.create(
            model=self.deployment_name,
            input=[
                {
                    "type": "message",
                    "role": "system",
                    "content": (
                        "You are an RFQ extraction agent. "
                        "Extract information from customer RFQ emails. "
                        "Do not invent information. "
                        "Return data that conforms exactly "
                        "to the supplied schema."
                    )
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": email_text
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "structured_rfq",
                    "schema": self.rfq_schema,
                    "strict": True
                }
            }
        )

        return StructuredRFQ.model_validate(
            json.loads(response.output_text)
        )