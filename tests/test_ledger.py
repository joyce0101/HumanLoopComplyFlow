"""Offline acceptance tests for B's Sprint 1 deliverable."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, fields
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from loopledger import ledger
from loopledger.schemas import GateResult, Prediction, ReviewAction


ROOT = Path(__file__).resolve().parents[1]


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "ledger.db"
        env = patch.dict(os.environ, {"LOOPLEDGER_DB_PATH": str(self.db)})
        env.start()
        self.addCleanup(env.stop)
        ledger.init_db()

    def sql(self, statement, parameters=()):
        connection = sqlite3.connect(self.db)
        try:
            with connection:
                return connection.execute(statement, parameters).fetchall()
        finally:
            connection.close()

    def record_case(self, case_id="case-1", needs_review=True, is_gold=False):
        pred = Prediction(
            case_id, {"age": 24, "申请说明": "稳定收入"}, "reject", 0.62,
            [("age", -0.23)], is_gold, "approve" if is_gold else None,
        )
        ledger.log_event("prediction", asdict(pred))
        ledger.log_event("gate", {
            "case_id": case_id,
            **asdict(GateResult(needs_review, ["low_confidence"] if needs_review else [])),
        })
        return pred

    def review(self, **overrides):
        data = dict(case_id="case-1", reviewer="reviewer-1", action="approve",
                    reason="核对收入和还款能力后，推翻 AI 建议。", seconds_spent=35.5)
        data.update(overrides)
        return ReviewAction(**data)

    def test_shared_schema_fields_match_plan(self):
        self.assertEqual([f.name for f in fields(Prediction)], [
            "case_id", "features", "decision", "confidence", "top_factors",
            "is_gold", "gold_correct_decision",
        ])
        self.assertEqual([f.name for f in fields(GateResult)], ["needs_review", "reasons"])
        self.assertEqual([f.name for f in fields(ReviewAction)], [
            "case_id", "reviewer", "action", "reason", "seconds_spent",
        ])

    def test_init_is_idempotent_and_empty_chain_is_valid(self):
        self.assertEqual(ledger.verify_chain(), (True, None))
        ledger.log_event("export", {"format": "markdown"})
        ledger.init_db()
        self.assertEqual(len(ledger.get_all_events()), 1)
        self.assertEqual(ledger.verify_chain(), (True, None))

    def test_twenty_events_match_independently_computed_hashes(self):
        for number in range(20):
            returned_hash = ledger.log_event("export", {"number": number, "备注": "审计"})
        self.assertEqual(ledger.verify_chain(), (True, None))
        rows = self.sql("SELECT ts, event_type, payload, prev_hash, hash FROM events ORDER BY id")
        self.assertEqual(len(rows), 20)
        previous = "0" * 64
        for ts, event_type, payload, prev_hash, event_hash in rows:
            expected = hashlib.sha256((previous + ts + event_type + payload).encode("utf-8")).hexdigest()
            self.assertEqual(prev_hash, previous)
            self.assertEqual(event_hash, expected)
            self.assertTrue(ts.endswith("+00:00"))
            previous = event_hash
        self.assertEqual(returned_hash, previous)
        self.assertIsInstance(ledger.get_all_events()[0]["payload"], dict)

    def test_payload_and_metadata_tampering_reports_exact_id(self):
        for number in range(20):
            ledger.log_event("export", {"number": number})
        original = self.sql("SELECT ts, event_type, payload, prev_hash, hash, case_id FROM events WHERE id = 10")[0]
        replacements = {
            "ts": "changed", "event_type": "changed", "payload": '{"number":999}',
            "prev_hash": "0" * 64, "hash": "f" * 64, "case_id": "other-case",
        }
        for column, value in replacements.items():
            with self.subTest(column=column):
                # Column names come from the fixed test dictionary, not user input.
                self.sql(f"UPDATE events SET {column} = ? WHERE id = 10", (value,))
                self.assertEqual(ledger.verify_chain(), (False, 10))
                self.sql(
                    "UPDATE events SET ts=?, event_type=?, payload=?, prev_hash=?, hash=?, case_id=? WHERE id=10",
                    original,
                )
        self.assertEqual(ledger.verify_chain(), (True, None))

    def test_deleting_middle_event_is_detected(self):
        for number in range(5):
            ledger.log_event("export", {"number": number})
        self.sql("DELETE FROM events WHERE id = 3")
        self.assertEqual(ledger.verify_chain(), (False, 3))

    def test_deleting_tail_or_all_events_is_detected(self):
        for number in range(5):
            ledger.log_event("export", {"number": number})
        self.sql("DELETE FROM events WHERE id = 5")
        self.assertEqual(ledger.verify_chain(), (False, 5))
        self.sql("DELETE FROM events")
        self.assertEqual(ledger.verify_chain(), (False, 1))

    def test_routing_and_review_round_trip(self):
        pred = self.record_case(is_gold=True)
        self.record_case("automatic", needs_review=False)
        self.assertEqual(ledger.get_pending_reviews(), [pred])
        action = self.review()
        ledger.submit_review(action)
        self.assertEqual(ledger.get_pending_reviews(), [])
        self.assertEqual(self.sql("SELECT status FROM cases WHERE case_id='case-1'"), [("reviewed",)])
        self.assertEqual(ledger.get_all_events()[-1]["payload"], asdict(action))
        self.assertEqual(ledger.verify_chain(), (True, None))

    def test_prediction_is_pending_until_gate_and_duplicate_is_rejected(self):
        pred = Prediction("case-1", {}, "approve", 0.9, [])
        ledger.log_event("prediction", asdict(pred))
        self.assertEqual(ledger.get_pending_reviews(), [pred])
        with self.assertRaises(ValueError):
            ledger.log_event("prediction", asdict(pred))
        self.assertEqual(len(ledger.get_all_events()), 1)

    def test_modify_is_preserved_without_inventing_final_decision(self):
        self.record_case()
        ledger.submit_review(self.review(action="modify"))
        self.assertEqual(ledger.get_all_events()[-1]["payload"]["action"], "modify")
        self.assertEqual(ledger.get_pending_reviews(), [])

    def test_duplicate_unknown_and_automatic_reviews_leave_no_event(self):
        self.record_case()
        self.record_case("automatic", needs_review=False)
        ledger.submit_review(self.review())
        for case_id in ("case-1", "missing", "automatic"):
            with self.subTest(case_id=case_id), self.assertRaises(ValueError):
                ledger.submit_review(self.review(case_id=case_id))
        self.assertEqual(len(ledger.get_all_events()), 5)
        self.assertEqual(ledger.verify_chain(), (True, None))

    def test_invalid_reviews_leave_case_pending_and_no_event(self):
        self.record_case()
        for overrides in (
            {"reviewer": " "}, {"reason": "\t"}, {"action": "invalid"},
            {"seconds_spent": -1}, {"seconds_spent": float("nan")},
            {"seconds_spent": float("inf")}, {"seconds_spent": True},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                ledger.submit_review(self.review(**overrides))
        self.assertEqual(len(ledger.get_all_events()), 2)
        self.assertEqual(len(ledger.get_pending_reviews()), 1)

    def test_invalid_predictions_and_gates_are_rolled_back(self):
        pred = Prediction("case-1", {}, "approve", 0.8, [])
        for overrides in (
            {"confidence": 1.1}, {"decision": "unknown"},
            {"is_gold": True}, {"top_factors": [["age"]]},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                ledger.log_event("prediction", {**asdict(pred), **overrides})
        self.assertEqual(ledger.get_all_events(), [])
        for payload in (
            {"case_id": "missing", "needs_review": True, "reasons": []},
            {"case_id": "missing", "needs_review": "false", "reasons": []},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                ledger.log_event("gate", payload)
        self.assertEqual(ledger.get_all_events(), [])

    def test_gate_cannot_reopen_an_already_routed_case(self):
        self.record_case(needs_review=False)
        with self.assertRaises(ValueError):
            ledger.log_event("gate", {"case_id": "case-1", "needs_review": True, "reasons": []})
        self.assertEqual(ledger.get_pending_reviews(), [])
        self.assertEqual(len(ledger.get_all_events()), 2)

    def test_case_status_rolls_back_if_event_insert_fails(self):
        self.record_case()
        self.sql("""
            CREATE TRIGGER reject_review BEFORE INSERT ON events
            WHEN NEW.event_type = 'review'
            BEGIN SELECT RAISE(ABORT, 'simulated event failure'); END
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            ledger.submit_review(self.review())
        self.assertEqual(len(ledger.get_pending_reviews()), 1)
        self.assertEqual(len(ledger.get_all_events()), 2)
        self.assertEqual(ledger.verify_chain(), (True, None))

    def test_concurrent_appends_do_not_fork_chain(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            hashes = list(pool.map(lambda n: ledger.log_event("export", {"number": n}), range(40)))
        self.assertEqual(len(set(hashes)), 40)
        self.assertEqual(len(ledger.get_all_events()), 40)
        self.assertEqual(ledger.verify_chain(), (True, None))

    def test_concurrent_review_submits_have_one_winner(self):
        self.record_case()

        def submit(reviewer):
            try:
                ledger.submit_review(self.review(reviewer=reviewer))
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, ("reviewer-1", "reviewer-2")))
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(ledger.get_all_events()), 3)
        self.assertEqual(ledger.verify_chain(), (True, None))

    def test_reset_cli_is_repeatable_offline_and_requires_explicit_overwrite(self):
        path = Path(self.directory.name) / "demo.db"
        command = [sys.executable, str(ROOT / "scripts" / "demo_reset.py"), "--db", str(path)]
        first = subprocess.run(command, capture_output=True, text=True, check=True)
        data = json.loads(first.stdout)
        self.assertEqual((data["events"], data["pending"], data["chain_intact"]), (20, 2, True))
        blocked = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("--force", blocked.stderr)
        second = subprocess.run(command + ["--force"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(second.stdout)["events"], 20)
        with patch.dict(os.environ, {"LOOPLEDGER_DB_PATH": str(path)}):
            self.assertEqual(ledger.verify_chain(), (True, None))
            reviews = [e["payload"] for e in ledger.get_all_events() if e["event_type"] == "review"]
            self.assertEqual({r["reviewer"] for r in reviews}, {"careful_reviewer", "rubber_stamp"})
            self.assertEqual(sum(p.is_gold for p in ledger.get_pending_reviews()), 0)
            self.assertEqual(len(self.sql("SELECT * FROM cases")), 0)
        empty = subprocess.run(command + ["--force", "--empty"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(empty.stdout)["events"], 0)
        with patch.dict(os.environ, {"LOOPLEDGER_DB_PATH": str(path)}):
            self.assertEqual(ledger.verify_chain(), (True, None))


if __name__ == "__main__":
    unittest.main()
