import unittest
from unittest.mock import MagicMock, patch

from app.repositories import bid_repository
from app.services.rfq_intake import resolve_bid_outcome
from app.services import bid_service
from app.workers import gmail_rfq_intake


class BidOutcomeExtractionTests(unittest.TestCase):
    def test_won_outcome_with_bid_id_and_final_price_is_matchable(self):
        result = resolve_bid_outcome({
            "merged": {"bid_outcome": {
                "bid_id": 10001,
                "status": "WON",
                "final_quote_price": 92000,
                "lost_reason": None,
            }},
            "conflicts": [],
        })

        self.assertEqual(result, {
            "bid_id": 10001,
            "status": "WON",
            "final_quote_price": 92000,
            "lost_reason": None,
            "missing_fields": [],
        })

    def test_lost_outcome_without_reason_is_matchable_and_flagged(self):
        result = resolve_bid_outcome({
            "merged": {"bid_outcome": {
                "bid_id": 10002,
                "status": "LOST",
                "final_quote_price": None,
                "lost_reason": None,
            }},
            "conflicts": [],
        })

        self.assertEqual(result["status"], "LOST")
        self.assertEqual(result["lost_reason"], None)
        self.assertEqual(result["missing_fields"], ["lost_reason"])

    def test_missing_won_price_is_flagged_without_blocking_outcome(self):
        result = resolve_bid_outcome({
            "merged": {"bid_outcome": {
                "bid_id": 10003,
                "status": "WON",
                "final_quote_price": None,
                "lost_reason": None,
            }},
            "conflicts": [],
        })

        self.assertEqual(result["status"], "WON")
        self.assertEqual(result["missing_fields"], ["final_quote_price"])

    def test_conflicting_bid_id_or_status_is_not_auto_matched(self):
        base = {"merged": {"bid_outcome": {
            "bid_id": 10004,
            "status": "WON",
            "final_quote_price": 10,
            "lost_reason": None,
        }}}
        for field in ("bid_outcome.bid_id", "bid_outcome.status"):
            with self.subTest(field=field):
                self.assertIsNone(resolve_bid_outcome({
                    **base,
                    "conflicts": [{"field": field}],
                }))

    def test_conflicting_final_price_is_flagged_and_not_used(self):
        result = resolve_bid_outcome({
            "merged": {"bid_outcome": {
                "bid_id": 10005,
                "status": "WON",
                "final_quote_price": 10,
                "lost_reason": None,
            }},
            "conflicts": [{"field": "bid_outcome.final_quote_price"}],
        })

        self.assertIsNone(result["final_quote_price"])
        self.assertEqual(result["missing_fields"], ["final_quote_price"])


class ClosedBidOutcomeRepositoryTests(unittest.TestCase):
    def test_won_outcome_creates_quote_version_without_policy_validation(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(mappings=MagicMock(return_value=MagicMock(first=MagicMock(return_value={
                "bid_id": 10006,
                "status": "CLOSED",
                "total_cost": 800,
                "quote_price": 1200,
                "current_quote_price": 1000,
            })))),
            MagicMock(scalar_one=MagicMock(return_value=2)),
            MagicMock(),
            MagicMock(),
            MagicMock(rowcount=1),
        ]
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection

        with patch.object(bid_repository, "engine", engine):
            result = bid_repository.apply_closed_bid_outcome(
                bid_id=10006,
                status="WON",
                source_message_id="gmail:box:message-1",
                final_quote_price=700,
                lost_reason=None,
                missing_fields=[],
            )

        self.assertEqual(result["status"], "WON")
        self.assertEqual(connection.execute.call_count, 6)
        insert_sql = str(connection.execute.call_args_list[4].args[0])
        self.assertIn("INSERT INTO quote_versions", insert_sql)
        self.assertNotIn("pricing_policies", " ".join(str(call.args[0]) for call in connection.execute.call_args_list))

    def test_non_closed_bid_is_not_updated(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(mappings=MagicMock(return_value=MagicMock(first=MagicMock(return_value={
                "bid_id": 10007,
                "status": "OPEN",
                "total_cost": 800,
                "quote_price": 1200,
                "current_quote_price": 1000,
            })))),
        ]
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection

        with patch.object(bid_repository, "engine", engine):
            result = bid_repository.apply_closed_bid_outcome(
                bid_id=10007,
                status="LOST",
                source_message_id="gmail:box:message-2",
                final_quote_price=None,
                lost_reason="Timing",
                missing_fields=[],
            )

        self.assertFalse(result["matched"])
        self.assertEqual(connection.execute.call_count, 2)

    def test_lost_reason_is_written_to_its_database_column(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(mappings=MagicMock(return_value=MagicMock(first=MagicMock(return_value={
                "bid_id": 10012,
                "status": "CLOSED",
                "total_cost": 800,
                "quote_price": 1200,
                "current_quote_price": 1000,
            })))),
            MagicMock(rowcount=1),
        ]
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection

        with patch.object(bid_repository, "engine", engine):
            result = bid_repository.apply_closed_bid_outcome(
                bid_id=10012,
                status="LOST",
                source_message_id="gmail:box:message-12",
                final_quote_price=None,
                lost_reason="Customer selected another supplier",
                missing_fields=[],
            )

        self.assertEqual(result["status"], "LOST")
        update = connection.execute.call_args_list[2]
        self.assertIn("lost_reason = :lost_reason", str(update.args[0]))
        self.assertEqual(update.args[1]["lost_reason"], "Customer selected another supplier")


