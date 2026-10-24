"""Exercise the default pages against real A/B/D interfaces in an isolated DB."""

from dataclasses import asdict
import json
from pathlib import Path
import runpy
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from loopledger import ledger, metrics
from loopledger.gold import get_gold_cases
from loopledger.schemas import GateResult, Prediction


ROOT = Path(__file__).resolve().parents[1]


def page(name):
    app = AppTest.from_file(str(ROOT / "pages" / name), default_timeout=30).run()
    assert not app.exception
    return app


def click(app, label):
    next(b for b in app.button if b.label == label).click().run()
    assert not app.exception


@pytest.mark.parametrize("filename,legacy_key,legacy_value", [
    ("1_Run_Batch.py", "rb_data_source", "Mock demo"),
    ("2_Review_Queue.py", "rq_data_source", "Session demo"),
    ("3_Oversight_Dashboard.py", "od_data_source", "Session demo"),
    ("4_Compliance.py", "cp_data_source", "UI demo"),
])
def test_pages_have_no_source_selector_and_ignore_legacy_modes(filename, legacy_key, legacy_value):
    app = AppTest.from_file(str(ROOT / "pages" / filename), default_timeout=30)
    app.session_state[legacy_key] = legacy_value
    app.session_state["rq_pending_reviews"] = [Prediction("OLD-MOCK", {}, "approve", .9, [])]
    app.session_state["rb_last_batch"] = {"mode": "Mock demo", "rows": []}
    app.session_state["cp_context"] = ("UI demo", "Pass")
    app.session_state["cp_export"] = {"source": "UI demo"}
    app.run()
    assert not app.exception
    assert not app.radio
    assert all("Mock data mode" not in item.value and "Session demo /" not in item.value for item in app.warning)
    if filename == "1_Run_Batch.py":
        assert not app.dataframe
        app.slider(key="rb_batch_size").set_value(1)
        click(app, "Run batch")
        assert len(ledger.get_all_events()) == 2
    elif filename == "2_Review_Queue.py":
        assert not app.selectbox
        assert app.metric[0].value == "0"
    elif filename == "3_Oversight_Dashboard.py":
        assert next(m.value for m in app.metric if m.label == "Total applications") == "0"
    else:
        assert not app.selectbox
        assert not app.checkbox
        assert not app.session_state["cp_export"]
        assert all(b.proto.disabled for b in app.get("download_button"))


def test_default_real_batch_persists_and_new_session_can_review():
    app = page("1_Run_Batch.py")
    assert not app.radio
    assert ledger.get_all_events() == []
    app.slider(key="rb_batch_size").set_value(3)
    click(app, "Run batch")
    assert not app.error
    assert len(ledger.get_all_events()) == 6
    assert len(ledger.get_pending_reviews()) == 3
    assert "rq_pending_reviews" not in app.session_state
    app.run()
    assert len(ledger.get_all_events()) == 6
    review = page("2_Review_Queue.py")
    assert not review.radio
    assert len(review.selectbox[0].options) == 3
    review.text_input(key="rq_reviewer").input("alice")
    review.text_area[0].input("Checked the documents and identity evidence.")
    click(review, "Reject application")
    events = ledger.get_all_events()
    assert len(events) == 7
    assert events[-1]["payload"]["action"] == "reject"
    assert len(ledger.get_pending_reviews()) == 2
    review.run()
    assert len(ledger.get_all_events()) == 7
    assert ledger.verify_chain() == (True, None)
    dashboard = page("3_Oversight_Dashboard.py")
    assert not dashboard.radio
    assert next(m.value for m in dashboard.metric if m.label == "Reviewed") == "1"
    assert dashboard.dataframe[0].value.iloc[0]["Reviewer"] == "alice"
    compliance = page("4_Compliance.py")
    assert not compliance.radio
    click(compliance, "Verify chain")
    click(compliance, "Generate report")
    assert not compliance.error
    bundle = compliance.session_state["cp_export"]
    data = json.loads(bundle["json_text"])
    assert data["system_stats"] == metrics.system_stats()
    assert data["total_events"] == 7
    assert data["reviewer_metrics"][0]["reviewer"] == "alice"
    assert "MOCK A/B/C" not in data["data_origin"]
    assert all(not b.proto.disabled for b in compliance.get("download_button"))


