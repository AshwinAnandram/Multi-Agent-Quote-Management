import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text

from app.repositories import bid_repository
from app.agents import tools as agent_tools
from app.api import simulation as simulation_api
from app.models.quote import QuoteSimulationRequest
from app.services.pricing_policy import (
    evaluate_quote_policy,
    minimum_quote_price_for_discount,
    minimum_quote_price_for_margin,
    validate_quote_policy,
)


class PricingPolicyValidationTests(unittest.TestCase):
    def setUp(self):
        self.result = {"margin_pct": 40.0, "discount_pct": 20.0}

    def test_compliant_quote_is_accepted(self):
        validate_quote_policy(
            self.result,
            {"min_margin_pct": 35, "max_discount_pct": 25},
        )

    def test_margin_violation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "minimum margin"):
            validate_quote_policy(
                {**self.result, "margin_pct": 34.99},
                {"min_margin_pct": 35, "max_discount_pct": 25},
            )

    def test_discount_violation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "maximum discount"):
            validate_quote_policy(
                {**self.result, "discount_pct": 25.01},
                {"min_margin_pct": 35, "max_discount_pct": 25},
            )

    def test_current_quote_policy_decision_is_structured(self):
        decision = evaluate_quote_policy(
            {"margin_pct": 34.0, "discount_pct": 31.0},
            {
                "pricing_policy_id": 2,
                "min_margin_pct": 30,
                "max_discount_pct": 30,
            },
        )

        self.assertEqual(decision["status"], "REJECTED")
        self.assertEqual(len(decision["reasons"]), 1)
        self.assertIn("maximum discount", decision["reasons"][0])

    def test_missing_policy_is_not_reported_as_compliant(self):
        decision = evaluate_quote_policy(self.result, None)

        self.assertEqual(decision["status"], "NO_POLICY")

    def test_minimum_margin_boundary_is_rounded_up_to_quote_cents(self):
        price = minimum_quote_price_for_margin(58707.72, 35)

        self.assertEqual(price, 90319.57)

        boundary_margin = (price - 58707.72) / price * 100
        below_margin = (price - 0.01 - 58707.72) / (price - 0.01) * 100
        self.assertGreaterEqual(boundary_margin, 35)
        self.assertLess(below_margin, 35)

    def test_minimum_margin_boundary_is_unavailable_for_invalid_policy(self):
        self.assertIsNone(minimum_quote_price_for_margin(100, None))
        self.assertIsNone(minimum_quote_price_for_margin(100, 100))

    def test_maximum_discount_boundary_is_rounded_up_to_quote_cents(self):
        price = minimum_quote_price_for_discount(1000, 25)

        self.assertEqual(price, 750)
        boundary_discount = (1000 - price) / 1000 * 100
        below_discount = (1000 - (price - 0.01)) / 1000 * 100
        self.assertLessEqual(boundary_discount, 25)
        self.assertGreater(below_discount, 25)

    def test_maximum_discount_boundary_supports_customer_policy_value(self):
        price = minimum_quote_price_for_discount(1000, 30)
        self.assertEqual(price, 700)

    def test_maximum_discount_boundary_requires_reference_price_and_policy(self):
        self.assertIsNone(minimum_quote_price_for_discount(0, 25))
        self.assertIsNone(minimum_quote_price_for_discount(1000, None))


class PricingPolicyLookupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE pricing_policies (
                    pricing_policy_id INTEGER PRIMARY KEY,
                    customer_id INTEGER,
                    min_margin_pct REAL,
                    max_discount_pct REAL,
                    is_active BOOLEAN
                )
            """))
            connection.execute(text("""
                INSERT INTO pricing_policies VALUES
                    (1, NULL, 35, 25, TRUE),
                    (2, 12, 30, 30, TRUE),
                    (3, 13, 20, 40, FALSE)
            """))
        self.engine_patch = patch.object(bid_repository, "engine", self.engine)
        self.engine_patch.start()

    def tearDown(self):
        self.engine_patch.stop()
        self.engine.dispose()

    def test_active_customer_policy_takes_precedence(self):
        policy = bid_repository.get_pricing_policy(12)
        self.assertEqual(policy["pricing_policy_id"], 2)
        self.assertEqual(policy["min_margin_pct"], 30)
        self.assertEqual(policy["max_discount_pct"], 30)

    def test_global_policy_is_used_when_customer_policy_is_absent(self):
        policy = bid_repository.get_pricing_policy(14)
        self.assertEqual(policy["pricing_policy_id"], 1)
        self.assertEqual(policy["min_margin_pct"], 35)
        self.assertEqual(policy["max_discount_pct"], 25)


class QuoteEntryPointPolicyTests(unittest.TestCase):
    def setUp(self):
        self.bid = {"bid_id": 99, "customer_id": 12}
        self.policy = {
            "pricing_policy_id": 2,
            "customer_id": 12,
            "min_margin_pct": 30,
            "max_discount_pct": 30,
        }
        self.simulation = {
            "bid_id": 99,
            "margin_pct": 29,
            "discount_pct": 20,
        }

    def test_agent_simulation_rejects_a_policy_violation(self):
        with (
            patch.object(agent_tools, "get_bid_simulation_context_data", return_value=self.bid),
            patch.object(agent_tools, "get_pricing_policy_data", return_value=self.policy),
            patch.object(agent_tools.simulation_service, "simulate", return_value=self.simulation),
        ):
            result = agent_tools.simulate_quote(99, 100)

        self.assertEqual(result["status"], "REJECTED")
        self.assertIn("minimum margin", result["message"])

    def test_api_simulation_rejects_a_policy_violation(self):
        with (
            patch.object(simulation_api, "get_bid_simulation_context_data", return_value=self.bid),
            patch.object(simulation_api, "get_pricing_policy_data", return_value=self.policy),
            patch.object(simulation_api.simulation_service, "simulate", return_value=self.simulation),
        ):
            with self.assertRaises(simulation_api.HTTPException) as raised:
                simulation_api.simulate_quote(
                    99,
                    QuoteSimulationRequest(proposed_quote_price=100),
                )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("minimum margin", raised.exception.detail)

    def test_bid_tool_uses_selected_policy_for_discount_boundary(self):
        bid_detail = {
            "bid_id": 99,
            "customer_id": 12,
            "total_cost": 500.0,
            "deal_size": 1200.0,
            "current_quote_price": 1000.0,
            "current_margin_pct": 50.0,
            "current_discount_pct": 0.0,
            "pricing_policy": self.policy,
        }

        with patch.object(agent_tools, "get_bid_detail", return_value=bid_detail):
            result = agent_tools.get_bid(99)

        boundary = result["bid"]["discount_boundary"]
        self.assertEqual(boundary["status"], "AVAILABLE")
        self.assertEqual(boundary["max_discount_pct"], 30.0)
        self.assertEqual(boundary["minimum_quote_price_within_discount_limit"], 700.0)
        self.assertEqual(boundary["first_cent_below_discount_boundary"], 699.99)


if __name__ == "__main__":
    unittest.main()