class BidOutcomeWorkflowTests(unittest.TestCase):
    def test_worker_updates_matched_closed_bid_without_creating_rfq(self):
        email = MagicMock(source_message_id="gmail:inbox:message-8", message_id="message-8")
        inbox = MagicMock()
        inbox.list_unprocessed.return_value = [email]
        outcome = {
            "bid_id": 10008,
            "status": "WON",
            "final_quote_price": 900,
            "lost_reason": None,
            "missing_fields": [],
        }
        with (
            patch.object(gmail_rfq_intake, "extract_inbound_email", return_value={}),
            patch.object(gmail_rfq_intake, "resolve_bid_outcome", return_value=outcome),
            patch.object(gmail_rfq_intake, "apply_closed_bid_outcome", return_value={"matched": True, "duplicate": False, "bid_id": 10008, "status": "WON"}) as apply,
            patch.object(gmail_rfq_intake, "save_inbound_rfq") as save_rfq,
        ):
            processed = gmail_rfq_intake.poll_once(inbox, object())

        self.assertEqual(processed, 1)
        apply.assert_called_once_with(**outcome, source_message_id=email.source_message_id)
        save_rfq.assert_not_called()
        inbox.mark_processed.assert_called_once_with(email)

    def test_worker_routes_unmatched_outcome_to_on_hold_rfq_flow(self):
        email = MagicMock(source_message_id="gmail:inbox:message-9", message_id="message-9")
        inbox = MagicMock()
        inbox.list_unprocessed.return_value = [email]
        intake = {"merged": {"bid_outcome": {"bid_id": 10009, "status": "LOST"}}}
        with (
            patch.object(gmail_rfq_intake, "extract_inbound_email", return_value=intake),
            patch.object(gmail_rfq_intake, "resolve_bid_outcome", return_value={"bid_id": 10009, "status": "LOST", "final_quote_price": None, "lost_reason": "Timing", "missing_fields": []}),
            patch.object(gmail_rfq_intake, "apply_closed_bid_outcome", return_value={"matched": False, "duplicate": False, "bid_id": 10009}),
            patch.object(gmail_rfq_intake, "save_inbound_rfq", return_value={"rfq_id": 101, "duplicate": False, "processing_status": "ON_HOLD"}) as save_rfq,
        ):
            processed = gmail_rfq_intake.poll_once(inbox, object())

        self.assertEqual(processed, 1)
        save_rfq.assert_called_once_with(email, intake)

    def test_finalize_emails_assigned_sales_rep_then_closes_open_bid(self):
        bid = {
            "bid_id": 10010,
            "status": "OPEN",
            "customer_name": "Example Customer",
            "sales_rep_name": "Sales Rep",
            "sales_rep_email": "rep@example.com",
            "current_quote_price": 900,
        }
        with (
            patch.object(bid_service, "get_bid", return_value=bid),
            patch.object(bid_service, "get_bid_line_items", return_value=[]),
            patch.object(bid_service, "GmailInbox") as inbox_class,
            patch.object(bid_service, "mark_bid_closed_if_open", return_value=True) as close_bid,
        ):
            inbox_class.return_value.send_message.return_value = "sent-1"
            result = bid_service.finalize_open_bid(10010)

        self.assertEqual(result["status"], "CLOSED")
        inbox_class.return_value.send_message.assert_called_once()
        close_bid.assert_called_once_with(10010)

    def test_finalize_does_not_close_bid_when_notification_fails(self):
        bid = {
            "bid_id": 10011,
            "status": "OPEN",
            "customer_name": "Example Customer",
            "sales_rep_email": "rep@example.com",
        }
        with (
            patch.object(bid_service, "get_bid", return_value=bid),
            patch.object(bid_service, "get_bid_line_items", return_value=[]),
            patch.object(bid_service, "GmailInbox") as inbox_class,
            patch.object(bid_service, "mark_bid_closed_if_open") as close_bid,
        ):
            inbox_class.return_value.send_message.side_effect = RuntimeError("send failed")
            with self.assertRaises(bid_service.BidFinalizationError):
                bid_service.finalize_open_bid(10011)

        close_bid.assert_not_called()


if __name__ == "__main__":
    unittest.main()