@pytest.mark.parametrize("label,action", [
    ("Approve application", "approve"), ("Reject application", "reject"),
])
def test_database_review_sparse_controls_show_gold_marker_hide_answers_and_preserve_failed_draft(label, action):
    pred = get_gold_cases(1, include_answers=True)[0]
    ledger.log_event("prediction", asdict(pred))
    app = page("2_Review_Queue.py")
    assert not app.error
    assert any(m.value == "Not provided" for m in app.metric)
    assert not app.get("plotly_chart")
    rendered = str(app.selectbox[0].options) + " ".join(
        str(item.value) for kind in ("caption", "markdown", "info", "warning", "text")
        for item in app.get(kind)
    )
    assert app.selectbox[0].options[0].startswith("🟨 GOLD · ")
    assert "is_gold" not in rendered
    assert "gold_correct_decision" not in rendered
    app.text_input(key="rq_reviewer").input("reviewer")
    app.text_area[0].input("Identity evidence checked carefully.")
    with patch.object(ledger, "submit_review", side_effect=RuntimeError("DB unavailable")):
        click(app, label)
    assert app.error
    assert app.text_area[0].value == "Identity evidence checked carefully."
    assert len(ledger.get_pending_reviews()) == 1
    click(app, label)
    assert ledger.get_all_events()[-1]["payload"]["action"] == action
    assert not ledger.get_pending_reviews()


def test_partial_gate_write_is_pending_and_never_reported_as_automatic():
    f = runpy.run_path(str(ROOT / "pages/1_Run_Batch.py"), run_name="integration_test")
    pred = Prediction("PARTIAL", {"credit_amount": 2000}, "approve", .95, [])
    batch = f["_new_batch"](1, "PARTIAL-BATCH", "Model preview")
    f["_record_prediction"](batch, pred, GateResult(False, []))
    real_log = ledger.log_event

    def fail_gate(kind, payload):
        if kind == "gate":
            raise RuntimeError("Gate save failed")
        return real_log(kind, payload)

    with patch.object(ledger, "log_event", side_effect=fail_gate):
        result = f["persist_model_batch"](batch)
    assert result["rows"][0]["Routing"] == "Manual review"
    assert "Gate save failed" in result["rows"][0]["Error"]
    assert len(ledger.get_pending_reviews()) == 1
    assert len(ledger.get_all_events()) == 1


def test_database_queue_error_never_seeds_session_fixtures():
    with patch.object(ledger, "get_pending_reviews", side_effect=RuntimeError("read failed")):
        app = page("2_Review_Queue.py")
    assert app.error
    assert not app.selectbox
    assert "rq_pending_reviews" not in app.session_state
    assert ledger.get_all_events() == []


def test_verified_model_batch_saves_automatic_and_manual_routes():
    f = runpy.run_path(str(ROOT / "pages/1_Run_Batch.py"), run_name="integration_test")
    result = f["persist_model_batch"](f["run_model_batch"](12, "VERIFIED-DB", identity_verified=True))
    counts = metrics.system_stats()
    routes = [row["Routing"] for row in result["rows"]]
    assert counts["auto_approved"] == routes.count("Auto approve") > 0
    assert counts["auto_rejected"] == routes.count("Auto reject") > 0
    assert counts["pending"] == routes.count("Manual review") > 0
    assert counts["total"] == 12
    assert len(ledger.get_all_events()) == 24
    assert ledger.verify_chain() == (True, None)


def test_prediction_save_failure_does_not_enqueue_or_append_gate():
    f = runpy.run_path(str(ROOT / "pages/1_Run_Batch.py"), run_name="integration_test")
    pred = Prediction("UNSAVED", {"credit_amount": 2000}, "approve", .95, [])
    batch = f["_new_batch"](1, "FAILED-BATCH", "Model preview")
    f["_record_prediction"](batch, pred, GateResult(False, []))
    with patch.object(ledger, "log_event", side_effect=RuntimeError("Write failed")) as log:
        result = f["persist_model_batch"](batch)
    assert log.call_count == 1
    assert result["rows"][0]["Routing"] == "Failed"
    assert not result["pending_reviews"]
    assert not ledger.get_all_events()
