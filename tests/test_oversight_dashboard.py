"""Oversight indicators use observable reviews and known original predictions."""

import hashlib
import json
from pathlib import Path
import runpy
import types
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from loopledger.schemas import Prediction, ReviewAction


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages/3_Oversight_Dashboard.py"


def functions():
    module = runpy.run_path(str(PAGE), run_name="dashboard_test")
    assert callable(module.get("build_session_snapshot")), "Session dashboard is not implemented."
    assert callable(module.get("load_backend_snapshot")), "Backend adapter is not implemented."
    return module


def prediction(case_id, *, gold=False, decision="approve", correct=None):
    return Prediction(case_id, {"credit_amount": 3000, "duration": 24, "age": 35},
                      decision, 0.8, [("age", -0.1)], gold, correct)


def reviewer_fixture():
    predictions = {}
    reviews = []
    for index, seconds in enumerate((40, 50, 60, 30, 45)):
        case_id = f"A-{index}"
        predictions[case_id] = prediction(case_id, gold=index == 0, correct="reject" if index == 0 else None)
        reviews.append(ReviewAction(case_id, "alice", "reject" if index < 2 else "approve",
                                    "Checked all supporting documents.", seconds))
    for index in range(5):
        case_id = f"B-{index}"
        predictions[case_id] = prediction(case_id, gold=index < 3, correct="reject" if index < 3 else None)
        reviews.append(ReviewAction(case_id, "bob", "approve", "ok", 2.0))
    return {"rq_reviewed_predictions": predictions, "rq_submitted_reviews": reviews,
            "rq_pending_reviews": []}


def open_dashboard(state=None):
    app = AppTest.from_file(str(PAGE), default_timeout=30)
    for key, value in (state or {}).items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    assert app.radio, "The dashboard must distinguish session and backend data."
    return app


def test_metrics_match_hand_calculated_reviews_and_distinguish_demo_flags():
    snapshot = functions()["build_session_snapshot"](reviewer_fixture())
    frame = snapshot["reviewer_stats"].set_index("reviewer")
    alice, bob = frame.loc["alice"], frame.loc["bob"]
    assert alice["n_reviews"] == 5
    assert alice["avg_seconds"] == 45.0
    assert alice["override_rate"] == 0.4
    assert alice["gold_catch_rate"] == 1.0
    assert alice["short_reason_rate"] == 0.0
    assert alice["flag"] == "no_alert"
    assert bob["avg_seconds"] == 2.0
    assert bob["override_rate"] == 0.0
    assert bob["gold_catch_rate"] == 0.0
    assert bob["short_reason_rate"] == 1.0
    assert bob["flag"] == "review_signals"
    assert len(snapshot["durations"]) == 10


def test_unknown_prediction_is_not_counted_as_agreement_or_failed_gold_check():
    state = {"rq_submitted_reviews": [ReviewAction("OLD", "alice", "approve", "Documents checked.", 20)]}
    snapshot = functions()["build_session_snapshot"](state)
    reviewer = snapshot["reviewer_stats"].iloc[0]
    assert reviewer["n_reviews"] == 1
    assert pd.isna(reviewer["override_rate"])
    assert pd.isna(reviewer["gold_catch_rate"])
    assert reviewer["flag"] == "insufficient_data"
    assert snapshot["warnings"]


def test_correct_ai_control_is_not_an_inverted_gold_probe():
    pred = prediction("G", gold=True, decision="approve", correct="approve")
    state = {"rq_reviewed_predictions": {"G": pred},
             "rq_submitted_reviews": [ReviewAction("G", "alice", "approve", "Documents checked.", 20)]}
    reviewer = functions()["build_session_snapshot"](state)["reviewer_stats"].iloc[0]
    assert reviewer["override_rate"] == 0.0
    assert pd.isna(reviewer["gold_catch_rate"])


def test_invalid_durations_are_missing_not_zero_in_means_or_charts():
    state = {"rq_submitted_reviews": [
        ReviewAction(f"BAD-{index}", "alice", "approve", "Documents checked.", seconds)
        for index, seconds in enumerate((float("nan"), float("inf"), -1))
    ]}
    snapshot = functions()["build_session_snapshot"](state)
    reviewer = snapshot["reviewer_stats"].iloc[0]
    assert reviewer["n_reviews"] == 3
    assert pd.isna(reviewer["avg_seconds"])
    assert snapshot["durations"].empty
    assert snapshot["warnings"]


def test_known_case_totals_use_all_unique_mock_batches_and_exclude_model_previews():
    batch = runpy.run_path(str(ROOT / "pages/1_Run_Batch.py"), run_name="batch_fixture")
    first = batch["run_mock_batch"](4, "FIRST")
    second = batch["run_mock_batch"](4, "SECOND")
    reviewed = first["pending_reviews"][0]
    state = {
        "rb_mock_batches": [first, second, first],
        "rb_last_batch": {"mode": "Model preview", "rows": [{"Case": "REAL", "Routing": "Manual review"}]},
        "rq_pending_reviews": first["pending_reviews"][1:] + second["pending_reviews"],
        "rq_submitted_reviews": [ReviewAction(reviewed.case_id, "alice", "approve", "Documents checked.", 25)],
    }
    snapshot = functions()["build_session_snapshot"](state)
    assert snapshot["system_stats"] == {
        "total": 8, "auto_approved": 2, "auto_rejected": 2,
        "sent_to_review": 4, "reviewed": 1, "pending": 3,
    }
    assert snapshot["reviewer_stats"].iloc[0]["override_rate"] == 0.0


