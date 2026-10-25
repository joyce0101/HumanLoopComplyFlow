"""Deterministic challenge and persisted review tests. No webcam required."""
import pytest

from loopledger.liveness import (
    FaceObservation, PresenceController, CHALLENGE_SECONDS, PASS_SECONDS,
    submit_review_with_presence,
)


def open_eyes():
    return FaceObservation(1, 0.08, 0.07, 0)


def shut_eyes():
    return FaceObservation(1, 0.87, 0.93, 0)


def blink_twice(ctl, case_id="CASE-A", t=1.0):
    for obs in [open_eyes()] * 2 + [shut_eyes()] * 2 + [open_eyes()] * 2 + [shut_eyes()] * 2 + [open_eyes()] * 2:
        ctl.observe(case_id, obs, now=t)
        t += 0.2
    return t


def test_blink_twice_requires_open_close_open_twice():
    c = PresenceController()
    c.start("CASE-A", "blink_twice", now=0)
    for i in range(4):
        c.observe("CASE-A", shut_eyes(), now=i + 1)
    assert c.snapshot(now=6)["status"] == "active"
    end = blink_twice(c)
    assert c.snapshot(now=end)["status"] == "passed"
    proof = c.consume("CASE-A", now=end)
    assert proof["challenge"] == "blink_twice"
    assert proof["result"] == "passed"
    assert c.consume("CASE-A", now=end) is None


def test_no_static_picture_or_wrong_case_pass():
    c = PresenceController()
    c.start("CASE-A", "blink_twice", now=0)
    for i in range(20):
        c.observe("CASE-A", open_eyes(), now=i / 2)
    assert c.consume("CASE-A", now=11) is None
    blink_twice(c)
    assert c.consume("CASE-B", now=5) is None
    assert c.consume("CASE-A", now=5) is not None


def test_head_turn_requires_centre_turn_return():
    c = PresenceController()
    c.start("CASE-A", "turn_head", now=0)
    for i in range(3):
        c.observe("CASE-A", FaceObservation(1, 0.1, 0.1, 0.01), now=0.1 + i * 0.1)
    assert c.snapshot(now=0.5)["status"] == "active"
    for i in range(2):
        c.observe("CASE-A", FaceObservation(1, 0.1, 0.1, -0.4), now=0.6+i * 0.1)
    assert c.snapshot(now=0.8)["status"] == "active"
    for i in range(3):
        c.observe("CASE-A", FaceObservation(1, 0.1, 0.1, 0.02), now=0.9+i * 0.1)
    assert c.snapshot(now=1.5)["status"] == "passed"


def test_expiration_and_fresh_challenge():
    c = PresenceController()
    first=c.start("A", "blink_twice", now=0)
    assert c.snapshot(now=CHALLENGE_SECONDS+1)["status"] == "expired"
    assert c.consume("A", now=CHALLENGE_SECONDS+1) is None
    next_challenge=c.start("A", "blink_twice", now=100)
    assert first["challenge_id"] != next_challenge["challenge_id"]
    end=blink_twice(c, "A", 101)
    assert c.consume("A", now=end+PASS_SECONDS+1) is None


def test_switching_case_resets_and_multiple_faces_cannot_pass():
    c=PresenceController()
    c.start("A", "blink_twice", now=0)
    for i in range(10):
        c.observe("A", FaceObservation(2, .9,.9,0), now=1+i*.1)
    assert c.consume("A", now=3) is None
    c.start("B", "blink_twice", now=4)
    assert c.snapshot(now=4)["case_id"] == "B"
    assert c.consume("A", now=4) is None


def test_failures_and_retry_reuses_unexpired_one_time_proof():
    c=PresenceController()
    c.start("A", "blink_twice", now=0)
    end=blink_twice(c, "A")
    proof=c.consume("A", now=end)
    assert proof is not None
    c.release("A", proof["challenge_id"], now=end)
    assert c.consume("A", now=end) is not None
    assert c.consume("A", now=end) is None


