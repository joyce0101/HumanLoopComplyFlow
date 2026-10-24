"""Binary review policy, with read-only compatibility for historical records."""

from dataclasses import asdict
import json
from typing import get_args, get_type_hints

import pytest

from loopledger import gold, ledger, metrics
from loopledger.schemas import Prediction, ReviewAction
from scripts.demo_reset import seed_oversight_demo


def legacy_case(*, case_id="LEGACY", action=None):
    """Create an authentic old-format fixture without using today's write policy."""
    pred = Prediction(case_id, {"credit_amount": 2000}, "approve", .95, [], True, "modify")
    with ledger._connection(write=True) as connection:
        connection.execute("INSERT INTO cases VALUES (?,?,?)", (
            case_id, json.dumps(asdict(pred)), "reviewed" if action else "pending",
        ))
        payloads = [("prediction", asdict(pred))]
        if action:
            payloads.append(("review", asdict(ReviewAction(
                case_id, "alice", action, "Historical evidence was checked.", 30.0,
            ))))
        for kind, payload in payloads:
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            previous = connection.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
            previous_hash = previous["hash"] if previous else ledger.GENESIS_HASH
            timestamp = "2026-10-24T00:00:00+00:00"
            connection.execute(
                "INSERT INTO events(ts,event_type,case_id,payload,prev_hash,hash) VALUES(?,?,?,?,?,?)",
                (timestamp, kind, case_id, encoded, previous_hash,
                 ledger._hash(previous_hash, timestamp, kind, encoded)),
            )
    return pred


def test_review_contract_only_exposes_approve_and_reject():
    assert set(get_args(get_type_hints(ReviewAction)["action"])) == {"approve", "reject"}


@pytest.mark.parametrize("direct_event", [False, True])
def test_new_modify_reviews_are_rejected_without_state_or_event_changes(direct_event):
    pred = Prediction("NEW", {}, "approve", .6, [])
    ledger.log_event("prediction", asdict(pred))
    before = ledger.get_all_events()
    action = ReviewAction("NEW", "alice", "modify", "Please check the evidence.", 20.0)
    with pytest.raises(ValueError, match="approve or reject"):
        if direct_event:
            ledger.log_event("review", asdict(action))
        else:
            ledger.submit_review(action)
    assert ledger.get_all_events() == before
    assert ledger.get_pending_reviews() == [pred]
    assert ledger.verify_chain() == (True, None)


def test_new_modify_gold_answers_are_rejected_but_old_records_remain_readable():
    pred = legacy_case()
    before = ledger.get_all_events()
    assert ledger.get_pending_reviews() == [pred]
    with pytest.raises(ValueError, match="approve or reject"):
        ledger.log_event("prediction", {**asdict(pred), "case_id": "NEW-GOLD"})
    assert ledger.get_all_events() == before
    ledger.submit_review(ReviewAction(pred.case_id, "alice", "reject", "Missing evidence.", 20.0))
    assert ledger.get_all_events()[:len(before)] == before
    assert not ledger.get_pending_reviews()
    assert ledger.verify_chain() == (True, None)


def test_gold_evaluator_rejects_modify():
    with pytest.raises(ValueError, match="approve.*reject"):
        gold.evaluate_gold_review("GOLD-001", "modify")


def test_oversight_seed_uses_only_binary_actions_and_answers():
    seed_oversight_demo()
    for event in ledger.get_all_events():
        payload = event["payload"]
        if event["event_type"] == "review":
            assert payload["action"] in ("approve", "reject")
        elif event["event_type"] == "prediction" and payload["is_gold"]:
            assert payload["gold_correct_decision"] in ("approve", "reject")


def test_legacy_modify_gold_answers_do_not_penalize_binary_review_scores():
    legacy_case(action="reject")
    before = ledger.get_all_events()
    row = metrics.reviewer_stats().iloc[0]
    assert row["n_reviews"] == 1
    assert row["gold_samples"] == 0
    assert row["gold_catch_rate"] is None
    pred = Prediction("BINARY-GOLD", {}, "approve", .95, [], True, "reject")
    ledger.log_event("prediction", asdict(pred))
    ledger.submit_review(ReviewAction("BINARY-GOLD", "alice", "reject", "Evidence checked.", 25.0))
    row = metrics.reviewer_stats().iloc[0]
    assert row["gold_samples"] == 1
    assert row["gold_catch_rate"] == 1.0
    assert ledger.get_all_events()[:len(before)] == before
    assert ledger.verify_chain() == (True, None)


def test_historical_modify_review_remains_in_the_audit_log():
    legacy_case(action="modify")
    before = ledger.get_all_events()
    row = metrics.reviewer_stats().iloc[0]
    assert row["n_reviews"] == 1
    assert row["gold_samples"] == 0
    assert ledger.get_all_events()[-1]["payload"]["action"] == "modify"
    assert ledger.get_all_events() == before
    assert ledger.verify_chain() == (True, None)
