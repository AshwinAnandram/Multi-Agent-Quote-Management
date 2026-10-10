import unittest

from app.services.quote_simulation import QuoteSimulationService


class FakePredictionService:
    def __init__(self):
        self.calls = 0

    def predict_win_probability(self, features):
        self.calls += 1
        return 0.6


class QuoteSimulationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.prediction_service = FakePredictionService()
        self.simulation_service = QuoteSimulationService(
            self.prediction_service
        )
        self.bid = {
            "bid_id": 1,
            "total_cost": 80,
            "deal_size": 200,
            "quote_price": 120,
            "experience_years": 5,
            "product_unit_cost": 80,
            "product_list_price": 120,
            "customer_prior_bids": 10,
            "customer_prior_wins": 5,
            "customer_prior_losses": 5,
            "customer_historical_win_rate": 0.5,
            "customer_avg_prior_deal_size": 120,
            "customer_avg_prior_discount": 10,
            "industry": "Software",
            "country": "US",
            "segment": "Enterprise",
            "product_category": "Hardware",
            "competitor_present": True,
        }
        self.policy = {
            "pricing_policy_id": 1,
            "min_margin_pct": 20,
            "max_discount_pct": 15,
        }

    def test_out_of_policy_discount_is_rejected_before_prediction(self):
        with self.assertRaisesRegex(
            ValueError,
            "maximum discount requirement of 15.00%",
        ):
            self.simulation_service.simulate(
                bid=self.bid,
                proposed_quote_price=100,
                pricing_policy=self.policy,
            )

        self.assertEqual(self.prediction_service.calls, 0)

    def test_out_of_policy_margin_is_rejected_before_prediction(self):
        with self.assertRaisesRegex(
            ValueError,
            "minimum margin requirement of 20.00%",
        ):
            self.simulation_service.simulate(
                bid=self.bid,
                proposed_quote_price=90,
                pricing_policy=self.policy,
            )

        self.assertEqual(self.prediction_service.calls, 0)

    def test_compliant_quote_is_simulated(self):
        result = self.simulation_service.simulate(
            bid=self.bid,
            proposed_quote_price=105,
            pricing_policy=self.policy,
        )

        self.assertEqual(result["status"], "VALID")
        self.assertEqual(self.prediction_service.calls, 1)


if __name__ == "__main__":
    unittest.main()