def test_persisted_liveness_event_then_review(tmp_path, monkeypatch):
    from loopledger import ledger
    from loopledger.schemas import Prediction, ReviewAction
    from dataclasses import asdict
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(tmp_path / "liveness.db"))
    ledger.init_db()
    pred = Prediction("LIVE-1", {"credit_amount":1000}, "approve", .90, [])
    ledger.log_event("prediction", asdict(pred))
    ledger.log_event("gate", {"case_id":"LIVE-1", "needs_review":True, "reasons":["manual test"]})
    c=PresenceController()
    c.start("LIVE-1", "blink_twice", now=0)
    end=blink_twice(c, "LIVE-1")
    proof=c.consume("LIVE-1", now=end)
    action=ReviewAction("LIVE-1", "test_reviewer", "reject", "Checked all evidence", 10)
    submit_review_with_presence(ledger, action, proof)
    events=ledger.get_all_events()
    assert [e["event_type"] for e in events]==["prediction","gate","reviewer_liveness","review"]
    assert events[2]["payload"]["challenge_id"]==proof["challenge_id"]
    assert events[2]["payload"]["reviewer"]=="test_reviewer"
    assert "image" not in str(events[2]["payload"])
    assert ledger.verify_chain()==(True,None)
    assert ledger.get_pending_reviews()==[]


def test_bad_or_wrong_case_proof_rejected(tmp_path,monkeypatch):
    from loopledger import ledger
    from loopledger.schemas import ReviewAction
    monkeypatch.setenv("LOOPLEDGER_DB_PATH",str(tmp_path / "empty.db"))
    ledger.init_db()
    a=ReviewAction("A","one","approve","details",1.)
    with pytest.raises(ValueError):
        submit_review_with_presence(ledger,a,{"case_id":"B","result":"passed","challenge_id":"x"})
    assert ledger.get_all_events()==[]


def test_invalid_challenge_type():
    ctl=PresenceController()
    with pytest.raises(ValueError):
        ctl.start("A", "photo_of_face")
    with pytest.raises(ValueError):
        ctl.start("", "blink_twice")


def test_short_blink_is_detectable_at_video_framerate():
    ctl=PresenceController()
    ctl.start("A", "blink_twice", now=0)
    sequence=[open_eyes(),open_eyes(),shut_eyes(),open_eyes(),open_eyes(),
              shut_eyes(),open_eyes(),open_eyes()]
    for i, observation in enumerate(sequence):
        ctl.observe("A", observation, now=.1 + i*.08)
    assert ctl.snapshot(now=2)["status"] == "passed"


def test_late_frames_from_previous_challenge_are_ignored():
    ctl=PresenceController()
    previous=ctl.start("A", "blink_twice", now=0)
    current=ctl.start("A", "blink_twice", now=10)
    assert previous["challenge_id"] != current["challenge_id"]
    for i in range(20):
        ctl.observe("A", open_eyes() if i%2 else shut_eyes(),
                    now=10+i*.1,challenge_id=previous["challenge_id"])
    assert ctl.snapshot(now=15)["status"] == "active"
    assert ctl.snapshot(now=15)["progress"] == 0


def test_camera_parser_extracts_face_features_without_loading_ml_runtime():
    from types import SimpleNamespace as NS
    from loopledger.liveness_camera import CameraProcessor
    coords=[NS(x=.5) for _ in range(264)]
    coords[33]=NS(x=.2)
    coords[263]=NS(x=.8)
    coords[1]=NS(x=.5)
    result=NS(face_landmarks=[coords], face_blendshapes=[[NS(category_name="eyeBlinkLeft",score=.8),
                                                         NS(category_name="eyeBlinkRight",score=.9)]])
    parsed=CameraProcessor._read(result)
    assert parsed.face_count==1
    assert parsed.left_eye_blink==pytest.approx(.8)
    assert parsed.right_eye_blink==pytest.approx(.9)
    assert parsed.yaw_offset==pytest.approx(0)
    assert CameraProcessor._read(NS(face_landmarks=[coords,coords],face_blendshapes=[])).face_count==2
