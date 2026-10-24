"""Checks of persisted metric denominators, flags and read-only behavior."""

from dataclasses import asdict
import itertools
import json
import sqlite3
from unittest.mock import patch

import pytest

from loopledger import ledger, metrics
from loopledger.schemas import GateResult, Prediction, ReviewAction
from scripts.demo_reset import seed_demo, seed_oversight_demo


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "metrics.db"
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(path))
    ledger.init_db()
    return path


@pytest.fixture
def review(database):
    sequence = itertools.count()

    def create(*, reviewer="alice", decision="approve", action="approve",
               seconds=30.0, reason="Checked all supporting documents.", correct=None):
        pred = Prediction(
            f"case-{next(sequence)}", {"credit_amount": 2500, "age": 35, "duration": 24},
            decision, 0.6, [("credit_amount", -0.1)], correct is not None, correct,
        )
        ledger.log_event("prediction", asdict(pred))
        ledger.log_event("gate", {"case_id": pred.case_id, **asdict(GateResult(True, ["low_confidence"]))})
        ledger.submit_review(ReviewAction(pred.case_id, reviewer, action, reason, seconds))
        return pred

    return create


def test_empty_metrics_keep_contract_columns_and_zero_counts(database):
    frame = metrics.reviewer_stats()
    assert frame.empty
    assert list(frame.columns[:7]) == [
        "reviewer", "n_reviews", "avg_seconds", "override_rate", "gold_catch_rate",
        "short_reason_rate", "flag",
    ]
    assert metrics.system_stats() == {
        "total": 0, "auto_approved": 0, "auto_rejected": 0,
        "sent_to_review": 0, "reviewed": 0, "pending": 0,
    }


def test_oversight_profile_has_hand_calculated_reviewer_contrast(database):
    seed_oversight_demo()
    frame = metrics.reviewer_stats().set_index("reviewer")
    careful, stamp = frame.loc["careful_reviewer"], frame.loc["rubber_stamp"]
    assert careful["n_reviews"] == stamp["n_reviews"] == 6
    assert (careful["avg_seconds"], stamp["avg_seconds"]) == (50.0, 2.0)
    assert (careful["override_rate"], stamp["override_rate"]) == (0.5, 0.0)
    assert (careful["gold_catch_rate"], stamp["gold_catch_rate"]) == (1.0, 0.0)
    assert (careful["short_reason_rate"], stamp["short_reason_rate"]) == (0.0, 1.0)
    assert careful["gold_samples"] == stamp["gold_samples"] == 3
    assert careful["flag"] == "no_alert"
    assert careful["flag_reasons"] == []
    assert stamp["flag"] == "review_signals"
    assert "gold_catch_rate_below_0.5" in stamp["flag_reasons"]
    assert "avg_seconds_below_5" in stamp["flag_reasons"]
    assert metrics.system_stats() == {
        "total": 16, "auto_approved": 1, "auto_rejected": 1,
        "sent_to_review": 14, "reviewed": 12, "pending": 2,
    }
    assert len(ledger.get_all_events()) == 44
    assert ledger.verify_chain() == (True, None)


def test_basic_profile_does_not_overclaim_from_two_reviews(database):
    seed_demo()
    frame = metrics.reviewer_stats()
    assert frame["flag"].tolist() == ["insufficient_data", "insufficient_data"]
    assert all("fewer_than_5_reviews" in reasons for reasons in frame["flag_reasons"])
    assert len(ledger.get_all_events()) == 20


def test_binary_actions_override_only_when_different_from_ai_and_match_gold_exactly(review):
    review(correct="reject", action="reject")
    review(correct="reject", action="approve")
    review(decision="reject", action="approve")
    row = metrics.reviewer_stats().iloc[0]
    assert row["override_rate"] == pytest.approx(2 / 3)
    assert row["gold_samples"] == 2
    assert row["gold_catch_rate"] == 0.5


def test_correct_ai_controls_and_pending_gold_do_not_dilute_error_catch_rate(review):
    review(correct="approve", action="reject")  # Correct-AI control, not an error probe.
    review(correct="reject", action="reject")
    pred = Prediction("pending-gold", {}, "approve", 0.95, [], True, "reject")
    ledger.log_event("prediction", asdict(pred))
    row = metrics.reviewer_stats().iloc[0]
    assert row["gold_samples"] == 1
    assert row["gold_catch_rate"] == 1.0
    assert row["n_reviews"] == 2


def test_absent_gold_measurements_stay_none_in_strict_json(review):
    review(reviewer="no-controls")
    review(reviewer="controls", correct="reject", action="reject")
    records = metrics.reviewer_stats().to_dict(orient="records")
    empty_gold = next(row for row in records if row["reviewer"] == "no-controls")
    assert empty_gold["gold_catch_rate"] is None
    assert empty_gold["gold_samples"] == 0
    json.dumps(records, allow_nan=False)


