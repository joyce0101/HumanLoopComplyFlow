"""Verify compliance UI states, exact exports, and stale-download invalidation."""

import hashlib
import json
from pathlib import Path
import types
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages/4_Compliance.py"


def open_page():
    app = AppTest.from_file(str(PAGE), default_timeout=20)
    app.run()
    assert not app.exception
    assert not app.radio
    return app


def button(app, label):
    return next(item for item in app.button if item.label == label)


def verify(app):
    button(app, "Verify chain").click().run()
    assert not app.exception


def generate(app):
    button(app, "Generate report").click().run()
    assert not app.exception


def download_disabled(app):
    downloads = app.get("download_button")
    assert len(downloads) == 2
    return [item.proto.disabled for item in downloads]


def backend_modules(*, intact=True, broken_id=None):
    ledger = types.ModuleType("loopledger.ledger")
    ledger.verify_chain = lambda: (intact, broken_id)
    evidence = types.ModuleType("loopledger.evidence")
    report = {
        "project": "LoopLedger", "report_id": "backend-001",
        "data_origin": "Backend test fixture",
        "integrity": {"chain_intact": intact, "first_broken_event_id": broken_id},
    }
    markdown = "# Backend evidence\n\n**Report ID:** `backend-001`\n\nFixture report.\n"
    evidence.build_report_json = lambda: report
    evidence.build_report = lambda: markdown
    return ledger, evidence


def test_initial_state_is_unchecked_with_no_preview_and_disabled_downloads():
    app = open_page()
    assert app.session_state["cp_chain"]["status"] == "unchecked"
    assert button(app, "Generate report").disabled
    assert download_disabled(app) == [True, True]
    assert not app.session_state.get("cp_export")


@pytest.mark.parametrize(
    "scenario,status", [("Pass", "passed"), ("Inconsistency at #17", "inconsistent"), ("Execution error", "error")]
)
def test_backend_verification_exposes_all_completed_chain_states(scenario, status):
    app = open_page()
    ledger, _ = backend_modules(intact=scenario == "Pass", broken_id=17 if scenario != "Pass" else None)
    if scenario == "Execution error":
        def fail():
            raise RuntimeError("Database unavailable")
        ledger.verify_chain = fail
    assert app.session_state["cp_chain"]["status"] == "unchecked"
    with patch.dict("sys.modules", {"loopledger.ledger": ledger}):
        verify(app)
    assert app.session_state["cp_chain"]["status"] == status
    assert download_disabled(app) == [True, True]
    assert button(app, "Generate report").disabled == (status == "error")


def test_generated_markdown_preview_matches_download_bundle_and_json():
    app = open_page()
    verify(app)
    generate(app)
    bundle = app.session_state["cp_export"]
    data = json.loads(bundle["json_text"])
    assert data["integrity"]["chain_intact"] is True
    assert "Local SQLite ledger snapshot" in data["data_origin"]
    assert data["report_id"] in bundle["markdown"]
    # Streamlit trims surrounding whitespace before rendering Markdown.
    assert any(item.value == bundle["markdown"].strip() for item in app.markdown)
    assert download_disabled(app) == [False, False]
    assert all(item.proto.url for item in app.get("download_button"))
    report_id = data["report_id"]
    app.run()
    assert not app.exception
    assert json.loads(app.session_state["cp_export"]["json_text"])["report_id"] == report_id


def test_inconsistent_chain_remains_exportable_as_failure_evidence():
    app = open_page()
    ledger, evidence = backend_modules(intact=False, broken_id=17)
    evidence.build_report = lambda: "# Report\n\n**Report ID:** `backend-001`\n\nFAIL\n"
    with patch.dict("sys.modules", {"loopledger.ledger": ledger, "loopledger.evidence": evidence}):
        verify(app)
        generate(app)
    bundle = app.session_state["cp_export"]
    data = json.loads(bundle["json_text"])
    assert data["integrity"] == {"chain_intact": False, "first_broken_event_id": 17}
    assert "FAIL" in bundle["markdown"]
    assert download_disabled(app) == [False, False]


