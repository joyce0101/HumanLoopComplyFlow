"""Mandatory local reviewer login + camera/desktop interaction check for Streamlit.

Mode via LOOPLEDGER_REVIEWER_VERIFY_MODE=camera|full. Default camera.
'full' requires Streamlit server to be running on the SAME Windows desktop as
reviewer. No photographs, video, screenshots, passwords, or pointer traces are
saved to the audit database; only high-level verification metrics.
"""
from __future__ import annotations

import os
import hashlib
import secrets
from pathlib import Path

import streamlit as st

from . import reviewer_auth
from .liveness import INSTRUCTIONS, PresenceController
from .liveness_camera import CameraProcessor, DEFAULT_MODEL
from .mouse_screen import MouseScreenMonitor
from .verification_service import (
    make_receipt, issue_workspace_pass, verify_workspace_pass,
    WORKSPACE_ENTRY_CASE_ID,
)

MODE_ENV = "LOOPLEDGER_REVIEWER_VERIFY_MODE"


def mode() -> str:
    """Enforce non-skippable GUI verification even without environment variables.

    Older documentation suggested 'off' to bypass login; deliberately reject
    it rather than silently letting a user operate the app without validation.
    """
    raw = os.environ.get(MODE_ENV)
    if raw is None:
        # Obsolete optional-mode settings must never silently disable the gate.
        raw = "camera"
    value = raw.strip().lower()
    if value not in ("camera", "full"):
        raise ValueError(
            f"{MODE_ENV} must be camera or full. The 'off' mode has been "
            "removed because authentication is mandatory."
        )
    return value


def authenticated_reviewer() -> str | None:
    return st.session_state.get("vr_authenticated")


def _stop_old_session() -> None:
    monitor = st.session_state.pop("vr_mouse_monitor", None)
    if monitor is not None:
        monitor.stop()
    processor = st.session_state.pop("vr_camera_processor", None)
    if processor is not None:
        processor.close()
    st.session_state.pop("vr_controller", None)
    st.session_state.pop("vr_case_id", None)
    st.session_state.pop("vr_case_reviewer", None)
    st.session_state.pop("vr_monitor_error", None)


def logout() -> None:
    """Drop session access and all outstanding biometric-interaction challenges."""
    _stop_old_session()
    for key in list(st.session_state.keys()):
        if key.startswith("vr_camera_consent_") or key.startswith("vr_screen_consent_"):
            st.session_state.pop(key, None)
    for key in ("vr_authenticated", "vr_workspace_nonce", "vr_workspace_pass", "vr_verified_user",
                "vr_login_password", "vr_login_user", "vr_screen_consent", "vr_camera_consent"):
        st.session_state.pop(key, None)


def login_panel() -> bool:
    """The FIRST gate: account login; never start a camera before login."""
    user = authenticated_reviewer()
    st.markdown("#### Step 1 / 2 — Reviewer account login")
    if user:
        left, right = st.columns([4, 1])
        left.success(f"Signed in: {user}")
        if right.button("Log out", key="vr_logout_before_access"):
            logout()
            st.rerun()
        return True
    st.info("Sign in with a local test reviewer account, then complete the camera challenge. "
            "Registration proves account control, not government identity.")
    tab_login, tab_register = st.tabs(["Sign in", "Create test reviewer"])
    with tab_login:
        with st.form("vr_signin"):
            user_input = st.text_input("Reviewer username", key="vr_login_user")
            password = st.text_input("Password", type="password", key="vr_login_password")
            pressed = st.form_submit_button("Sign in")
        if pressed:
            if reviewer_auth.authenticate(user_input, password):
                _stop_old_session()
                st.session_state["vr_authenticated"] = user_input.strip()
                st.session_state["vr_workspace_nonce"] = secrets.token_hex(24)
                st.session_state.pop("vr_workspace_pass", None)
                st.rerun()
            else:
                st.error("Invalid username/password or account temporarily locked.")
    with tab_register:
        with st.form("vr_register"):
            candidate = st.text_input("New username", key="vr_register_user")
            secret = st.text_input("New password (at least 10 characters)", type="password", key="vr_register_pw")
            secret_again = st.text_input("Repeat password", type="password", key="vr_register_confirm")
            pressed = st.form_submit_button("Create account")
        if pressed:
            if secret != secret_again:
                st.error("Passwords do not match.")
            else:
                try:
                    reviewer_auth.register(candidate, secret)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success("Account created. Switch to Sign in to continue.")
    return False


