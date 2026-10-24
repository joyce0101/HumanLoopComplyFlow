"""Local-only deterministic validation without a camera or display server."""
from dataclasses import asdict
from types import SimpleNamespace
import math
import time

import numpy as np
import pytest

from loopledger import ledger, reviewer_auth
from loopledger.liveness import FaceObservation, PresenceController
from loopledger.mouse_screen import (
    MousePoint, evaluate_mouse_trace, compare_cursor_locations,
    find_cursor_difference, MouseScreenMonitor,
)
from loopledger.schemas import Prediction, ReviewAction
from loopledger.verification_service import make_receipt, verify_receipt


def face(eyes=0.05, yaw=0):
    return FaceObservation(1, eyes, eyes, yaw)


def finish_combined(controller, case, start=1.0):
    sequence = ([face()] * 2 + [face(.9)] * 2 + [face()] * 2
                + [face(.9)] * 2 + [face()] * 2
                + [face()] * 3  # forward baseline
                + [face(yaw=.43)] * 2  # first side
                + [face()] * 2  # return
                + [face(yaw=-.44)] * 2  # opposite side
                + [face()] * 2)  # return
    for i, observation in enumerate(sequence):
        controller.observe(case, observation, now=start + i * 0.1)
    return start + len(sequence) * .1


def test_combined_requires_two_blinks_and_both_directions():
    p=PresenceController()
    p.start("CASE", "blink_and_turn_both", now=0)
    end=finish_combined(p,"CASE")
    assert p.snapshot(now=end)["status"] == "passed"
    assert p.snapshot(now=end)["progress"] == 4


def test_combined_one_side_only_does_not_pass():
    p=PresenceController()
    p.start("CASE", "blink_and_turn_both", now=0)
    # only blink and first side
    sequence=[face()]*2+[face(.9)]*2+[face()]*2+[face(.9)]*2+[face()]*2+[face()]*3+[face(yaw=.42)]*2+[face()]*2
    for i,o in enumerate(sequence):p.observe("CASE",o,now=1+i*.1)
    assert p.snapshot(now=5)["status"] == "active"


def test_trace_anomaly_is_only_a_signal():
    steady=[MousePoint(i*.05, 100+i*6, 60+(i%4)*6) for i in range(50)]
    results=evaluate_mouse_trace(steady)
    assert results["path_px"]>180
    assert results["behavior"]=="observed_motion"
    anomalous=[MousePoint(i*.05,i*5,20) for i in range(12)]
    anomalous.extend([MousePoint(.56,800,300),MousePoint(.58,1500,500)])
    assert evaluate_mouse_trace(anomalous)["behavior"]=="unusual_motion"


def test_cursor_match_and_missing_are_distinct():
    assert compare_cursor_locations((50,50),(58,50))["aligned"] is True
    assert compare_cursor_locations((50,50),(150,50))["aligned"] is False
    assert compare_cursor_locations((50,50),None) is None


def test_visible_cursor_diff_finds_small_change_not_entire_screen():
    background=np.zeros((100,100,4),dtype=np.uint8)
    screenshot=background.copy()
    screenshot[30:42,45:55,:3]=255
    assert find_cursor_difference(background,screenshot,left=100,top=200) == (150,236)
    screenshot[:,:,:3]=255
    assert find_cursor_difference(background,screenshot) is None


def test_login_hashed_and_locked(tmp_path,monkeypatch):
    monkeypatch.setenv("LOOPLEDGER_AUTH_DB_PATH",str(tmp_path/"auth.db"))
    reviewer_auth.register("alice", "correctHorse123")
    assert reviewer_auth.authenticate("alice","correctHorse123",now=1_000)
    assert not reviewer_auth.authenticate("alice","not-the-password",now=1_001)
    assert reviewer_auth.authenticate("alice","correctHorse123",now=1_002)
    for i in range(5):
        assert not reviewer_auth.authenticate("alice","invalid-password",now=1_010)
    assert not reviewer_auth.authenticate("alice","correctHorse123",now=1_015)
    assert reviewer_auth.authenticate("alice","correctHorse123",now=1_041)
    with pytest.raises(ValueError):reviewer_auth.register("alice","anotherPassword123")


