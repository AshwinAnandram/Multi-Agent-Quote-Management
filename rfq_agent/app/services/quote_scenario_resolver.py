import re
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from app.agents.tools import get_bid


class QuoteScenario(BaseModel):
    intent: Literal[
        "SPECIFIC_PRICE",
        "PRICE_COMPARISON",
        "DISCOUNT_SCENARIO",
        "OPTIMIZATION",
        "CURRENT_QUOTE",
        "GENERAL_ANALYSIS",
        "CLARIFY",
    ]
    proposed_quote_prices: list[float] = Field(default_factory=list)
    discount_pct: float | None = None
    discount_basis: Literal[
        "CURRENT_QUOTE",
        "EACH_PROPOSED_PRICE",
    ] | None = None
    optimization_count: int = Field(default=1, ge=1, le=10)
    requested_analysis: list[
        Literal["pricing", "risk", "research", "recommendation"]
    ] = Field(default_factory=list)
    clarification_question: str | None = None
    reasoning: str


class QuoteScenarioResolver:
    def __init__(
        self,
        client: OpenAI,
        deployment_name: str,
    ):
        self.client = client
        self.deployment_name = deployment_name

    def _normalize_proposed_price_discount(
        self,
        result: dict,
        user_message: str,
    ) -> dict:
        message = user_message.lower()

        mentions_discount = (
            "discount" in message or "%" in message
        )

        mentions_current_quote = any(
            phrase in message
            for phrase in [
                "current quote",
                "existing quote",
                "current price",
                "existing price",
            ]
        )

        if (
            mentions_discount
            and not mentions_current_quote
            and result["proposed_quote_prices"]
        ):
            match = re.search(
                r"(\d+(?:\.\d+)?)\s*%",
                user_message,
            )

            if match:
                discount_pct = float(match.group(1))

                result["intent"] = "DISCOUNT_SCENARIO"
                result["discount_pct"] = discount_pct
                result["discount_basis"] = "EACH_PROPOSED_PRICE"
                result["clarification_question"] = None
                result["reasoning"] = (
                    "An explicit discount applies to each proposed price."
                )

        return result


    def _normalize_current_quote_discount(
        self,
        result: dict,
        user_message: str,
    ) -> dict:
        message = user_message.lower()

        mentions_discount = (
            "discount" in message or "%" in message
        )
        mentions_current_quote = any(
            phrase in message
            for phrase in [
                "current quote",
                "existing quote",
                "current price",
                "existing price",
            ]
        )
        mentions_risk = "risk" in message

        if (
            result["intent"] == "CLARIFY"
            and mentions_discount
            and mentions_current_quote
            and mentions_risk
        ):
            result["intent"] = "DISCOUNT_SCENARIO"
            result["discount_basis"] = "CURRENT_QUOTE"
            result["requested_analysis"] = ["risk"]
            result["clarification_question"] = None

            if result["discount_pct"] is None:
                match = re.search(
                    r"(\d+(?:\.\d+)?)\s*%",
                    user_message,
                )
                if match:
                    result["discount_pct"] = float(match.group(1))

            result["reasoning"] = (
                "The request specifies a discount on the current "
                "quote and asks for a risk assessment."
            )

        return result

    def _get_current_quote(self, bid_id: int) -> float:
        bid_result = get_bid(bid_id=bid_id)

        if not isinstance(bid_result, dict):
            raise ValueError(
                "Unable to retrieve authoritative bid information."
            )

        if bid_result.get("status") != "FOUND":
            raise ValueError(
                f"Unable to retrieve bid {bid_id}: "
                f"{bid_result.get('status', 'UNKNOWN')}"
            )

        bid_data = bid_result.get("bid")

        if not isinstance(bid_data, dict):
            raise ValueError(
                "The bid details are missing from the bid response."
            )

        current_quote = bid_data.get("current_quote_price")

        if current_quote is None:
            raise ValueError(
                "The current quote price is missing from bid data."
            )

        current_quote = float(current_quote)

        if current_quote <= 0:
            raise ValueError(
                "The current quote price must be greater than zero."
            )

        return current_quote

    def resolve(
        self,
        bid_id: int,
        user_message: str,
    ) -> dict:
        response = self.client.responses.parse(
            model=self.deployment_name,
            instructions=(
                "You are a quote scenario resolver for an enterprise "
                "RFQ and quote management system. Classify the user's "
                "request into a QuoteScenario. Do not invent bid data "
                "or calculate prices. "
                "Use SPECIFIC_PRICE for one explicit proposed price. "
                "Use PRICE_COMPARISON for two or more explicit prices "
                "to compare. Use DISCOUNT_SCENARIO when a discount is "
                "requested. Set discount_basis to CURRENT_QUOTE when "
                "the discount applies to the current or existing quote, "
                "or EACH_PROPOSED_PRICE when it applies to explicitly "
                "provided prices. Use OPTIMIZATION when the user asks "
                "for the best or optimal price. Set optimization_count "
                "to the requested number of optimal prices. Use "
                "CURRENT_QUOTE for requests about the current quote, "
                "GENERAL_ANALYSIS for general analysis, and CLARIFY "
                "when essential information is missing. Include the "
                "applicable requested_analysis values: pricing, risk, "
                "research, recommendation. Preserve all explicit prices. "
                "If a discount applies to provided prices, identify the "
                "basis clearly so prices are not discounted twice."
            ),
            input=(
                f"Bid ID: {bid_id}\n"
                f"User request: {user_message}"
            ),
            text_format=QuoteScenario,
        )

        scenario = response.output_parsed

        if scenario is None:
            raise ValueError(
                "The model did not return a valid quote scenario."
            )

        result = scenario.model_dump()

        result = self._normalize_current_quote_discount(
            result=result,
            user_message=user_message,
        )

        result = self._normalize_proposed_price_discount(
            result=result,
            user_message=user_message,
        )

        intent = result["intent"]
        prices = result["proposed_quote_prices"]
        discount_pct = result["discount_pct"]
        discount_basis = result["discount_basis"]

        if any(price <= 0 for price in prices):
            raise ValueError(
                "Proposed quote prices must be greater than zero."
            )

        if discount_pct is not None and not 0 <= discount_pct <= 100:
            raise ValueError(
                "Discount percentage must be between 0 and 100."
            )

        if intent == "SPECIFIC_PRICE" and len(prices) != 1:
            raise ValueError(
                "SPECIFIC_PRICE requires exactly one proposed price."
            )

        if intent == "PRICE_COMPARISON" and len(prices) < 2:
            raise ValueError(
                "PRICE_COMPARISON requires at least two proposed prices."
            )

        if intent == "DISCOUNT_SCENARIO":
            if discount_pct is None:
                raise ValueError(
                    "A discount scenario requires a discount percentage."
                )

            if discount_basis is None:
                raise ValueError(
                    "A discount scenario requires a discount basis."
                )

            if discount_basis == "CURRENT_QUOTE":
                current_quote = self._get_current_quote(bid_id)

                proposed_price = round(
                    current_quote * (1 - discount_pct / 100),
                    2,
                )

                result["current_quote_price"] = current_quote
                result["proposed_quote_prices"] = [proposed_price]

            elif discount_basis == "EACH_PROPOSED_PRICE":
                if not prices:
                    raise ValueError(
                        "A discount on proposed prices requires "
                        "at least one explicit proposed price."
                    )

                result["proposed_quote_prices"] = [
                    round(price * (1 - discount_pct / 100), 2)
                    for price in prices
                ]

        if intent == "OPTIMIZATION":
            result["optimization_count"] = max(
                1,
                min(10, int(result["optimization_count"])),
            )

        return result


def resolve_quote_scenario(
    bid_id: int,
    user_message: str,
    client: OpenAI,
    deployment_name: str,
) -> dict:
    resolver = QuoteScenarioResolver(
        client=client,
        deployment_name=deployment_name,
    )

    return resolver.resolve(
        bid_id=bid_id,
        user_message=user_message,
    )