def workspace_unlocked() -> bool:
    """Never trust a boolean flag alone; validate the signed temporary grant."""
    return bool(
        authenticated_reviewer()
        and verify_workspace_pass(
            st.session_state.get("vr_workspace_pass"),
            authenticated_reviewer(),
            st.session_state.get("vr_workspace_nonce", ""),
        )
    )


def require_workspace_access() -> None:
    """Call this FIRST in every Streamlit entry point, before all business IO.

    The homepage and all four pages use the same gate; a URL to a page does not
    bypass authentication.  Workspaces unlock after a combined face challenge
    (and in full mode a local Windows cursor/screen cross-check).
    """
    try:
        level = mode()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
        return
    if not authenticated_reviewer():
        st.title("LoopLedger — Access control")
        st.caption("Sign in → prove human presence → access workspace")
        login_panel()
        st.stop()
        return

    if workspace_unlocked():
        reviewer = authenticated_reviewer()
        st.sidebar.success(f"Verified reviewer: {reviewer}")
        grant = st.session_state.get("vr_workspace_pass", {})
        remaining = max(0, int(grant.get("expires_at_epoch", 0) - __import__("time").time()))
        st.sidebar.caption(f"Next face verification in {remaining // 60:02d}:{remaining % 60:02d} (max 30 minutes).")
        if st.sidebar.button("Log out", key="vr_global_logout"):
            logout()
            st.rerun()
        return

    # Clear expired passes before displaying new challenge; retain account login.
    st.session_state.pop("vr_workspace_pass", None)
    st.title("LoopLedger — Access control")
    st.caption("Step 1: signed in ✓ · Step 2: live verification required")
    login_panel()
    st.markdown("#### Step 2 / 2 — Complete verification to enter")
    st.warning("All workspace pages stay locked until you pass this check. "
               "The camera is used for a movement challenge, not biometric face matching.")
    render_verification_panel(WORKSPACE_ENTRY_CASE_ID)
    # Camera frames are processed by a WebRTC callback thread. A Streamlit
    # fragment polls the trusted controller, so the reviewer does not need to
    # click Refresh or Finish once the challenge actually passes.
    _auto_complete_workspace_entry()
    st.stop()


@st.fragment(run_every="1s")
def _auto_complete_workspace_entry() -> None:
    """Automatically mint the 30-minute pass after the entry challenge passes.

    Never rely on a UI flag: consume the backend's signed, one-use receipt.
    In full mode this also waits until mouse/screen checks are complete.
    """
    if workspace_unlocked():
        st.rerun(scope="app")
        return
    reviewer = authenticated_reviewer()
    controller = st.session_state.get("vr_controller")
    if (not reviewer or st.session_state.get("vr_case_id") != WORKSPACE_ENTRY_CASE_ID
            or not isinstance(controller, PresenceController)):
        return
    if controller.snapshot().get("status") != "passed":
        return
    _, receipt = consume_verification(WORKSPACE_ENTRY_CASE_ID, reviewer)
    if receipt is None:
        if mode() == "full":
            st.caption("Face verified; waiting for the mouse/screen challenge to finish…")
        return
    grant = issue_workspace_pass(receipt, reviewer, st.session_state.get("vr_workspace_nonce", ""))
    if grant is None:
        st.error("Verification receipt expired. Start a fresh challenge.")
        return
    clear_success()
    st.session_state["vr_workspace_pass"] = grant
    # Rerun the whole requested page, not just the polling fragment.
    st.rerun(scope="app")


def _session(case_id: str, reviewer: str) -> PresenceController:
    if (st.session_state.get("vr_case_id") != case_id
            or st.session_state.get("vr_case_reviewer") != reviewer):
        _stop_old_session()
        st.session_state["vr_case_id"] = case_id
        st.session_state["vr_case_reviewer"] = reviewer
        st.session_state["vr_controller"] = PresenceController()
    return st.session_state["vr_controller"]


