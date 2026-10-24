"""B-owned integration checks against unchanged team A implementations."""

from dataclasses import asdict
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from loopledger import ledger
from loopledger.gate import evaluate_risk
from loopledger.gold import get_gold_cases, public_review_payload, evaluate_gold_review
from loopledger.schemas import Prediction, ReviewAction


class TeamIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        environment = patch.dict(os.environ, {"LOOPLEDGER_DB_PATH": str(self.directory / "ledger.db")})
        environment.start()
        self.addCleanup(environment.stop)
        ledger.init_db()

    def store(self, pred):
        application = {**pred.features, "case_id": pred.case_id}
        result = evaluate_risk(application, pred)
        ledger.log_event("prediction", asdict(pred))
        ledger.log_event("gate", {"case_id": pred.case_id, **asdict(result)})
        return result

    def test_all_team_gold_cases_round_trip_including_modify(self):
        cases = get_gold_cases(6, include_answers=True)
        self.assertEqual(len(cases), 6)
        self.assertIn("modify", {pred.gold_correct_decision for pred in cases})
        for pred in cases:
            self.assertTrue(self.store(pred).needs_review)
        self.assertEqual(ledger.get_pending_reviews(), cases)
        for pred in ledger.get_pending_reviews():
            public = public_review_payload(pred)
            self.assertNotIn("is_gold", public)
            self.assertNotIn("gold_correct_decision", public)
            action = pred.gold_correct_decision
            ledger.submit_review(ReviewAction(
                pred.case_id, "team-integration", action,
                "Checked the available policy evidence before deciding.", 35.0,
            ))
            self.assertTrue(evaluate_gold_review(pred.case_id, action)["is_correct"])
        self.assertEqual(ledger.get_pending_reviews(), [])
        self.assertEqual(len(ledger.get_all_events()), 18)
        self.assertEqual(ledger.verify_chain(), (True, None))

    def test_masked_gold_input_requires_backend_answer_key(self):
        pred = get_gold_cases(1)[0]
        self.assertIsNone(pred.gold_correct_decision)
        with self.assertRaisesRegex(ValueError, "include_answers=True"):
            ledger.log_event("prediction", asdict(pred))
        self.assertEqual(ledger.get_all_events(), [])

    def test_real_team_gate_controls_auto_and_pending_status(self):
        safe = Prediction(
            "safe", {"credit_amount": 2000, "identity_verified": True},
            "approve", 0.95, [],
        )
        uncertain = Prediction(
            "uncertain", {"credit_amount": 2000, "identity_verified": True},
            "approve", 0.6, [],
        )
        self.assertFalse(self.store(safe).needs_review)
        self.assertTrue(self.store(uncertain).needs_review)
        self.assertEqual(ledger.get_pending_reviews(), [uncertain])
        self.assertEqual(ledger.verify_chain(), (True, None))

    def test_team_database_module_entry_point_is_preserved(self):
        result = subprocess.run(
            [sys.executable, "-m", "loopledger.ledger"],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("Database ready:", result.stdout)
        self.assertEqual(ledger.verify_chain(), (True, None))

    @unittest.skipUnless(importlib.util.find_spec("sklearn"), "model smoke test needs scikit-learn")
    def test_real_model_prediction_gate_and_review_with_temporary_artifact(self):
        from loopledger.model import EXAMPLE_APPLICATION, predict, train

        # Train from the team's local dataset. Do not overwrite their joblib file.
        model_path = self.directory / "integration-model.joblib"
        metrics = train(model_path=model_path)
        self.assertEqual((metrics["train_rows"], metrics["test_rows"]), (750, 250))
        pred = predict(dict(EXAMPLE_APPLICATION), case_id=EXAMPLE_APPLICATION["case_id"], model_path=model_path)
        self.assertIsInstance(pred, Prediction)
        self.assertTrue(self.store(pred).needs_review)
        self.assertEqual(ledger.get_pending_reviews(), [pred])
        ledger.submit_review(ReviewAction(
            pred.case_id, "model-integration", "modify",
            "The large amount requires additional supporting evidence.", 42.0,
        ))
        self.assertEqual(ledger.get_pending_reviews(), [])
        self.assertEqual(ledger.verify_chain(), (True, None))


if __name__ == "__main__":
    unittest.main()
