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
        self.rfq_schema = _make_strict_json_schema(
            TypeAdapter(StructuredRFQ).json_schema()
        )

    def extract(self, email_text: str) -> StructuredRFQ:
        response = self.client.responses.create(
            model=self.deployment_name,
            input=[
                {
                    "type": "message",
                    "role": "system",
                    "content": (
                        "You are an RFQ and bid-outcome extraction agent. "
                        "The customer name means the customer's company or "
                        "organization name, such as DANONE, Nike, Monsanto, "
                        "or Walmart. Extract customer.name only when that "
                        "company name is explicitly stated in the email body. "
                        "Do not use the sender's personal name, sender email "
                        "address, or subject line as the customer name. If the "
                        "body does not explicitly identify the company, return "
                        "null for customer.name. "
                        "Extract RFQ details and quoted prices or terms "
                        "from a single email or document source. Also extract "
                        "a bid outcome only when the source explicitly identifies "
                        "a bid ID and clearly states WON or LOST. For a won outcome, "
                        "extract the customer's final accepted quote price when stated. "
                        "For a lost outcome, extract the stated reason. Do not infer "
                        "an outcome, bid ID, price, or reason. "
                        "Do not invent information. "
                        "Leave missing values empty. Do not reconcile this "
                        "source with any other source. "
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


def _make_strict_json_schema(schema: dict) -> dict:
    """Require every object property for strict structured JSON output.

    Pydantic represents fields with defaults as optional in JSON Schema. The
    strict Responses API format requires every property to be listed in
    ``required``; nullable types still represent values the model may not know.
    """
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            schema["required"] = list(properties)
            schema["additionalProperties"] = False
        for value in schema.values():
            _make_strict_json_schema(value)
    elif isinstance(schema, list):
        for value in schema:
            _make_strict_json_schema(value)
    return schema