def render_verification_panel(case_id: str) -> None:
    level = mode()
    reviewer = authenticated_reviewer()
    if not reviewer:
        st.error("Sign in before attempting reviewer verification.")
        return
    controller = _session(case_id, reviewer)
    st.markdown("#### Reviewer identity & human-interaction check")
    st.caption(
        "Local prototype: a reviewer password plus camera movement challenge. "
        "Full mode adds local OS cursor/screen-visible cursor comparison. "
        "This is not biometric face matching or certified anti-spoofing."
    )
    if level == "full":
        st.warning(
            "FULL mode reads local Windows mouse coordinates and 160×160 pixel "
            "screen regions while the challenge is active. No frames or full trajectories "
            "are saved. Use only on your own Windows desktop after consent."
        )
        consent = st.checkbox(
            "I consent to local webcam and temporary mouse/screen-cursor analysis for this review.",
            key="vr_screen_consent_" + hashlib.sha256(case_id.encode()).hexdigest()[:16],
        )
    else:
        consent = st.checkbox(
            "I consent to a temporary webcam movement check.",
            key="vr_camera_consent_" + hashlib.sha256(case_id.encode()).hexdigest()[:16],
        )
    if st.button("Start new verification", key="vr_start", disabled=not consent):
        _stop_old_session()
        # Reset session identity after clearing old resources.
        controller = _session(case_id, reviewer)
        challenge = controller.start(case_id, kind="blink_and_turn_both")
        if level == "full":
            monitor = MouseScreenMonitor(case_id, reviewer, challenge["challenge_id"])
            try:
                monitor.start()
            except RuntimeError as exc:
                st.session_state["vr_monitor_error"] = str(exc)
            else:
                st.session_state["vr_mouse_monitor"] = monitor
                st.session_state.pop("vr_monitor_error", None)
        st.rerun()

    status = controller.snapshot()
    if status["status"] == "not_started":
        st.info("Consent and start a challenge. Blink twice, turn one way and back, then the other way and back.")
        return
    st.write(f"**Face challenge:** {status['status']} · {status['progress']}/4 stages")
    if status["status"] == "active":
        st.info(INSTRUCTIONS[status["kind"]])
        if status["message"] != INSTRUCTIONS[status["kind"]]:
            st.warning(status["message"])
        model_path = Path(os.environ.get("LOOPLEDGER_FACE_MODEL", str(DEFAULT_MODEL)))
        if not model_path.is_file():
            st.error("Face model is missing. Run: python scripts/download_liveness_model.py")
        else:
            try:
                from streamlit_webrtc import webrtc_streamer, WebRtcMode
            except ImportError:
                st.error("Install camera dependencies: pip install -r requirements-verification.txt")
            else:
                processor = st.session_state.get("vr_camera_processor")
                if (not isinstance(processor, CameraProcessor)
                        or processor.case_id != case_id
                        or processor.challenge_id != status["challenge_id"]
                        or processor._closed):
                    processor = CameraProcessor(controller, case_id, status["challenge_id"], model_path)
                    st.session_state["vr_camera_processor"] = processor
                webrtc_streamer(
                    key=f"vr_camera_{status['challenge_id']}",
                    mode=WebRtcMode.SENDRECV,
                    video_frame_callback=processor.video_frame_callback,
                    on_video_ended=processor.close,
                    media_stream_constraints={"video": True, "audio": False},
                    async_processing=True,
                )
        st.caption("Camera: press START in the video widget and allow permission. "
                   "Move in a well-lit room with only one face in view.")
    elif status["status"] == "passed":
        if case_id == WORKSPACE_ENTRY_CASE_ID:
            st.success("Face challenge passed. Opening the workspace automatically…")
        else:
            st.success("Face challenge passed. Finish any required mouse/screen check and submit this review within 60 seconds.")
    else:
        st.warning("Face challenge expired or already used; restart verification.")

    if level == "full":
        if error := st.session_state.get("vr_monitor_error"):
            st.error(error)
        monitor = st.session_state.get("vr_mouse_monitor")
        if monitor is None:
            st.error("Mouse/screen verification hasn't started; full-mode review remains blocked.")
        else:
            mouse = monitor.status()
            st.markdown("##### Mouse movement & screen cursor alignment")
            st.caption("Move your mouse at least ~180 px with several small pauses. "
                       "The screen check needs at least 4 visible cursor comparisons. "
                       "A browser-only installation or blocked screen capture cannot pass.")
            left, middle, right = st.columns(3)
            left.metric("Mouse path (px)", mouse["path_px"])
            middle.metric("Screen checks", mouse["visible_cursor_checks"])
            right.metric("Matches", mouse["aligned_cursor_checks"])
            st.write(f"Behavior signal: **{mouse['behavior']}** · Overall: **{mouse['status']}**")
            if mouse["cursor_alignment_rate"] is not None:
                st.write(f"Visible cursor ↔ OS cursor alignment: {mouse['cursor_alignment_rate']:.0%}")
            if mouse["error"]:
                st.error(mouse["error"])
            if mouse["teleport_count"]:
                st.warning("Unusual rapid pointer jumps observed; this alone does NOT establish automation.")
            # Preview OS trace vs independently observed cursor positions.
            # Only in RAM, shown to signed-in reviewer; never written to DB.
            traces = monitor.trace_preview()
            if traces["os_trace"]:
                import plotly.graph_objects as go
                fig = go.Figure()
                os_points = traces["os_trace"]
                fig.add_trace(go.Scatter(x=[p[0] for p in os_points],
                                         y=[p[1] for p in os_points], mode="lines",
                                         name="Actual OS cursor trajectory"))
                visible = traces["screen_pairs"]
                if visible:
                    fig.add_trace(go.Scatter(x=[p[2] for p in visible],
                                             y=[p[3] for p in visible], mode="markers",
                                             name="Cursor detected in screen frames"))
                fig.update_layout(height=280, xaxis_title="Screen X (pixels)",
                                  yaxis_title="Screen Y (pixels)",
                                  yaxis_autorange="reversed",
                                  margin=dict(l=20,r=20,t=10,b=20))
                st.plotly_chart(fig, width="stretch", key="vr_mouse_paths")
                st.caption("Blue line = operating-system pointer trace (downsampled); "
                           "other markers = positions inferred from the captured screen images. "
                           "Only captured cursor points are plotted; absent points are not filled in.")
    if case_id != WORKSPACE_ENTRY_CASE_ID:
        st.button("Refresh verification status", key="vr_refresh")


