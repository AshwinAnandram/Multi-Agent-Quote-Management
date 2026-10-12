import unittest
from unittest.mock import MagicMock

from app.agents.extraction import RFQExtractionAgent
from app.models.rfq import StructuredRFQ


class RFQExtractionSchemaTests(unittest.TestCase):
    def setUp(self):
        self.agent = RFQExtractionAgent(client=object(), deployment_name="test")

    def test_every_object_property_is_required_for_strict_output(self):
        self._assert_object_properties_required(self.agent.rfq_schema)

    def test_nullable_fields_remain_nullable(self):
        schema = self.agent.rfq_schema
        nullable_fields = [
            schema["$defs"]["RFQCustomer"]["properties"]["name"],
            schema["$defs"]["RFQCustomer"]["properties"]["email"],
            schema["$defs"]["RFQDetails"]["properties"]["subject"],
            schema["$defs"]["RFQLineItem"]["properties"]["product_name"],
            schema["$defs"]["BidOutcome"]["properties"]["bid_id"],
            schema["$defs"]["BidOutcome"]["properties"]["status"],
            schema["$defs"]["BidOutcome"]["properties"]["final_quote_price"],
            schema["$defs"]["BidOutcome"]["properties"]["lost_reason"],
        ]

        for field in nullable_fields:
            with self.subTest(field=field):
                self.assertIn("null", {variant.get("type") for variant in field["anyOf"]})

    def test_strict_output_with_unknown_values_validates(self):
        extracted = StructuredRFQ.model_validate({
            "customer": {"name": None, "email": None},
            "bid_outcome": {
                "bid_id": None,
                "status": None,
                "final_quote_price": None,
                "lost_reason": None,
            },
            "rfq": {
                "subject": None,
                "delivery_location": None,
                "required_by_date": None,
                "currency": None,
                "payment_terms": None,
                "quote_validity_days": None,
                "submission_deadline": None,
                "quote_total": None,
                "deal_size": None,
                "quote_reference": None,
            },
            "line_items": [],
            "special_requirements": [],
        })

        self.assertIsNone(extracted.customer.name)
        self.assertIsNone(extracted.rfq.subject)
        self.assertIsNone(extracted.bid_outcome.bid_id)
        self.assertIsNone(extracted.bid_outcome.status)
        self.assertEqual(extracted.line_items, [])

    def test_customer_name_is_company_name_taken_only_from_email_body(self):
        client = MagicMock()
        client.responses.create.return_value.output_text = (
            '{"customer":{"name":null,"email":null},"rfq":{},'
            '"bid_outcome":{},"line_items":[],"special_requirements":[]}'
        )
        agent = RFQExtractionAgent(client=client, deployment_name="test")

        agent.extract("Subject: Walmart RFQ\\nFrom: buyer@example.com\\nBody: Hello")

        instructions = client.responses.create.call_args.kwargs["input"][0]["content"]
        self.assertIn("company or organization name", instructions)
        self.assertIn("explicitly stated in the email body", instructions)
        self.assertIn("Do not use", instructions)
        self.assertIn("subject line", instructions)

    def _assert_object_properties_required(self, value):
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                self.assertEqual(set(value.get("required", [])), set(properties))
                self.assertIs(value.get("additionalProperties"), False)
            for nested in value.values():
                self._assert_object_properties_required(nested)
        elif isinstance(value, list):
            for nested in value:
                self._assert_object_properties_required(nested)


if __name__ == "__main__":
    unittest.main()
