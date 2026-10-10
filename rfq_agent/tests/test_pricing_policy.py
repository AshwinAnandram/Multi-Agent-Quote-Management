import unittest

from app.services.pricing_policy import (
    get_policy_limits,
    validate_quote_policy,
)


class PricingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = {
            "pricing_policy_id": 1,
            "min_margin_pct": 20,
            "max_discount_pct": 15,
        }

    def test_policy_boundaries_are_accepted(self):
        validate_quote_policy(
            margin_pct=20,
            discount_pct=15,
            pricing_policy=self.policy,
        )

    def test_margin_below_minimum_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "minimum margin requirement of 20.00%",
        ):
            validate_quote_policy(
                margin_pct=19.99,
                discount_pct=10,
                pricing_policy=self.policy,
            )

    def test_discount_above_maximum_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "maximum discount requirement of 15.00%",
        ):
            validate_quote_policy(
                margin_pct=25,
                discount_pct=15.01,
                pricing_policy=self.policy,
            )

    def test_missing_policy_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "No applicable pricing policy",
        ):
            get_policy_limits(None)

    def test_missing_margin_limit_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "does not define a minimum margin",
        ):
            get_policy_limits({
                "max_discount_pct": 15,
            })

    def test_missing_discount_limit_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "does not define a maximum discount",
        ):
            get_policy_limits({
                "min_margin_pct": 20,
            })

    def test_non_finite_threshold_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "invalid margin or discount thresholds",
        ):
            get_policy_limits({
                "min_margin_pct": float("nan"),
                "max_discount_pct": 15,
            })


if __name__ == "__main__":
    unittest.main()