def consume_verification(case_id: str, reviewer: str) -> tuple[PresenceController | None, dict | None]:
    """Only the trusted backend controller may sign a one-use receipt."""
    level = mode()
    if (authenticated_reviewer() != reviewer or st.session_state.get("vr_case_id") != case_id):
        return None, None
    controller = st.session_state.get("vr_controller")
    if not isinstance(controller, PresenceController):
        return None, None
    monitor = st.session_state.get("vr_mouse_monitor") if level == "full" else None
    receipt = make_receipt(controller, case_id, reviewer, monitor=monitor, require_screen=(level == "full"))
    return controller, receipt


def restore_after_failed_write(controller: PresenceController, receipt: dict) -> None:
    controller.release(receipt["case_id"], receipt["challenge_id"])


def clear_success() -> None:
    _stop_old_session()


def review_ready(case_id: str) -> bool:
    """Review is allowed during the signed 30-minute workspace session."""
    return workspace_unlocked()


def _legacy_review_ready(case_id: str) -> bool:
    """Previous per-case challenge check (unused by the new review queue)."""
    if not workspace_unlocked() or authenticated_reviewer() != st.session_state.get("vr_case_reviewer"):
        return False
    if st.session_state.get("vr_case_id") != case_id:
        return False
    controller = st.session_state.get("vr_controller")
    if not isinstance(controller, PresenceController) or controller.snapshot().get("status") != "passed":
        return False
    if mode() == "full":
        monitor = st.session_state.get("vr_mouse_monitor")
        return bool(monitor is not None and monitor.case_id == case_id
                    and monitor.reviewer == authenticated_reviewer()
                    and monitor.challenge_id == controller.snapshot().get("challenge_id")
                    and monitor.evidence() is not None)
    return True
