"""SQLite business state and a SHA-256 audit chain (PLAN.md section 3).

Call init_db() at application startup. Prediction and gate events use flattened
dataclass dictionaries; gate payloads also include case_id. Every business state
change commits with its event. LOOPLEDGER_DB_PATH selects an isolated database.
"""

from contextlib import closing, contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Optional

from .schemas import GateResult, Prediction, ReviewAction


DB_PATH = Path(__file__).resolve().parent.parent / "loopledger.db"
GENESIS_HASH = "0" * 64


@contextmanager
def _connection(*, write=False):
    path = os.environ.get("LOOPLEDGER_DB_PATH", str(DB_PATH))
    with closing(sqlite3.connect(path, timeout=10)) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            # Serialize read/modify/append operations across Streamlit sessions.
            # BEGIN also gives multi-query readers a consistent snapshot.
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection


def init_db() -> None:
    """Create the contracted tables without clearing existing evidence."""
    with _connection(write=True) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                case_id TEXT,
                payload TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                prediction TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('auto', 'pending', 'reviewed'))
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS cases_by_status ON cases(status)"
        )


def _json(value: dict) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def _nonempty_text(value, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _finite_number(value, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")


def _prediction(payload: dict) -> Prediction:
    pred = Prediction(**payload)
    _nonempty_text(pred.case_id, "case_id")
    if not isinstance(pred.features, dict):
        raise ValueError("features must be a dictionary")
    if pred.decision not in ("approve", "reject"):
        raise ValueError("decision must be approve or reject")
    _finite_number(pred.confidence, "confidence")
    if not 0 <= pred.confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(pred.is_gold, bool):
        raise ValueError("is_gold must be a boolean")
    if pred.gold_correct_decision not in (None, "approve", "reject", "modify"):
        raise ValueError("gold_correct_decision must be approve, reject or modify")
    if pred.is_gold and pred.gold_correct_decision is None:
        raise ValueError("gold cases require gold_correct_decision; load backend cases with include_answers=True")
    if not isinstance(pred.top_factors, list):
        raise ValueError("top_factors must be a list")
    factors = []
    for factor in pred.top_factors:
        if not isinstance(factor, (list, tuple)) or len(factor) != 2:
            raise ValueError("each top factor must contain a name and contribution")
        name, contribution = factor
        _nonempty_text(name, "factor name")
        _finite_number(contribution, "factor contribution")
        factors.append((name, contribution))
    # JSON arrays become tuples again to preserve the shared Python contract.
    pred.top_factors = factors
    return pred


def _review(payload: dict) -> ReviewAction:
    action = ReviewAction(**payload)
    _nonempty_text(action.case_id, "case_id")
    _nonempty_text(action.reviewer, "reviewer")
    _nonempty_text(action.reason, "reason")
    if action.action not in ("approve", "reject", "modify"):
        raise ValueError("action must be approve, reject or modify")
    _finite_number(action.seconds_spent, "seconds_spent")
    if action.seconds_spent < 0:
        raise ValueError("seconds_spent must be non-negative")
    return action


def _apply_event(connection, event_type: str, payload: dict) -> None:
    case_id = payload.get("case_id")
    if event_type == "prediction":
        pred = _prediction(payload)
        if connection.execute(
            "SELECT 1 FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone():
            raise ValueError(f"Case {case_id!r} already exists")
        # Fail closed: a prediction stays pending until a gate routes it.
        connection.execute(
            "INSERT INTO cases (case_id, prediction, status) VALUES (?, ?, 'pending')",
            (case_id, _json(asdict(pred))),
        )
    elif event_type == "gate":
        gate = GateResult(**{key: value for key, value in payload.items() if key != "case_id"})
        if not isinstance(gate.needs_review, bool):
            raise ValueError("needs_review must be a boolean")
        if not isinstance(gate.reasons, list) or any(
            not isinstance(reason, str) for reason in gate.reasons
        ):
            raise ValueError("reasons must be a list of strings")
        if connection.execute(
            "SELECT 1 FROM events WHERE event_type = 'gate' AND case_id = ?", (case_id,)
        ).fetchone():
            raise ValueError(f"Case {case_id!r} has already been routed")
        result = connection.execute(
            "UPDATE cases SET status = ? WHERE case_id = ? AND status = 'pending'",
            ("pending" if gate.needs_review else "auto", case_id),
        )
        if result.rowcount != 1:
            raise ValueError(f"Case {case_id!r} does not exist or is no longer pending")
    elif event_type == "review":
        action = _review(payload)
        result = connection.execute(
            "UPDATE cases SET status = 'reviewed' WHERE case_id = ? AND status = 'pending'",
            (action.case_id,),
        )
        if result.rowcount != 1:
            raise ValueError(f"Case {case_id!r} does not exist or is no longer pending")


def _hash(prev_hash: str, ts: str, event_type: str, payload: str) -> str:
    # This exact concatenation is specified in PLAN.md section 3.3.
    return hashlib.sha256((prev_hash + ts + event_type + payload).encode("utf-8")).hexdigest()


def log_event(event_type: str, payload: dict) -> str:
    """Append evidence and update case state atomically; return the event hash.

    prediction: asdict(Prediction)
    gate: {"case_id": ..., **asdict(GateResult)}
    review: asdict(ReviewAction), also used by submit_review()
    Other event types (including export) append evidence without changing cases.
    """
    _nonempty_text(event_type, "event_type")
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dictionary")
    serialized = _json(payload)
    # Snapshot input before opening a transaction, including nested values.
    snapshot = json.loads(serialized)
    case_id = snapshot.get("case_id")
    if case_id is not None:
        _nonempty_text(case_id, "case_id")
    if event_type in ("prediction", "gate", "review") and case_id is None:
        raise ValueError("case_id is required for business events")
    with _connection(write=True) as connection:
        _apply_event(connection, event_type, snapshot)
        last = connection.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = last["hash"] if last else GENESIS_HASH
        ts = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        event_hash = _hash(prev_hash, ts, event_type, serialized)
        connection.execute(
            "INSERT INTO events (ts, event_type, case_id, payload, prev_hash, hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, event_type, case_id, serialized, prev_hash, event_hash),
        )
    return event_hash


def get_pending_reviews() -> list[Prediction]:
    """Return pending predictions in insertion order; gold metadata is backend-only."""
    with _connection() as connection:
        rows = connection.execute(
            "SELECT prediction FROM cases WHERE status = 'pending' ORDER BY rowid"
        ).fetchall()
    return [_prediction(json.loads(row["prediction"])) for row in rows]


def submit_review(action: ReviewAction) -> None:
    """Persist one review for a pending case; reject duplicate submissions."""
    if not isinstance(action, ReviewAction):
        raise TypeError("action must be a ReviewAction")
    log_event("review", asdict(action))


def submit_verified_review(action: ReviewAction, receipt: dict, *, workspace_nonce: str | None = None) -> None:
    """Atomically save verification evidence and the human review decision.

    An HMAC-signed, case/reviewer-bound one-use receipt is required. Unlike the
    two-event legacy demo helper, both events commit together or neither does.
    This protects the verified UI flow; the unrestricted legacy submit_review()
    still exists for compatibility and is not a global enforcement mechanism.
    """
    from .verification_service import verify_receipt, verify_workspace_pass
    if not isinstance(action, ReviewAction):
        raise TypeError("action must be ReviewAction")
    if workspace_nonce is not None:
        # Each submission checks the signed session grant again, including its expiry.
        # This is NOT a new camera challenge per case.
        if not verify_workspace_pass(receipt, action.reviewer, workspace_nonce):
            raise ValueError("30-minute reviewer session expired; re-verify your face")
        evidence = {
            "result": "passed", "verification_method": "periodic_workspace_face_check",
            "reviewer": action.reviewer, "case_id": action.case_id,
            "entry_challenge_id": receipt["entry_challenge_id"],
            "verified_at_epoch": receipt["issued_at_epoch"],
            "expires_at_epoch": receipt["expires_at_epoch"],
        }
    else:
        # Preserve the original case-scoped interface for existing callers/tests.
        if not verify_receipt(receipt, action.case_id, action.reviewer):
            raise ValueError("Valid, unexpired reviewer verification receipt required")
        if os.environ.get("LOOPLEDGER_REVIEWER_VERIFY_MODE", "").strip().lower() == "full":
            screen = receipt.get("screen_mouse")
            if (not isinstance(screen, dict) or screen.get("status") != "passed"
                    or screen.get("visible_cursor_checks", 0) < 4
                    or screen.get("cursor_alignment_rate", 0) < 0.75):
                raise ValueError("Full mode requires screen/OS cursor alignment evidence")
        evidence = {k: v for k, v in receipt.items() if k != "signature"}
    payloads = [("reviewer_verification", evidence), ("review", asdict(action))]
    with _connection(write=True) as connection:
        # Enforce existing case status & action schema FIRST, inside txn.
        _apply_event(connection, "review", asdict(action))
        prev = connection.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        previous_hash = prev["hash"] if prev else GENESIS_HASH
        for event_type, payload in payloads:
            serialized = _json(payload)
            stamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            event_hash = _hash(previous_hash, stamp, event_type, serialized)
            connection.execute(
                "INSERT INTO events (ts,event_type,case_id,payload,prev_hash,hash) "
                "VALUES (?,?,?,?,?,?)",
                (stamp, event_type, action.case_id, serialized, previous_hash, event_hash),
            )
            previous_hash = event_hash


def get_all_events() -> list[dict]:
    """Return chronological event dictionaries with decoded JSON payloads."""
    with _connection() as connection:
        rows = connection.execute("SELECT * FROM events ORDER BY id").fetchall()
    return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]


def verify_chain() -> tuple[bool, Optional[int]]:
    """Find the first broken hash/link or missing ID, without modifying evidence.

    The sequence counter detects tail deletion while it remains intact. A trusted
    external checkpoint is needed to detect full rewrites or counter resets.
    This verifies events, not the separate cases projection.
    """
    with _connection() as connection:
        rows = connection.execute("SELECT * FROM events ORDER BY id").fetchall()
        sequence = connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'events'"
        ).fetchone()
    prev_hash = GENESIS_HASH
    expected_id = 1
    for row in rows:
        if row["id"] != expected_id:
            return False, expected_id
        if row["prev_hash"] != prev_hash:
            return False, row["id"]
        if row["hash"] != _hash(prev_hash, row["ts"], row["event_type"], row["payload"]):
            return False, row["id"]
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            return False, row["id"]
        # case_id is duplicated outside the hashed payload for querying.
        if not isinstance(payload, dict) or row["case_id"] != payload.get("case_id"):
            return False, row["id"]
        prev_hash = row["hash"]
        expected_id += 1
    if sequence and sequence["seq"] >= expected_id:
        return False, expected_id
    return True, None


if __name__ == "__main__":
    init_db()
    print(f"Database ready: {os.environ.get('LOOPLEDGER_DB_PATH', str(DB_PATH))}")
