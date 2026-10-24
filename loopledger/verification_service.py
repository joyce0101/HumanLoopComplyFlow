"""Short-lived server-signed verification receipts for *local demo only*.

Combines a MediaPipe motion challenge, optional Windows screen/mouse cross-check,
and a logged-in reviewer account. Does NOT perform biometric face matching or
real-world ID proofing. Receipts are validated by ledger.submit_verified_review.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
import time

# Server-local secret: workers must share one process for this local prototype.
_SECRET = secrets.token_bytes(32)
SCHEMA_VERSION = "reviewer-interaction-prototype-v2"
RECEIPT_TTL = 60


def _signed_content(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def make_receipt(face_controller, case_id: str, reviewer: str, *,
                 monitor=None, require_screen: bool = False, now: float | None = None) -> dict | None:
    """Consume a valid face challenge exactly once; verify optional screen evidence."""
    if not case_id or not reviewer:
        return None
    screen = None
    if require_screen:
        if monitor is None or monitor.case_id != case_id or monitor.reviewer != reviewer:
            return None
        screen = monitor.evidence()
        if screen is None:
            return None
        # Require the monitor be tied to the same face challenge, not old data.
        if monitor.challenge_id != face_controller.snapshot()["challenge_id"]:
            return None
    face = face_controller.consume(case_id)
    if not face:
        return None
    epoch = time.time() if now is None else float(now)
    receipt = {
        "case_id": case_id,
        "reviewer": reviewer,
        "challenge_id": face["challenge_id"],
        "face_challenge": face["challenge"],
        "face_method": face["method"],
        "face_result": face["result"],
        "screen_mouse": screen if require_screen else {"status": "not_required"},
        "issued_at_epoch": int(epoch),
        "expires_at_epoch": int(epoch) + RECEIPT_TTL,
        "version": SCHEMA_VERSION,
        "result": "passed",
    }
    signature = hmac.new(_SECRET, _signed_content(receipt), hashlib.sha256).hexdigest()
    return {**receipt, "signature": signature}


def verify_receipt(receipt: dict, case_id: str, reviewer: str, *,
                   now: float | None = None) -> bool:
    if not isinstance(receipt, dict) or receipt.get("case_id") != case_id or receipt.get("reviewer") != reviewer:
        return False
    if (receipt.get("version") != SCHEMA_VERSION or receipt.get("result") != "passed"
            or receipt.get("face_result") != "passed"
            or receipt.get("face_challenge") not in ("blink_twice", "turn_head", "blink_and_turn_both")
            or not isinstance(receipt.get("challenge_id"), str)):
        return False
    if not isinstance(receipt.get("signature"), str):
        return False
    tick = time.time() if now is None else float(now)
    if (not isinstance(receipt.get("issued_at_epoch"), int)
            or not isinstance(receipt.get("expires_at_epoch"), int)
            or tick < receipt["issued_at_epoch"] - 5
            or tick > receipt["expires_at_epoch"]
            or receipt["expires_at_epoch"] - receipt["issued_at_epoch"] != RECEIPT_TTL):
        return False
    body = {key: value for key, value in receipt.items() if key != "signature"}
    expected = hmac.new(_SECRET, _signed_content(body), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, receipt["signature"])


# A verified entry challenge unlocks the GUI workspace for a limited period.
# The server signs the pass and binds it to the current Streamlit session nonce
# and authenticated account; navigating directly to any page cannot mint it.
WORKSPACE_ENTRY_CASE_ID = "__LOOPLEDGER_WORKSPACE_ENTRY__"
WORKSPACE_PASS_VERSION = "reviewer-workspace-gate-v1"
WORKSPACE_PASS_TTL = 1 * 60  # seconds; require a new face challenge after expiry


def issue_workspace_pass(receipt: dict, reviewer: str, session_nonce: str,
                         *, now: float | None = None) -> dict | None:
    """Issue a signed temporary GUI grant only after a valid entry receipt."""
    if not isinstance(reviewer, str) or not reviewer or not isinstance(session_nonce, str) or len(session_nonce) < 24:
        return None
    if not verify_receipt(receipt, WORKSPACE_ENTRY_CASE_ID, reviewer, now=now):
        return None
    tick = int(time.time() if now is None else now)
    body = {
        "version": WORKSPACE_PASS_VERSION,
        "reviewer": reviewer,
        "session_nonce": session_nonce,
        "entry_challenge_id": receipt["challenge_id"],
        "issued_at_epoch": tick,
        "expires_at_epoch": tick + WORKSPACE_PASS_TTL,
    }
    signature = hmac.new(_SECRET, _signed_content(body), hashlib.sha256).hexdigest()
    return {**body, "signature": signature}


def verify_workspace_pass(grant: dict, reviewer: str, session_nonce: str,
                          *, now: float | None = None) -> bool:
    """Check that the same signed-in reviewer/session completed face verification."""
    if not isinstance(grant, dict) or not isinstance(reviewer, str) or not isinstance(session_nonce, str):
        return False
    if (grant.get("version") != WORKSPACE_PASS_VERSION
            or grant.get("reviewer") != reviewer
            or grant.get("session_nonce") != session_nonce
            or not isinstance(grant.get("signature"), str)
            or not isinstance(grant.get("entry_challenge_id"), str)
            or not isinstance(grant.get("issued_at_epoch"), int)
            or not isinstance(grant.get("expires_at_epoch"), int)):
        return False
    tick = time.time() if now is None else float(now)
    if (tick < grant["issued_at_epoch"] - 5
            or tick > grant["expires_at_epoch"]
            or grant["expires_at_epoch"] - grant["issued_at_epoch"] != WORKSPACE_PASS_TTL):
        return False
    body = {key: value for key, value in grant.items() if key != "signature"}
    try:
        expected = hmac.new(_SECRET, _signed_content(body), hashlib.sha256).hexdigest()
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(expected, grant["signature"])