def test_generation_failure_removes_old_preview_and_disables_both_downloads():
    app = open_page()
    verify(app)
    generate(app)
    old_markdown = app.session_state["cp_export"]["markdown"]
    with patch("loopledger.evidence.build_report", side_effect=RuntimeError("Report failed")):
        generate(app)
    assert app.error
    assert not app.session_state.get("cp_export")
    assert download_disabled(app) == [True, True]
    assert not any(item.value == old_markdown for item in app.markdown)
    generate(app)
    assert not app.error
    assert download_disabled(app) == [False, False]


def test_reverification_failure_invalidates_previous_exports():
    app = open_page()
    verify(app)
    generate(app)
    verify(app)
    assert not app.session_state.get("cp_export")
    assert download_disabled(app) == [True, True]
    generate(app)
    ledger, _ = backend_modules()
    def fail():
        raise RuntimeError("Database unavailable")
    ledger.verify_chain = fail
    with patch.dict("sys.modules", {"loopledger.ledger": ledger}):
        verify(app)
    assert app.session_state["cp_chain"]["status"] == "error"
    assert download_disabled(app) == [True, True]
    assert button(app, "Generate report").disabled


def test_missing_backend_verification_is_a_visible_error_not_a_demo_pass():
    app = open_page()
    with patch.dict("sys.modules", {"loopledger.ledger": types.ModuleType("loopledger.ledger")}):
        verify(app)
    assert app.error
    assert app.session_state["cp_chain"]["status"] == "error"
    assert download_disabled(app) == [True, True]


def test_backend_exports_use_d_interfaces_and_do_not_regenerate_on_rerun():
    app = open_page()
    ledger, evidence = backend_modules()
    with patch.dict("sys.modules", {"loopledger.ledger": ledger, "loopledger.evidence": evidence}):
        verify(app)
        generate(app)
    assert app.session_state["cp_export"]["markdown"].startswith("# Backend evidence")
    assert json.loads(app.session_state["cp_export"]["json_text"])["report_id"] == "backend-001"
    assert download_disabled(app) == [False, False]
    # An ordinary rerun keeps prepared artifacts without regenerating them.
    app.run()
    assert not app.exception
    assert not app.error
    assert download_disabled(app) == [False, False]


@pytest.mark.parametrize("bad_result", [("True", None), (True, 17), (False, None), (False, -1)])
def test_malformed_backend_check_results_are_execution_errors(bad_result):
    app = open_page()
    ledger, _ = backend_modules()
    ledger.verify_chain = lambda: bad_result
    with patch.dict("sys.modules", {"loopledger.ledger": ledger}):
        verify(app)
    assert app.session_state["cp_chain"]["status"] == "error"
    assert app.error
    assert download_disabled(app) == [True, True]


@pytest.mark.parametrize("failure", ["empty_markdown", "invalid_json", "report_id_changed", "integrity_changed"])
def test_invalid_or_mismatched_backend_exports_never_enable_partial_downloads(failure):
    app = open_page()
    ledger, evidence = backend_modules()
    if failure == "empty_markdown":
        evidence.build_report = lambda: "   "
    elif failure == "invalid_json":
        evidence.build_report_json = lambda: {"value": float("nan")}
    elif failure == "report_id_changed":
        evidence.build_report = lambda: "# Report\n\n**Report ID:** `different-id`\n"
    else:
        evidence.build_report_json = lambda: {
            "report_id": "backend-001", "integrity": {"chain_intact": False, "first_broken_event_id": 17}
        }
    with patch.dict("sys.modules", {"loopledger.ledger": ledger, "loopledger.evidence": evidence}):
        verify(app)
        generate(app)
    assert app.error
    assert not app.session_state.get("cp_export")
    assert download_disabled(app) == [True, True]
    if failure == "integrity_changed":
        assert app.session_state["cp_chain"]["status"] == "unchecked"
        assert not any("Check passed" in item.value for item in app.success)
        assert button(app, "Generate report").disabled


def test_compliance_ui_does_not_modify_real_database():
    path = ROOT / "loopledger.db"
    before = hashlib.sha256(path.read_bytes()).digest()
    app = open_page()
    verify(app)
    generate(app)
    assert hashlib.sha256(path.read_bytes()).digest() == before
