"""Periodic signed reviewer-session expiry and re-verification tests."""
import secrets
import time
from loopledger.verification_service import (
    WORKSPACE_PASS_TTL, WORKSPACE_ENTRY_CASE_ID, issue_workspace_pass,
    verify_workspace_pass,
)
from tests.test_workspace_access import _make_valid_entry_receipt

def test_thirty_minute_grant_expires_and_renewal():
    assert WORKSPACE_PASS_TTL == 1800
    reviewer = "alice"
    nonce = secrets.token_hex(24)
    t = int(time.time())
    grant = issue_workspace_pass(_make_valid_entry_receipt(reviewer, now_epoch=t), reviewer, nonce, now=t)
    assert grant is not None
    assert verify_workspace_pass(grant, reviewer, nonce, now=t+1799)
    assert not verify_workspace_pass(grant, reviewer, nonce, now=t+1801)
    assert not verify_workspace_pass(grant, "someone_else", nonce, now=t+1)
    renewed = issue_workspace_pass(_make_valid_entry_receipt(reviewer, now_epoch=t+1802), reviewer, nonce, now=t+1802)
    assert verify_workspace_pass(renewed, reviewer, nonce, now=t+1803)
