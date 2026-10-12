import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.api import rfqs
from app.repositories.rfq_repository import _rfq_list_fields


class RejectedRFQEndpointTests(unittest.TestCase):
    def test_rejected_endpoint_returns_rejected_list(self):
        expected = {"total": 1, "rfqs": [{"rfq_id": 10003, "processing_status": "REJECTED"}]}
        with patch.object(rfqs, "list_rejected_rfqs", return_value=expected) as list_rejected:
            result = rfqs.get_rejected(page=2, page_size=50)

        self.assertEqual(result, expected)
        list_rejected.assert_called_once_with(2, 50)

    def test_rejected_endpoint_rejects_invalid_pagination(self):
        with self.assertRaises(HTTPException) as raised:
            rfqs.get_rejected(page=0, page_size=25)

        self.assertEqual(raised.exception.status_code, 400)

    def test_reject_endpoint_persists_the_supplied_reason(self):
        with patch.object(rfqs, "reject_rfq", return_value=True) as reject_rfq:
            result = rfqs.reject(10003, rfqs.RejectRequest(reason="Customer withdrew request"))

        self.assertEqual(result, {"rfq_id": 10003, "status": "REJECTED"})
        reject_rfq.assert_called_once_with(10003, "Customer withdrew request")

    def test_review_endpoint_exposes_the_saved_rejection_reason(self):
        rejected = {"rfq_id": 10003, "processing_status": "REJECTED", "rejection_reason": "Customer withdrew request"}
        with patch.object(rfqs, "get_rfq_review", return_value=rejected):
            result = rfqs.get_review(10003)

        self.assertEqual(result["rejection_reason"], "Customer withdrew request")

    def test_rejected_list_reads_reason_from_database_column(self):
        row = {
            "rfq_id": 10003,
            "received_date": None,
            "required_by_date": None,
            "delivery_location": None,
            "rfq_description": "RFQ",
            "processing_status": "REJECTED",
            "extracted_json": {
                "review_decision": {"reason": "Legacy JSON reason"},
                "intake": {"merged": {"customer": {"name": "Example Customer"}}},
            },
            "rejection_reason": "Database column reason",
            "line_items": [],
        }

        result = _rfq_list_fields(row, {"example customer"})

        self.assertEqual(result["rejection_reason"], "Database column reason")


if __name__ == "__main__":
    unittest.main()