def test_dashboard_visit_never_seeds_reviews_or_pretends_empty_rates_are_measured():
    app = open_dashboard()
    assert not app.dataframe
    assert not app.get("plotly_chart")
    assert "rq_pending_reviews" not in app.session_state
    assert "rq_submitted_reviews" not in app.session_state
    assert any("No completed reviews" in item.value for item in app.info)


def test_dashboard_displays_rates_flags_and_real_duration_charts_without_gold_answers():
    app = open_dashboard(reviewer_fixture())
    table = app.dataframe[0].value
    assert len(table) == 2
    assert table.loc[table["Reviewer"] == "alice", "Gold catch rate"].iloc[0] == "100.0%"
    assert table.loc[table["Reviewer"] == "bob", "Gold catch rate"].iloc[0] == "0.0%"
    assert table["Status"].str.contains("🔴").any()
    assert len(app.get("plotly_chart")) == 2
    assert "gold_correct_decision" not in table.columns
    assert not app.json


def test_refresh_reloads_current_session_reviews():
    state = reviewer_fixture()
    state["rq_submitted_reviews"] = state["rq_submitted_reviews"][:5]
    app = open_dashboard(state)
    assert len(app.dataframe[0].value) == 1
    app.session_state["rq_submitted_reviews"] = reviewer_fixture()["rq_submitted_reviews"]
    next(button for button in app.button if button.label == "Refresh metrics").click().run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 2


def test_backend_mode_reports_missing_functions_without_session_fallback():
    app = open_dashboard(reviewer_fixture())
    app.radio(key="od_source").set_value("Backend metrics").run()
    assert not app.exception
    assert app.error
    assert not app.dataframe


@pytest.mark.parametrize("payload_as_json", [False, True])
def test_backend_adapter_uses_review_events_for_duration_distribution(payload_as_json):
    module = functions()
    metrics = types.ModuleType("loopledger.metrics")
    metrics.system_stats = lambda: {"total": 2, "auto_approved": 0, "sent_to_review": 2, "reviewed": 1, "pending": 1}
    metrics.reviewer_stats = lambda: pd.DataFrame([{
        "reviewer": "backend-user", "n_reviews": 1, "avg_seconds": 25.0,
        "override_rate": 1.0, "gold_catch_rate": None, "short_reason_rate": 0.0,
        "flag": "insufficient_data",
    }])
    payload = {"reviewer": "backend-user", "seconds_spent": 25.0}
    ledger = types.ModuleType("loopledger.ledger")
    ledger.get_all_events = lambda: [{"event_type": "review", "payload": json.dumps(payload) if payload_as_json else payload}]
    with patch.dict("sys.modules", {"loopledger.metrics": metrics, "loopledger.ledger": ledger}):
        snapshot = module["load_backend_snapshot"]()
    assert snapshot["system_stats"]["pending"] == 1
    assert snapshot["system_stats"]["auto_rejected"] is None
    assert snapshot["durations"].to_dict("records") == [{"reviewer": "backend-user", "seconds_spent": 25.0}]


def test_successful_review_retains_original_prediction_but_failed_submit_does_not():
    page = ROOT / "pages/2_Review_Queue.py"
    app = AppTest.from_file(str(page)).run()
    original = app.session_state["rq_pending_reviews"][0]
    app.text_input(key="rq_reviewer").input("alice")
    app.text_area[0].input("Documents checked thoroughly.")
    approve = next(button for button in app.button if button.label == "Approve application")
    with patch("builtins.print", side_effect=OSError("Output unavailable")):
        approve.click().run()
    assert not app.exception
    assert "rq_reviewed_predictions" not in app.session_state
    next(button for button in app.button if button.label == "Approve application").click().run()
    assert not app.exception
    assert app.session_state["rq_reviewed_predictions"][original.case_id] == original


def test_mock_batch_history_retains_prior_batches_on_later_runs():
    app = AppTest.from_file(str(ROOT / "pages/1_Run_Batch.py")).run()
    for n in (4, 8):
        app.slider(key="rb_batch_size").set_value(n)
        next(button for button in app.button if button.label == "Run batch").click().run()
        assert not app.exception
    history = app.session_state["rb_mock_batches"]
    assert [batch["requested"] for batch in history] == [4, 8]


def test_dashboard_does_not_write_database():
    database = ROOT / "loopledger.db"
    before = hashlib.sha256(database.read_bytes()).digest()
    open_dashboard(reviewer_fixture())
    assert hashlib.sha256(database.read_bytes()).digest() == before
