"""Entry gate regression tests: no verified login => no business workspace.

These tests exercise signing and route protection without a webcam.  The
Streamlit UI itself still requires Windows/browser hands-on validation.
"""
from __future__ import annotations

import ast
import importlib
import secrets
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from loopledger.liveness import PresenceController, FaceObservation
from loopledger.verification_service import (
    WORKSPACE_ENTRY_CASE_ID, WORKSPACE_PASS_TTL,
    issue_workspace_pass, verify_workspace_pass, make_receipt,
)

ROOT = Path(__file__).resolve().parents[1]


def _make_valid_entry_receipt(reviewer="alice", *, now_epoch=None):
    ctl = PresenceController()
    ctl.start(WORKSPACE_ENTRY_CASE_ID, "blink_and_turn_both", now=0)
    face = lambda blink=.05, yaw=0: FaceObservation(1, blink, blink, yaw)
    sequence = ([face()] * 2 + [face(.9)] * 2 + [face()] * 2
                + [face(.9)] * 2 + [face()] * 2 + [face()] * 3
                + [face(yaw=.43)] * 2 + [face()] * 2
                + [face(yaw=-.43)] * 2 + [face()] * 2)
    for i, obs in enumerate(sequence):
        ctl.observe(WORKSPACE_ENTRY_CASE_ID, obs, now=1+i*.1)
    assert ctl.snapshot(now=4)["status"] == "passed"
    with patch("loopledger.liveness.time.monotonic", return_value=4.0):
        result = make_receipt(ctl, WORKSPACE_ENTRY_CASE_ID, reviewer, now=now_epoch)
    assert result is not None
    return result


def test_workspace_pass_only_minted_from_signed_entry_face_check():
    now = 2_000_000
    reviewer = "alice"
    nonce = secrets.token_hex(24)
    receipt = _make_valid_entry_receipt(reviewer, now_epoch=now)
    grant = issue_workspace_pass(receipt, reviewer, nonce, now=now+1)
    assert grant is not None
    assert verify_workspace_pass(grant, reviewer, nonce, now=now+2)
    assert verify_workspace_pass(grant, reviewer, nonce, now=now+1+WORKSPACE_PASS_TTL)
    assert not verify_workspace_pass(grant, reviewer, nonce, now=now+2+WORKSPACE_PASS_TTL)
    assert not verify_workspace_pass(grant, "bob", nonce, now=now+2)
    assert not verify_workspace_pass(grant, reviewer, secrets.token_hex(24), now=now+2)
    forged = {**grant, "reviewer":"bob"}
    assert not verify_workspace_pass(forged, "bob", nonce, now=now+2)
    forged = {**grant, "expires_at_epoch":now+99999}
    assert not verify_workspace_pass(forged, reviewer, nonce, now=now+2)
    assert not verify_workspace_pass({"verified":True}, reviewer, nonce, now=now+2)
    assert not issue_workspace_pass(receipt, "bob", nonce, now=now+1)
    assert not issue_workspace_pass(receipt, reviewer, "invalid", now=now+1)


def test_entry_receipt_cannot_be_replaced_by_ordinary_case_receipt():
    ctl = PresenceController()
    ctl.start("C-101", "blink_twice", now=0)
    obs = lambda blink: FaceObservation(1, blink, blink, 0)
    for i, v in enumerate([.05,.05,.9,.9,.05,.05,.9,.9,.05,.05]):
        ctl.observe("C-101", obs(v), now=1+i*.1)
    with patch("loopledger.liveness.time.monotonic", return_value=4.0):
        receipt = make_receipt(ctl, "C-101", "alice", now=2_000_000)
    assert issue_workspace_pass(receipt, "alice", secrets.token_hex(24), now=2_000_001) is None


def _ui_import(monkeypatch):
    # Streamlit is deliberately optional in the no-camera CI environment.
    # The mock is limited to the UI fixture and is never bundled as app code.
    if "streamlit" not in sys.modules:
        try:
            import streamlit  # noqa: F401
        except ImportError:
            monkeypatch.setitem(sys.modules, "streamlit", types.ModuleType("streamlit"))
    return importlib.import_module("loopledger.verification_ui")


