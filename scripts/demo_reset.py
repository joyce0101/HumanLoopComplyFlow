"""Reset a local demo database and seed synthetic, offline integration fixtures."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loopledger import ledger
from loopledger.schemas import GateResult, Prediction, ReviewAction


def seed_demo() -> None:
    """8 cases + 8 gates + 4 reviews = 20 events; no trained model is involved."""
    predictions = {}
    for number in range(1, 9):
        is_gold = number in (4, 6)
        pred = Prediction(
            case_id=f"demo-{number:03d}",
            features={"credit_amount": 1000 + number * 500, "age": 22 + number, "duration": 12},
            decision="reject" if number > 2 and number % 2 == 0 else "approve",
            confidence=0.93 if number <= 2 else 0.61,
            top_factors=[("credit_amount", -0.2), ("duration", 0.1), ("age", 0.05)],
            is_gold=is_gold,
            gold_correct_decision="approve" if is_gold else None,
        )
        predictions[number] = pred
        ledger.log_event("prediction", asdict(pred))
        gate = GateResult(number > 2, ["low_confidence"] if number > 2 else [])
        ledger.log_event("gate", {"case_id": pred.case_id, **asdict(gate)})
    for number, reviewer, seconds, reason in (
        (3, "careful_reviewer", 45.0, "Checked the repayment term and affordability against the application."),
        (4, "careful_reviewer", 60.0, "Rejected the AI recommendation after checking the supporting evidence."),
        (5, "rubber_stamp", 1.0, "OK"),
        (6, "rubber_stamp", 2.0, "OK"),
    ):
        pred = predictions[number]
        ledger.submit_review(ReviewAction(
            case_id=pred.case_id,
            reviewer=reviewer,
            action="approve" if reviewer == "careful_reviewer" else pred.decision,
            reason=reason,
            seconds_spent=seconds,
        ))


def seed_oversight_demo(*, binary_only: bool = False) -> None:
    """16 synthetic cases, 12 reviews, 44 events; six reviews per reviewer.

    Each reviewer sees three deliberately wrong AI probes. The careful reviewer
    catches all three; the rubber stamp follows the AI. binary_only uses the
    real model risk gate and approve/reject operations for functional checks.
    """
    for number in range(1, 17):
        automatic = number <= 2
        completed = 3 <= number <= 14
        careful = 3 <= number <= 8
        index = (number - 3) % 6
        is_gold = completed and index < 3
        answers = ("reject" if binary_only else "modify", "reject", "approve")
        correct = answers[index] if is_gold else None
        decision = "reject" if (correct == "approve" or number == 2) else "approve"
        pred = Prediction(
            case_id=f"oversight-{number:03d}",
            features={"credit_amount": 2000 + number * 100, "age": 30 + number, "duration": 24},
            decision=decision,
            confidence=0.95 if automatic or is_gold else 0.61,
            top_factors=[("credit_amount", -0.2), ("duration", 0.1), ("age", 0.05)],
            is_gold=is_gold,
            gold_correct_decision=correct,
        )
        if binary_only:
            pred.features.update(case_id=pred.case_id, identity_verified=True)
        ledger.log_event("prediction", asdict(pred))
        if binary_only:
            from loopledger.gate import evaluate_risk
            gate = evaluate_risk(pred.features, pred)
        else:
            gate = GateResult(not automatic, ["demo_manual_review"] if not automatic else [])
        ledger.log_event("gate", {"case_id": pred.case_id, **asdict(gate)})
        if completed:
            ledger.submit_review(ReviewAction(
                case_id=pred.case_id,
                reviewer="careful_reviewer" if careful else "rubber_stamp",
                action=correct if careful and is_gold else pred.decision,
                reason="Checked the application and supporting evidence before deciding." if careful else "OK",
                seconds_spent=(45.0, 50.0, 55.0, 60.0, 40.0, 50.0)[index] if careful else 2.0,
            ))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("LOOPLEDGER_DB_PATH", ledger.DB_PATH)))
    parser.add_argument("--empty", action="store_true", help="Create empty tables without demo fixtures")
    parser.add_argument("--force", action="store_true", help="Clear an existing database before seeding")
    parser.add_argument(
        "--profile", choices=("basic", "oversight", "functional"), default="basic",
        help="basic: 20 events; oversight: 44 events; functional: binary actions and model risk gate",
    )
    args = parser.parse_args(argv)
    path = args.db.resolve()
    if path.exists() and not args.force:
        parser.error(f"Database already exists: {path}. Use --force to reset its data.")
    os.environ["LOOPLEDGER_DB_PATH"] = str(path)
    ledger.init_db()
    with sqlite3.connect(path, timeout=10) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM cases")
        connection.execute("DELETE FROM events")
        connection.execute("DELETE FROM sqlite_sequence WHERE name = 'events'")
    if not args.empty:
        if args.profile == "basic":
            seed_demo()
        else:
            seed_oversight_demo(binary_only=args.profile == "functional")
    intact, broken_id = ledger.verify_chain()
    if not intact:
        raise RuntimeError(f"Demo chain is broken at #{broken_id}")
    print(json.dumps({
        "database": str(path), "synthetic_data": not args.empty,
        "profile": args.profile,
        "events": len(ledger.get_all_events()),
        "pending": len(ledger.get_pending_reviews()), "chain_intact": intact,
    }))


if __name__ == "__main__":
    main()