@pytest.mark.parametrize("seconds,flag", [
    (4.999, "review_signals"), (5.0, "watch"),
    (14.999, "watch"), (15.0, "no_alert"),
])
def test_review_time_threshold_boundaries(review, seconds, flag):
    for index in range(5):
        review(seconds=seconds, action="reject" if index == 0 else "approve")
    assert metrics.reviewer_stats().iloc[0]["flag"] == flag


@pytest.mark.parametrize("short_count,flag", [
    (1, "no_alert"), (2, "watch"), (4, "review_signals"),
])
def test_short_reason_thresholds_use_stripped_text_and_twelve_chars(review, short_count, flag):
    for index in range(5):
        review(
            reason="  abcdefghijk \n" if index < short_count else "abcdefghijkl",
            action="reject" if index == 0 else "approve",
        )
    row = metrics.reviewer_stats().iloc[0]
    assert row["short_reason_rate"] == short_count / 5
    assert row["flag"] == flag


def test_zero_overrides_needs_five_comparisons_and_only_raises_watch(review):
    for _ in range(4):
        review()
    assert metrics.reviewer_stats().iloc[0]["flag"] == "insufficient_data"
    review()
    row = metrics.reviewer_stats().iloc[0]
    assert row["flag"] == "watch"
    assert row["flag_reasons"] == ["zero_overrides_across_5_or_more_reviews"]


@pytest.mark.parametrize("caught,flag", [(1, "review_signals"), (2, "watch"), (3, "no_alert")])
def test_gold_alerts_require_three_error_probes(review, caught, flag):
    for index in range(3):
        review(correct="reject", action="reject" if index < caught else "approve")
    for _ in range(2):
        review()
    row = metrics.reviewer_stats().iloc[0]
    assert row["gold_catch_rate"] == caught / 3
    assert row["flag"] == flag


def test_fewer_than_three_gold_probes_do_not_raise_gold_alert(review):
    review(correct="reject")
    review(correct="reject")
    for index in range(3):
        review(action="reject" if index == 0 else "approve")
    row = metrics.reviewer_stats().iloc[0]
    assert row["gold_samples"] == 2
    assert row["gold_catch_rate"] == 0.0
    assert row["flag"] == "no_alert"


def test_automatic_rejections_are_not_counted_as_approvals_and_unrouted_is_pending(database):
    for case_id, decision in (("approved", "approve"), ("rejected", "reject")):
        ledger.log_event("prediction", asdict(Prediction(case_id, {}, decision, 0.95, [])))
        ledger.log_event("gate", {"case_id": case_id, "needs_review": False, "reasons": []})
    ledger.log_event("prediction", asdict(Prediction("unrouted", {}, "approve", 0.6, [])))
    assert metrics.system_stats() == {
        "total": 3, "auto_approved": 1, "auto_rejected": 1,
        "sent_to_review": 1, "reviewed": 0, "pending": 1,
    }


def test_rates_use_audited_prediction_instead_of_mutable_case_projection(review, database):
    pred = review(action="reject")
    with sqlite3.connect(database) as connection:
        replacement = asdict(pred)
        replacement["decision"] = "reject"
        connection.execute("UPDATE cases SET prediction=? WHERE case_id=?", (json.dumps(replacement), pred.case_id))
    assert metrics.reviewer_stats().iloc[0]["override_rate"] == 1.0


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1, True])
def test_legacy_missing_predictions_or_invalid_timings_are_not_zero_agreement(database, duration):
    payload = asdict(ReviewAction("missing-original", "alice", "approve", "Documents checked.", duration))
    with patch.object(ledger, "get_all_events", return_value=[{"event_type": "review", "payload": payload}]):
        row = metrics.reviewer_stats().iloc[0]
    assert row["avg_seconds"] is None
    assert row["override_rate"] is None
    assert row["gold_catch_rate"] is None
    assert row["flag"] == "insufficient_data"
    assert "missing_ai_predictions" in row["flag_reasons"]
    assert "missing_or_invalid_timings" in row["flag_reasons"]


def test_metrics_reads_do_not_write_or_cache_stale_state(database, review):
    before = database.read_bytes()
    assert metrics.reviewer_stats().empty
    assert metrics.system_stats()["reviewed"] == 0
    assert database.read_bytes() == before
    review(action="reject")
    after_write = database.read_bytes()
    assert metrics.reviewer_stats().iloc[0]["n_reviews"] == 1
    assert metrics.system_stats()["reviewed"] == 1
    assert database.read_bytes() == after_write
    assert len(ledger.get_all_events()) == 3


def test_oversight_cli_selects_profile_and_preserves_basic_default(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    path = tmp_path / "oversight.db"
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/demo_reset.py"),
               "--db", str(path), "--profile", "oversight"]
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    assert result["profile"] == "oversight"
    assert (result["events"], result["pending"], result["chain_intact"]) == (44, 2, True)
    with patch.dict(os.environ, {"LOOPLEDGER_DB_PATH": str(path)}):
        assert metrics.system_stats()["reviewed"] == 12
