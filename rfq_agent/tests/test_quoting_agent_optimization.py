import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agents.quoting_agent import QuotingAgent


class FakeResponses:
    def __init__(self, requested_count=None):
        arguments = (
            {"top_n": requested_count}
            if requested_count is not None
            else {}
        )
        self.responses = [
            SimpleNamespace(
                id="response-1",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="optimize_price",
                        arguments=json.dumps(arguments),
                        call_id="call-1",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="Optimization results."),
        ]
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class QuotingAgentOptimizationTests(unittest.TestCase):
    def make_agent(self, requested_count=None):
        responses = FakeResponses(requested_count=requested_count)
        client = SimpleNamespace(responses=responses)
        return QuotingAgent(client, "test-deployment"), responses

    def test_maximum_profit_request_forces_optimization(self):
        agent, _ = self.make_agent()

        message = "List three prices at which the profit is maximum"

        self.assertEqual(agent._detect_forced_tool(message), "optimize_price")
        self.assertEqual(agent._extract_optimization_count(message), 3)

    def test_explicit_count_is_forwarded_to_optimizer(self):
        # Even if the model's tool arguments omit or misstate the count,
        # the explicit count in the user's request takes precedence.
        agent, responses = self.make_agent(requested_count=1)

        with patch(
            "app.agents.quoting_agent.optimize_price",
            return_value={"status": "COMPLETED", "optimal_results": []},
        ) as optimize_mock:
            result = agent.run(
                bid_id=10001,
                user_message="List three prices at which the profit is maximum",
            )

        self.assertEqual(result, "Optimization results.")
        optimize_mock.assert_called_once_with(bid_id=10001, top_n=3)
        self.assertEqual(
            responses.calls[0]["tool_choice"],
            {"type": "function", "name": "optimize_price"},
        )

    def test_tool_count_is_capped_at_ten(self):
        agent, _ = self.make_agent(requested_count=20)

        with patch(
            "app.agents.quoting_agent.optimize_price",
            return_value={"status": "COMPLETED", "optimal_results": []},
        ) as optimize_mock:
            agent.run(
                bid_id=10001,
                user_message="Find the maximum profit",
            )

        optimize_mock.assert_called_once_with(bid_id=10001, top_n=10)

    def test_unspecified_count_defaults_to_one(self):
        agent, _ = self.make_agent()

        with patch(
            "app.agents.quoting_agent.optimize_price",
            return_value={"status": "COMPLETED", "optimal_results": []},
        ) as optimize_mock:
            agent.run(bid_id=10001, user_message="Optimize price")

        optimize_mock.assert_called_once_with(bid_id=10001, top_n=1)

    def test_margin_threshold_question_gets_authoritative_boundary_without_llm(self):
        agent = QuotingAgent(client=object(), deployment_name="unused")
        bid_result = {
            "status": "FOUND",
            "bid": {
                "margin_boundary": {
                    "status": "AVAILABLE",
                    "min_margin_pct": 35.0,
                    "minimum_quote_price_for_margin": 90319.57,
                    "first_cent_below_margin_boundary": 90319.56,
                }
            },
        }

        with patch(
            "app.agents.quoting_agent.get_bid",
            return_value=bid_result,
        ) as get_bid_mock:
            answer = agent.run(
                bid_id=10001,
                user_message=(
                    "What is the quote price that goes below the minimum defined margin?"
                ),
            )

        self.assertIn("minimum margin is 35.00%", answer)
        self.assertIn("$90,319.57", answer)
        self.assertIn("$90,319.56", answer)
        get_bid_mock.assert_called_once_with(10001)

    def test_maximum_discount_question_gets_authoritative_boundary_without_llm(self):
        agent = QuotingAgent(client=object(), deployment_name="unused")
        bid_result = {
            "status": "FOUND",
            "bid": {
                "discount_boundary": {
                    "status": "AVAILABLE",
                    "max_discount_pct": 25.0,
                    "reference_quote_price": 1000.0,
                    "minimum_quote_price_within_discount_limit": 750.0,
                    "first_cent_below_discount_boundary": 749.99,
                }
            },
        }

        with patch(
            "app.agents.quoting_agent.get_bid",
            return_value=bid_result,
        ) as get_bid_mock:
            answer = agent.run(
                bid_id=10001,
                user_message="What quote price is at the maximum discount?",
            )

        self.assertIn("maximum discount is 25.00%", answer)
        self.assertIn("$1,000.00", answer)
        self.assertIn("$750.00", answer)
        self.assertIn("$749.99", answer)
        get_bid_mock.assert_called_once_with(10001)


if __name__ == "__main__":
    unittest.main()
