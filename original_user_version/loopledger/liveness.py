"""Prototype active face-presence challenge for LoopLedger reviewers.

Privacy: no image, video, face embedding or landmarks are written to disk/DB.
Security: UI-level demonstration, NOT a biometric identity check or PAD-certified
anti-spoofing. A compromised client/server can forge observations or bypass the UI.

No third-party image packages are needed to test this finite-state machine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import secrets
import threading
import time
from typing import Optional

CHALLENGES = ("blink_twice", "turn_head", "blink_and_turn_both")
INSTRUCTIONS = {
    "blink_twice": "Look at the camera, then blink BOTH eyes twice.",
    "turn_head": "Look straight ahead, turn your head to either side, then face front.",
    "blink_and_turn_both": "Blink twice; turn head to one side and centre, then the OTHER side and centre.",
}
CHALLENGE_SECONDS = 125.0
PASS_SECONDS = 60.0
MIN_FRAMES = 2

# Prototype thresholds used by the MediaPipe Face Landmarker blendshape scores.
# Keep a clear gap (hysteresis): one static image cannot count as a blink.
# Relaxed from 0.25/0.55 because simultaneous 0.55 readings are often missed.
EYES_OPEN_MAX = 0.30
EYES_CLOSED_MIN = 0.30


@dataclass(frozen=True)
class FaceObservation:
    """Non-identifying measurements derived from one video frame."""
    face_count: int
    left_eye_blink: float = 0.0
    right_eye_blink: float = 0.0
    yaw_offset: float = 0.0


@dataclass
class _Challenge:
    case_id: str
    challenge_id: str
    kind: str
    issued_at: float
    expires_at: float
    passed_at: Optional[float] = None
    consumed: bool = False
    phase: int = 0
    phase_frames: int = 0
    progress: int = 0
    missing_frames: int = 0
    baseline: Optional[float] = None
    first_side_sign: Optional[int] = None
    baseline_values: list[float] = field(default_factory=list)
    last_error: str = ""


class PresenceController:
    """Thread-safe per-Streamlit-session active challenge tracker.

    Calling `observe` requires a real camera pipeline in the UI. The tracker is
    deliberately independent of the detector so motion can be unit-tested.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._challenge: Optional[_Challenge] = None

    def start(self, case_id: str, kind: str | None = None, *, now=None) -> dict:
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("A nonempty case_id is required")
        if kind is None:
            kind = secrets.choice(CHALLENGES)
        if kind not in CHALLENGES:
            raise ValueError(f"Unknown challenge: {kind!r}")
        tick = time.monotonic() if now is None else float(now)
        with self._lock:
            self._challenge = _Challenge(
                case_id=case_id,
                challenge_id=secrets.token_hex(16),
                kind=kind,
                issued_at=tick,
                expires_at=tick + CHALLENGE_SECONDS,
            )
            return self._snapshot(tick)

    def reset(self) -> None:
        with self._lock:
            self._challenge = None

    @staticmethod
    def _state(c: _Challenge, tick: float) -> str:
        if c.consumed:
            return "consumed"
        if c.passed_at is not None:
            return "passed" if tick <= c.passed_at + PASS_SECONDS else "expired"
        return "active" if tick <= c.expires_at else "expired"

    def _snapshot(self, tick: float) -> dict:
        c = self._challenge
        if c is None:
            return {"status": "not_started", "case_id": None, "kind": None, "progress": 0,
                    "message": "Start a presence challenge to continue."}
        status = self._state(c, tick)
        message = (
            "Challenge passed. Submit your review before the proof expires." if status == "passed"
            else "Challenge has expired. Start a new challenge." if status == "expired"
            else "Proof was already used; start a new challenge." if status == "consumed"
            else c.last_error or INSTRUCTIONS[c.kind]
        )
        # Phase is only used for live, in-memory camera diagnostics; it is not
        # written to the audit ledger and does not bypass any state checks.
        return {"status": status, "case_id": c.case_id, "kind": c.kind,
                "progress": c.progress, "phase": c.phase,
                "challenge_id": c.challenge_id, "message": message}

    def snapshot(self, *, now=None) -> dict:
        tick = time.monotonic() if now is None else float(now)
        with self._lock:
            return self._snapshot(tick)

    @staticmethod
    def _step(c: _Challenge, predicate: bool, next_phase: int, needed: int = MIN_FRAMES) -> bool:
        c.phase_frames = c.phase_frames + 1 if predicate else 0
        if c.phase_frames < needed:
            return False
        c.phase_frames = 0
        c.phase = next_phase
        return True

    def observe(self, case_id: str, observation: FaceObservation, *, now=None, challenge_id=None) -> dict:
        """Consume a camera measurement; no Streamlit calls or DB writes."""
        tick = time.monotonic() if now is None else float(now)
        with self._lock:
            c = self._challenge
            if (c is None or c.case_id != case_id or self._state(c, tick) != "active"
                    or (challenge_id is not None and challenge_id != c.challenge_id)):
                return self._snapshot(tick)
            if observation.face_count != 1:
                c.missing_frames += 1
                c.last_error = "Show exactly one face in the camera frame."
                if c.missing_frames >= 5:
                    c.phase = c.progress = c.phase_frames = 0
                    c.baseline = None
                    c.baseline_values.clear()
                return self._snapshot(tick)
            c.missing_frames = 0
            c.last_error = ""
            left = observation.left_eye_blink
            right = observation.right_eye_blink
            if not all(math.isfinite(float(x)) for x in (left, right, observation.yaw_offset)):
                return self._snapshot(tick)
            if c.kind in ("blink_twice", "blink_and_turn_both"):
                # Require BOTH eyes and an actual open -> closed -> open
                # sequence. These values are blendshape *scores*, not EAR.
                eyes_open = left <= EYES_OPEN_MAX and right <= EYES_OPEN_MAX
                eyes_closed = left >= EYES_CLOSED_MIN and right >= EYES_CLOSED_MIN
                if c.phase == 0:  # Require a real open-eye baseline.
                    self._step(c, eyes_open, 1)
                elif c.phase == 1:
                    self._step(c, eyes_closed, 2, needed=1)
                elif c.phase == 2 and self._step(c, eyes_open, 1):
                    c.progress += 1
                    if c.progress >= 2:
                        if c.kind == "blink_twice":
                            c.passed_at = tick
                        else:
                            c.phase = 3
                            c.baseline_values.clear()
                elif c.kind == "blink_and_turn_both":
                    yaw = observation.yaw_offset
                    if c.phase == 3:  # calibrate face looking forward
                        if abs(yaw) <= 0.18:
                            c.baseline_values.append(yaw)
                            if len(c.baseline_values) >= 3:
                                c.baseline = sum(c.baseline_values) / len(c.baseline_values)
                                c.phase = 4
                        else:
                            c.baseline_values.clear()
                    elif c.phase == 4:  # visit first side
                        relative = yaw - (c.baseline or 0.0)
                        if self._step(c, abs(relative) >= 0.22, 5):
                            c.first_side_sign = 1 if relative > 0 else -1
                    elif c.phase == 5:  # return to forward
                        if self._step(c, abs(yaw - (c.baseline or 0)) <= 0.11, 6):
                            c.progress = 3
                    elif c.phase == 6:  # visit opposite side
                        relative = yaw - (c.baseline or 0)
                        if self._step(c, (relative * (c.first_side_sign or 1)) <= -0.22, 7):
                            c.progress = 3
                    elif c.phase == 7 and self._step(c, abs(yaw - (c.baseline or 0)) <= 0.11, 8):
                        c.progress = 4
                        c.passed_at = tick
            else:  # turn_head: relative horizontal nose displacement; mirror-agnostic
                yaw = observation.yaw_offset
                if c.phase == 0:
                    if abs(yaw) <= 0.18:
                        c.baseline_values.append(yaw)
                        if len(c.baseline_values) >= 3:
                            c.baseline = sum(c.baseline_values) / len(c.baseline_values)
                            c.phase = 1
                    else:
                        c.baseline_values.clear()
                elif c.phase == 1:
                    if self._step(c, abs(yaw - (c.baseline or 0)) >= 0.22, 2):
                        c.progress = 1
                elif c.phase == 2 and self._step(c, abs(yaw - (c.baseline or 0)) <= 0.10, 3):
                    c.progress = 2
                    c.passed_at = tick
            return self._snapshot(tick)

    def error(self, case_id: str, message: str) -> None:
        with self._lock:
            c = self._challenge
            if c and c.case_id == case_id:
                c.last_error = message[:180]

    def consume(self, case_id: str, *, now=None) -> dict | None:
        """Return a one-use evidence token only when this case recently passed."""
        tick = time.monotonic() if now is None else float(now)
        with self._lock:
            c = self._challenge
            if c is None or c.case_id != case_id or self._state(c, tick) != "passed":
                return None
            c.consumed = True
            return {
                "case_id": c.case_id,
                "challenge_id": c.challenge_id,
                "challenge": c.kind,
                "result": "passed",
                "method": "active_face_landmarker_prototype_v1",
                "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round((c.passed_at or tick) - c.issued_at, 3),
                "version": "prototype-v1",
            }

    def release(self, case_id: str, challenge_id: str, *, now=None) -> None:
        """Enable retry after a DB write failure while the proof remains valid."""
        tick = time.monotonic() if now is None else float(now)
        with self._lock:
            c = self._challenge
            if c and c.case_id == case_id and c.challenge_id == challenge_id:
                if c.passed_at is not None and tick <= c.passed_at + PASS_SECONDS:
                    c.consumed = False


def submit_review_with_presence(ledger, action, proof: dict) -> None:
    """Audit a consumed challenge before review; never write images or geometry.

    This UI-level protocol uses B's existing two event interfaces. The pair of
    writes is NOT one transaction; failure of the second may leave a liveness
    event without a review. Proper server-side enforcement requires a B-owned
    transactional/authorization API in a later iteration.
    """
    if not proof or proof.get("result") != "passed" or proof.get("case_id") != action.case_id:
        raise ValueError("A matching, consumed live-challenge proof is required")
    if not isinstance(proof.get("challenge_id"), str):
        raise ValueError("Missing challenge ID")
    ledger.log_event("reviewer_liveness", {**proof, "reviewer": action.reviewer})
    ledger.submit_review(action)
