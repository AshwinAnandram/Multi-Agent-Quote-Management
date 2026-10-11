import json
import re

from openai import OpenAI

from app.agents.tools import (
    get_bid,
    simulate_quote,
    lookup_customer_history,
    compare_prices,
    optimize_price
)


class QuotingAgent:

    _OPTIMIZATION_COUNTS = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }

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
            "maximize expected profit",
            "maximize profit",
            "maximum expected profit",
            "maximum profit",
            "highest expected profit",
            "highest profit",
            "profit is maximum",
            "profit is maximized",
            "most profitable prices",
        ]

        if any(
            term in message
            for term in optimization_terms
        ):
            return "optimize_price"

        return None

    def _extract_optimization_count(
        self,
        user_message: str,
    ) -> int | None:
        """Extract an explicit result count near a request for prices."""
        count_pattern = r"(?P<count>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
        item_pattern = r"(?:prices?|quotes?|options?|results?)"
        action_pattern = r"(?:list|give|show|return|provide|find|identify)"

        patterns = (
            rf"\b{action_pattern}\s+(?:me\s+)?(?:the\s+)?{count_pattern}"
            rf"\s+(?:(?:best|optimal|top)\s+)?{item_pattern}\b",
            rf"\btop\s+{count_pattern}\s+{item_pattern}\b",
            rf"\b{count_pattern}\s+(?:best|optimal)\s+{item_pattern}\b",
        )

        message = user_message.lower()
        for pattern in patterns:
            match = re.search(pattern, message)
            if not match:
                continue

            raw_count = match.group("count")
            count = self._OPTIMIZATION_COUNTS.get(raw_count)
            if count is None:
                count = int(raw_count)
            return max(1, min(10, count))

        return None

    def _is_margin_threshold_question(self, user_message: str) -> bool:
        message = user_message.lower()
        asks_about_margin = "margin" in message
        asks_about_price = "price" in message or "quote" in message
        asks_about_boundary = any(
            term in message
            for term in (
                "below",
                "under",
                "minimum",
                "threshold",
                "fall",
                "drop",
                "goes",
            )
        )
        return asks_about_margin and asks_about_price and asks_about_boundary

    def _is_discount_threshold_question(self, user_message: str) -> bool:
        message = user_message.lower()
        asks_about_discount = "discount" in message
        asks_about_price = "price" in message or "quote" in message
        asks_about_boundary = any(
            term in message
            for term in (
                "maximum",
                "max",
                "limit",
                "above",
                "over",
                "exceed",
                "threshold",
                "allowed",
                "goes",
                "below",
            )
        )
        return asks_about_discount and asks_about_price and asks_about_boundary

    def _answer_margin_threshold(self, bid_id: int) -> str:
        result = get_bid(bid_id)
        if result.get("status") != "FOUND":
            return result.get("message", "Bid details are unavailable.")

        bid = result["bid"]
        boundary = bid.get("margin_boundary", {})
        if boundary.get("status") == "NO_FEASIBLE_PRICE":
            return (
                f"Bid {bid_id} has no quote price within its deal-size limit "
                f"that meets the {boundary['min_margin_pct']:.2f}% minimum margin."
            )

        if boundary.get("status") != "AVAILABLE":
            return (
                "I can’t determine the minimum-margin quote boundary: "
                f"{boundary.get('reason', 'the required policy data is unavailable')}"
            )

        minimum_margin_pct = boundary["min_margin_pct"]
        boundary_price = boundary["minimum_quote_price_for_margin"]
        first_below_price = boundary["first_cent_below_margin_boundary"]
        return (
            f"For bid {bid_id}, the applicable minimum margin is "
            f"{minimum_margin_pct:.2f}%. A quote of ${boundary_price:,.2f} "
            f"meets that margin. The first cent-denominated price below the "
            f"boundary, ${first_below_price:,.2f}, falls below the minimum margin."
        )

    def _answer_discount_threshold(self, bid_id: int) -> str:
        result = get_bid(bid_id)
        if result.get("status") != "FOUND":
            return result.get("message", "Bid details are unavailable.")

        bid = result["bid"]
        boundary = bid.get("discount_boundary", {})
        if boundary.get("status") == "NO_FEASIBLE_PRICE":
            return (
                f"Bid {bid_id} has no quote price within its deal-size limit "
                f"that stays within the {boundary['max_discount_pct']:.2f}% "
                "maximum discount."
            )

        if boundary.get("status") != "AVAILABLE":
            return (
                "I can’t determine the maximum-discount quote boundary: "
                f"{boundary.get('reason', 'the required policy data is unavailable')}"
            )

        max_discount_pct = boundary["max_discount_pct"]
        reference_price = boundary["reference_quote_price"]
        boundary_price = boundary["minimum_quote_price_within_discount_limit"]
        first_below_price = boundary["first_cent_below_discount_boundary"]
        return (
            f"For bid {bid_id}, the applicable maximum discount is "
            f"{max_discount_pct:.2f}% of the current quote price "
            f"${reference_price:,.2f}. A quote of ${boundary_price:,.2f} "
            f"is the lowest cent-denominated price within that limit. "
            f"The first cent below it, ${first_below_price:,.2f}, exceeds "
            "the maximum discount."
        )

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

        if self._is_margin_threshold_question(user_message):
            return self._answer_margin_threshold(bid_id)

        if self._is_discount_threshold_question(user_message):
            return self._answer_discount_threshold(bid_id)

        tools = [
            {
                "type": "function",
                "name": "get_bid",
                "description": (
                    "Retrieve authoritative information about a bid. "
                    "Use this when the user asks about the current "
                    "quote, margin, discount, customer, bid status, "
                    "bid date, competitor information, or line items. "
                    "The bid result includes current pricing-policy "
                    "limits and a deterministic policy_decision."
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
                    "recommended, or best price for the bid. "
                    "Accept top_n when the user asks for multiple "
                    "best prices and return ranked feasible results."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "top_n": {
                            "type": "integer",
                            "description": (
                                "How many highest expected-profit "
                                "feasible prices to return. Use the "
                                "count requested by the user; default "
                                "to 1 when no count is stated."
                            ),
                        }
                    },
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
            "Requests for a stated number of prices with maximum, "
            "highest, or greatest profit are optimization requests. "
            "Pass the requested count as top_n and do not ask the user "
            "to repeat a count already provided. Return up to top_n "
            "distinct feasible results in descending expected-profit order. "
            "If fewer feasible results exist, explain how many were found. "

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
            "in a tool result. "

            "For questions about the current quote's margin, discount, "
            "policy limits, or whether the current quote meets policy, "
            "you MUST use get_bid and report its policy_decision exactly. "
            "A REJECTED or NO_POLICY decision must never be described as "
            "compliant or approved. A risk classification cannot change "
            "a pricing-policy decision. For a proposed price, use the "
            "simulation or comparison tool and report its validation result."
        )

        forced_tool = self._detect_forced_tool(
            user_message
        )
        requested_count = self._extract_optimization_count(
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

                    top_n = (
                        requested_count
                        if requested_count is not None
                        else arguments.get("top_n", 1)
                    )
                    top_n = max(1, min(10, int(top_n)))

                    result = optimize_price(
                        bid_id=bid_id,
                        top_n=top_n,
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
