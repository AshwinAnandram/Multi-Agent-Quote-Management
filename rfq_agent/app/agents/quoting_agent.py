import json

from openai import OpenAI

from app.agents.tools import (
    get_bid,
    simulate_quote,
    lookup_customer_history,
    compare_prices,
    optimize_price
)


class QuotingAgent:

    def __init__(
        self,
        client: OpenAI,
        deployment_name: str
    ):
        self.client = client
        self.deployment_name = deployment_name

    def _detect_forced_tool(
        self,
        user_message: str
    ) -> str | None:

        message = user_message.lower()

        optimization_terms = [
            "optimal price",
            "optimal pricing",
            "optimize price",
            "optimize pricing",
            "best price",
            "recommended price",
            "recommend a price",
            "what price should",
            "price that maximizes",
            "maximize expected profit"
        ]

        if any(
            term in message
            for term in optimization_terms
        ):
            return "optimize_price"

        return None

    def synthesize(
        self,
        bid_id: int,
        user_message: str,
        specialist_results: dict,
    ) -> str:
        system_prompt = (
            "You are a sales quoting copilot responsible for synthesizing "
            "specialist findings into a clear, accurate response. "
            "Risk results may contain multiple assessments, one per proposed price. "
            "Match each assessment to its proposed quote price using the evidence "
            "provided. Report the risk classification for each price separately. "
            "Do not describe a price as safe or compliant unless the evidence "
            "explicitly supports that conclusion. "
            "Use the supplied specialist results as the sole authoritative "
            "source for pricing metrics, risk assessments, and recommendations. "
            "Do not call tools or recalculate any values. "
            "Do not replace adjusted prices with the original proposed prices. "
            "Clearly distinguish original prices from adjusted prices when relevant. "
            "State which proposed prices were actually assessed for risk. "
            "Do not imply that a risk assessment covers prices that were not evaluated. "
            "If a price violates a pricing policy, explicitly identify the violation "
            "when that information appears in the specialist results. "
            "If specialist findings are incomplete or conflict, state that limitation "
            "rather than inventing or reconciling unsupported values."
        )

        response = self.client.responses.create(
            model=self.deployment_name,
            input=[
                {
                    "type": "message",
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": (
                        f"Bid ID: {bid_id}\n"
                        f"User request: {user_message}\n\n"
                        f"Specialist results:\n"
                        f"{json.dumps(specialist_results, default=str)}"
                    ),
                },
            ],
        )

        return response.output_text


    def run(
        self,
        bid_id: int,
        user_message: str
    ) -> str:

        tools = [
            {
                "type": "function",
                "name": "get_bid",
                "description": (
                    "Retrieve authoritative information about a bid. "
                    "Use this when the user asks about the current "
                    "quote, margin, discount, customer, bid status, "
                    "bid date, competitor information, or line items."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
            },
            {
                "type": "function",
                "name": "simulate_quote",
                "description": (
                    "Simulate a proposed quote price for a specific bid. "
                    "This tool is mandatory whenever the user asks "
                    "what happens if they quote a specific price. "
                    "The tool performs business-rule validation, "
                    "pricing calculations, margin calculations, "
                    "win-probability prediction, and expected-profit "
                    "calculations."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "proposed_quote_price": {
                            "type": "number",
                            "description": (
                                "The exact proposed quote price "
                                "to simulate."
                            )
                        }
                    },
                    "required": [
                        "proposed_quote_price"
                    ],
                    "additionalProperties": False
                }
            },
            {
                "type": "function",
                "name": "compare_prices",
                "description": (
                    "Compare multiple proposed quote prices for the current bid. "
                    "Use this when the user asks to compare two or more prices "
                    "or asks how different pricing scenarios perform. "
                    "The tool returns the calculated discount, margin, "
                    "win probability, expected profit, and validation status "
                    "for each proposed price."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "proposed_quote_prices": {
                            "type": "array",
                            "items": {
                                "type": "number"
                            },
                            "description": (
                                "The proposed quote prices to compare."
                            )
                        }
                    },
                    "required": [
                        "proposed_quote_prices"
                    ],
                    "additionalProperties": False
                }
            },
            {
                "type": "function",
                "name": "optimize_price",
                "description": (
                    "Find the quote price that maximizes expected profit "
                    "for the current bid while respecting the applicable "
                    "commercial pricing policy. "
                    "The policy may be customer-specific or global. "
                    "Use this when the user asks for the optimal, "
                    "recommended, or best price for the bid."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
            },
            {
                "type": "function",
                "name": "lookup_customer_history",
                "description": (
                    "Retrieve historical performance information "
                    "for the customer associated with the current bid. "
                    "Use this when the user asks about previous bids, "
                    "previous wins or losses, historical win rate, "
                    "historical deal size, or historical discount."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
            }
        ]

        system_prompt = (
            "You are a sales quoting copilot. "
            "You help sales representatives evaluate bids "
            "and quote scenarios. "

            "TOOL SELECTION RULES: "

            "If the user asks for current bid information, "
            "use the get_bid tool. "

            "If the user asks about historical customer performance, "
            "previous bids, previous wins or losses, historical win rate, "
            "historical deal size, or historical discount, "
            "use the lookup_customer_history tool. "

            "If the user asks what happens at a specific proposed "
            "quote price, use the simulate_quote tool. "

            "If the user asks to compare multiple proposed quote prices, "
            "use the compare_prices tool. "

            "If the user asks for the optimal price, best price, "
            "recommended price, price that maximizes expected profit, "
            "or asks what price should be quoted, "
            "you MUST use the optimize_price tool. "

            "A bid being closed, won, lost, or having an existing quote "
            "does NOT prevent the optimize_price tool from being used. "

            "Do not refuse price optimization because of the current "
            "bid status unless a tool explicitly reports that optimization "
            "is not possible. "

            "Never calculate discount, margin, win probability, "
            "or expected profit yourself. "

            "Never estimate or approximate these values from "
            "information in the conversation. "

            "Tool results are the sole authoritative source "
            "for bid, pricing, policy, and optimization information. "

            "Never override, reinterpret, contradict, "
            "or replace a tool result. "

            "Never invent a value that is not present "
            "in a tool result."
        )

        response = self.client.responses.create(
            model=self.deployment_name,
            input=[
                {
                    "type": "message",
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": (
                        f"The current bid ID is {bid_id}. "
                        f"The sales representative says: "
                        f"{user_message}"
                    )
                }
            ],
            tools=tools,
            tool_choice="required"
        )

        forced_tool = self._detect_forced_tool(
            user_message
        )

        tool_choice = (
            {
                "type": "function",
                "name": forced_tool
            }
            if forced_tool
                else "required"
            )

        response = self.client.responses.create(
            model=self.deployment_name,
            input=[
                {
                    "type": "message",
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": (
                        f"The current bid ID is {bid_id}. "
                        f"The sales representative says: "
                        f"{user_message}"
                    )
                }
            ],
            tools=tools,
            tool_choice=tool_choice
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

            for item in function_calls:

                arguments = json.loads(
                    item.arguments
                )

                if item.name == "get_bid":

                    result = get_bid(
                        bid_id=bid_id
                    )

                elif item.name == "simulate_quote":

                    proposed_quote_price = float(
                        arguments[
                            "proposed_quote_price"
                        ]
                    )

                    result = simulate_quote(
                        bid_id=bid_id,
                        proposed_quote_price=(
                            proposed_quote_price
                        )
                    )

                elif item.name == "compare_prices":

                    proposed_quote_prices = [
                        float(price)
                        for price in arguments[
                            "proposed_quote_prices"
                        ]
                    ]

                    result = compare_prices(
                    bid_id=bid_id,
                    proposed_quote_prices=proposed_quote_prices
                )

                elif item.name == "optimize_price":

                    result = optimize_price(
                        bid_id=bid_id
                    )

                elif item.name == "lookup_customer_history":

                    result = lookup_customer_history(bid_id=bid_id)

                else:

                    result = {
                        "status": "ERROR",
                        "message": (
                            f"Unknown tool: {item.name}"
                        )
                    }

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": json.dumps(
                            result,
                            default=str
                        )
                    }
                )

            response = self.client.responses.create(
                model=self.deployment_name,
                previous_response_id=response.id,
                input=tool_outputs
            )