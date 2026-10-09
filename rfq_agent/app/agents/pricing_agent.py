import json
import re

from openai import OpenAI

from app.agents.tools import (
    compare_prices,
    optimize_price,
    simulate_quote,
)


class PricingAgent:

    def __init__(
        self,
        client: OpenAI,
        deployment_name: str
    ):
        self.client = client
        self.deployment_name = deployment_name

    def _extract_prices(
        self,
        user_message: str
    ) -> list[float]:

        pattern = (
            r"(?:\$|USD\s*)?"
            r"(\d+(?:,\d{3})*(?:\.\d+)?)"
        )

        matches = re.findall(
            pattern,
            user_message
        )

        prices = []

        for match in matches:
            value = match.replace(",", "")
            prices.append(float(value))

        return prices

    def _detect_intent(
        self,
        user_message: str
    ) -> tuple[str, list[float]]:

        message = user_message.lower()
        prices = self._extract_prices(user_message)

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
        ]

        if any(
            term in message
            for term in optimization_terms
        ):
            return "optimize_price", prices

        comparison_terms = [
            "compare",
            "comparison",
            "compare prices",
            "compare quotes",
            "which price is better",
            "which quote is better",
        ]

        if (
            any(
                term in message
                for term in comparison_terms
            )
            and len(prices) >= 2
        ):
            return "compare_prices", prices

        if len(prices) >= 1:
            return "simulate_quote", prices

        return "unknown", []

    def _explain_result(
        self,
        bid_id: int,
        user_message: str,
        tool_result: dict
    ) -> str:

        response = self.client.responses.create(
            model=self.deployment_name,
            instructions=
                        """
                            You are the Pricing Agent in an enterprise
                            quote management system.

                            Your responsibility is to evaluate quote pricing.

                            You can:

                            - Simulate a proposed quote price.
                            - Compare multiple proposed quote prices.
                            - Optimize the quote price.
                            - Explain pricing policy constraints.
                            - Explain win probability and expected profit
                              returned by the pricing tools.

                            Rules:

                            - The pricing tool result is authoritative.
                            - Do not recalculate pricing metrics.
                            - Do not change any numbers.
                            - Do not invent additional metrics.
                            - Do not answer customer-history questions.
                            - Do not perform customer research.
                            - Do not make statements about customer history
                              unless that information is explicitly supplied
                              in the pricing context.
                            - Do not tell the sales representative that another
                              agent needs to provide information.
                            - Stay within the pricing domain.
                            - Explain the pricing result clearly and concisely.
                        """,
            input=(
                f"Bid ID: {bid_id}\n\n"
                f"Sales representative request:\n"
                f"{user_message}\n\n"
                f"Authoritative pricing result:\n"
                f"{json.dumps(tool_result, default=str)}"
            ),
        )

        return response.output_text


    def run(
        self,
        bid_id: int,
        user_message: str,
        quote_scenario: dict | None = None,
    ) -> str:

        if quote_scenario:
            scenario_intent = quote_scenario.get("intent")
            prices = quote_scenario.get("proposed_quote_prices", [])

            if scenario_intent == "SPECIFIC_PRICE" and prices:
                intent = "simulate_quote"

            elif scenario_intent == "PRICE_COMPARISON" and len(prices) >= 2:
                intent = "compare_prices"

            elif scenario_intent == "DISCOUNT_SCENARIO" and prices:
                if len(prices) >= 2:
                    intent = "compare_prices"
                else:
                    intent = "simulate_quote"

            elif scenario_intent == "OPTIMIZATION":
                intent = "optimize_price"

            else:
                intent = "unknown"

        else:
            intent, prices = self._detect_intent(user_message)

        if intent == "simulate_quote":
            result = simulate_quote(
                bid_id=bid_id,
                proposed_quote_price=prices[0],
            )

            return self._explain_result(
                bid_id=bid_id,
                user_message=user_message,
                tool_result=result,
            )

        if intent == "compare_prices":
            result = compare_prices(
                bid_id=bid_id,
                proposed_quote_prices=prices,
            )

            return self._explain_result(
                bid_id=bid_id,
                user_message=user_message,
                tool_result=result,
            )

        if intent == "optimize_price":
            optimization_count = (
                quote_scenario.get("optimization_count", 1)
                if quote_scenario
                else 1
            )

            result = optimize_price(
                bid_id=bid_id,
                step=500.0,
                top_n=optimization_count,
            )

            return self._explain_result(
                bid_id=bid_id,
                user_message=user_message,
                tool_result=result,
            )

        return (
            "I need a specific quote price, a set of "
            "prices to compare, or a request to optimize "
            "the quote price."
        )