def test_default_mode_requires_camera_and_off_cannot_bypass(monkeypatch):
    ui = _ui_import(monkeypatch)
    monkeypatch.delenv(ui.MODE_ENV, raising=False)
    monkeypatch.setenv("LOOPLEDGER_LIVENESS_MODE", "off")
    assert ui.mode() == "camera"  # obsolete setting can't disable auth
    monkeypatch.setenv(ui.MODE_ENV, "camera")
    assert ui.mode() == "camera"
    monkeypatch.setenv(ui.MODE_ENV, "full")
    assert ui.mode() == "full"
    monkeypatch.setenv(ui.MODE_ENV, "off")
    with pytest.raises(ValueError, match="removed"):
        ui.mode()


class Stopped(Exception):
    pass


class FakeSidebar:
    def __init__(self):
        self.log_out_seen = False
    def success(self, *_):
        pass
    def caption(self, *_):
        pass
    def button(self, label, **kwargs):
        self.log_out_seen = True
        return False


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.sidebar = FakeSidebar()
        self.messages = []
    def title(self, msg):
        self.messages.append(msg)
    def caption(self, msg):
        self.messages.append(msg)
    def markdown(self, msg):
        self.messages.append(msg)
    def warning(self, msg):
        self.messages.append(msg)
    def error(self, msg):
        self.messages.append(msg)
    def stop(self):
        raise Stopped()


def test_gate_stops_unauthenticated_and_authenticated_unverified_sessions(monkeypatch):
    ui = _ui_import(monkeypatch)
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)
    monkeypatch.setenv(ui.MODE_ENV, "camera")
    calls=[]
    monkeypatch.setattr(ui, "login_panel", lambda: calls.append("login"))
    monkeypatch.setattr(ui, "render_verification_panel", lambda scope: calls.append(scope))
    with pytest.raises(Stopped):
        ui.require_workspace_access()
    assert calls == ["login"]
    assert "Access control" in fake.messages[0]
    assert fake.sidebar.log_out_seen is False

    fake.session_state["vr_authenticated"]="alice"
    fake.session_state["vr_workspace_nonce"]=secrets.token_hex(24)
    with pytest.raises(Stopped):
        ui.require_workspace_access()
    assert calls == ["login", "login", WORKSPACE_ENTRY_CASE_ID]

    # A signed grant unlocks the exact verified account + browser session.
    epoch = time.time()
    receipt = _make_valid_entry_receipt("alice", now_epoch=epoch)
    grant = issue_workspace_pass(receipt,"alice",fake.session_state["vr_workspace_nonce"],now=epoch)
    fake.session_state["vr_workspace_pass"] = grant
    assert ui.workspace_unlocked()
    ui.require_workspace_access()
    assert fake.sidebar.log_out_seen
    fake.session_state["vr_authenticated"]="bob"
    assert not ui.workspace_unlocked()
    with pytest.raises(Stopped):
        ui.require_workspace_access()


def test_all_entry_scripts_gate_before_business_ui():
    pages = [ROOT / "app.py", *(ROOT / "pages" / s for s in (
        "1_Run_Batch.py", "2_Review_Queue.py", "3_Oversight_Dashboard.py", "4_Compliance.py"
    ))]
    for page in pages:
        tree = ast.parse(page.read_text(encoding="utf-8"), filename=str(page))
        main = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "main")
        # Session gate must occur directly after set_page_config and before
        # any DB reads or business buttons, including direct sidebar URLs.
        calls = []
        for statement in main.body[:4]:
            if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
                f = statement.value.func
                if isinstance(f, ast.Attribute):
                    calls.append((getattr(f.value,"id", ""), f.attr))
        assert calls[:2] == [("st", "set_page_config"),("verification_ui", "require_workspace_access")], page


def test_review_ui_has_no_unsigned_fallback():
    content = (ROOT / "pages" / "2_Review_Queue.py").read_text(encoding="utf-8")
    assert "ledger.submit_verified_review(action, grant, workspace_nonce=nonce)" in content
    assert "ledger.submit_review(action)" not in content
    assert "disabled=not ready" in content