def test_short_password_or_bad_name_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv("LOOPLEDGER_AUTH_DB_PATH",str(tmp_path/"auth.db"))
    with pytest.raises(ValueError):reviewer_auth.register("admin", "short")
    with pytest.raises(ValueError):reviewer_auth.register("!invalid", "perfectlyGoodPassword")


def test_receipt_valid_and_tamper_detected(tmp_path,monkeypatch):
    p=PresenceController()
    p.start("ONE", "blink_and_turn_both",now=0)
    finish_combined(p,"ONE")
    # make_receipt reads real monotonic clock, so simulate liveness with a
    # freshly issued normal challenge for expiry-compatible receipt.
    from unittest.mock import patch
    with patch("loopledger.liveness.time.monotonic", return_value=4.0):
        receipt=make_receipt(p,"ONE","alice",now=1_000_000)
    assert verify_receipt(receipt,"ONE","alice",now=1_000_002)
    assert not verify_receipt(receipt,"ONE","bob",now=1_000_002)
    assert not verify_receipt(receipt,"ONE","alice",now=1_000_062)
    tampered=dict(receipt);tampered["reviewer"]="bob"
    assert not verify_receipt(tampered,"ONE","bob",now=1_000_002)
    assert p.consume("ONE",now=4) is None


def test_full_mode_requires_mouse_proof():
    p=PresenceController(); p.start("ONE","blink_and_turn_both",now=0)
    finish_combined(p,"ONE")
    from unittest.mock import patch
    monitor=SimpleNamespace(case_id="ONE",reviewer="alice",challenge_id=p.snapshot(now=4)["challenge_id"],evidence=lambda:None)
    with patch("loopledger.liveness.time.monotonic",return_value=4):
        assert make_receipt(p,"ONE","alice",monitor=monitor,require_screen=True) is None
    assert p.consume("ONE",now=4) is not None  # no premature burn


def test_atomic_review_and_hash(tmp_path,monkeypatch):
    monkeypatch.setenv("LOOPLEDGER_DB_PATH",str(tmp_path/"verification.db"))
    ledger.init_db()
    pred=Prediction("ONE", {"credit_amount":1000},"approve",.7,[])
    ledger.log_event("prediction",asdict(pred))
    ledger.log_event("gate",{"case_id":"ONE","needs_review":True,"reasons":["test"]})
    p=PresenceController();p.start("ONE","blink_and_turn_both",now=0)
    finish_combined(p,"ONE")
    from unittest.mock import patch
    with patch("loopledger.liveness.time.monotonic",return_value=4):
        receipt=make_receipt(p,"ONE","alice")
    assert receipt is not None
    action=ReviewAction("ONE","alice","reject","Checked evidence",20)
    ledger.submit_verified_review(action,receipt)
    events=ledger.get_all_events()
    assert [e["event_type"] for e in events]==["prediction","gate","reviewer_verification","review"]
    assert ledger.verify_chain()==(True,None)
    assert not ledger.get_pending_reviews()
    assert "signature" not in str(events[2]["payload"])
    with pytest.raises(ValueError):ledger.submit_verified_review(action,receipt)
    assert len(ledger.get_all_events())==4


def test_rejected_receipt_does_not_write_any_event(tmp_path,monkeypatch):
    monkeypatch.setenv("LOOPLEDGER_DB_PATH",str(tmp_path/"verification.db"))
    ledger.init_db()
    pred=Prediction("ONE",{"credit_amount":1000},"approve",.7,[])
    ledger.log_event("prediction",asdict(pred))
    ledger.log_event("gate",{"case_id":"ONE","needs_review":True,"reasons":["test"]})
    action=ReviewAction("ONE","alice","reject","Checked evidence",20)
    with pytest.raises(ValueError):
        ledger.submit_verified_review(action,{"result":"passed","case_id":"ONE","reviewer":"alice"})
    assert len(ledger.get_all_events())==2
    assert len(ledger.get_pending_reviews())==1


def test_local_windows_enforced(monkeypatch):
    import loopledger.mouse_screen as m
    monkeypatch.setattr(m.platform,"system",lambda:"Linux")
    worker=MouseScreenMonitor("ONE","alice","challenge")
    with pytest.raises(RuntimeError,match="Windows"):
        worker.start()
