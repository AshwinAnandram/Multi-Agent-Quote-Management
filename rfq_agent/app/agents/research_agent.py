import json

from openai import OpenAI

from app.agents.tools import lookup_customer_history


class ResearchAgent:

    def __init__(
        self,
        client: OpenAI,
        deployment_name: str
    ):
        self.client = client
        self.deployment_name = deployment_name

    def run(
        self,
        bid_id: int,
        user_message: str
    ) -> str:

        tools = [
            {
                "type": "function",
                "name": "lookup_customer_history",
                "description": (
                    "Retrieve historical customer performance "
                    "for a bid, including prior bids, wins, "
                    "losses, historical win rate, average prior "
                    "deal size, and average prior discount."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "bid_id": {
                            "type": "integer",
                            "description": "The bid ID."
                        }
                    },
                    "required": ["bid_id"],
                    "additionalProperties": False
                }
            }
        ]

        instructions = """
                        You are the Research Agent in an enterprise
                        quote management system.

                        Your responsibility is to retrieve and explain
                        customer historical information.

                        You can provide:

                        - Customer historical win rate
                        - Previous bids
                        - Previous wins
                        - Previous losses
                        - Average prior deal size
                        - Average prior discount
                        - Other customer historical information returned
                          by the customer history tool

                        Rules:

                        - Use the customer history tool when historical
                          information is required.
                        - Treat tool results as authoritative.
                        - Do not calculate or invent historical metrics.
                        - Do not make pricing recommendations.
                        - Do not optimize quote prices.
                        - Do not simulate quote prices.
                        - Do not recommend discounts.
                        - Do not make statements about the best price to quote.
                        - Do not ask the sales representative whether they
                          want a price recommendation.
                        - Stay within the research domain.
                        - Explain the retrieved information clearly and
                          concisely.
                        """

        response = self.client.responses.create(
            model=self.deployment_name,
            instructions=instructions,
            input=(
                f"Bid ID: {bid_id}\n\n"
                f"Sales representative request:\n"
                f"{user_message}"
            ),
            tools=tools,
            tool_choice="required"
        )

        while True:

            function_calls = [
                item
                for item in response.output
                if item.type == "function_call"
            ]

            if not function_calls:
                return response.output_text

            tool_outputs = []

            for call in function_calls:

                arguments = json.loads(call.arguments)

                if call.name == "lookup_customer_history":
                    result = lookup_customer_history(
                        bid_id=arguments["bid_id"]
                    )
                else:
                    result = {
                        "status": "REJECTED",
                        "message": (
                            f"Unknown research tool: "
                            f"{call.name}"
                        )
                    }

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(
                            result,
                            default=str
                        )
                    }
                )

            response = self.client.responses.create(
                model=self.deployment_name,
                instructions=instructions,
                previous_response_id=response.id,
                input=tool_outputs
            )