"""Exercise the review workflow through Streamlit's real AppTest runtime."""

from dataclasses import asdict
from pathlib import Path
import runpy
import time
from unittest.mock import patch

import pytest
from loopledger import ledger
from loopledger.schemas import Prediction
from streamlit.testing.v1 import AppTest


PAGE = Path(__file__).resolve().parents[1] / "pages" / "2_Review_Queue.py"


def open_page():
    app = AppTest.from_file(str(PAGE), default_timeout=20)
    fixtures = runpy.run_path(str(PAGE), run_name="review_fixtures")["make_mock_pending_reviews"]()
    for pred in fixtures:
        ledger.log_event("prediction", asdict(pred))
    app.run()
    assert not app.exception
    assert not app.radio
    assert app.selectbox, "The page must expose a pending-case selector."
    return app


def button(app, label):
    return next(item for item in app.button if item.label == label)


def fill_review(app, reviewer="alice", reason="Verified the application documents."):
    app.text_input(key="rq_reviewer").input(reviewer)
    app.text_area[0].input(reason)


def application_text(app):
    return " ".join(str(item.value) for kind in ("markdown", "text", "caption", "metric")
                    for item in app.get(kind))


def test_application_details_decode_credit_finances_and_employment_without_writes():
    pred = Prediction("DETAILS", {
        "credit_amount": 3000, "duration": 24, "age": 35,
        "purpose": "A41", "credit_history": "A33", "checking_status": "A11",
        "savings_status": "A65", "employment": "A74", "existing_credits": 2,
        "installment_commitment": 4, "other_parties": "A103", "housing": "A151",
        "property_magnitude": "A124", "other_payment_plans": "A141", "num_dependents": 0,
        "identity_verified": False, "gold_correct_decision": "PRIVATE-ANSWER",
    }, "approve", .6, [])
    ledger.log_event("prediction", asdict(pred))
    before = ledger.get_all_events()
    app = AppTest.from_file(str(PAGE)).run()
    assert not app.exception
    rendered = application_text(app)
    for label in ("Loan purpose", "Credit history", "Checking account", "Savings / bonds",
                  "Employment tenure", "Existing credits at this bank",
                  "Other debtors / guarantors", "Housing", "Property", "Other installment plans",
                  "People financially supported"):
        assert label in rendered
    for value in ("Used car", "Prior repayment delays", "Balance below 0 DM",
                  "Unknown / no savings account", "4 to less than 7 years", "Guarantor",
                  "Rented housing", "Unknown / no property", "Bank installment plan"):
        assert value in rendered
    assert "Installment burden" not in rendered
    assert "Code 4" not in rendered
    assert "4%" not in rendered
    assert "PRIVATE-ANSWER" not in rendered
    assert "gold_correct_decision" not in rendered
    assert ledger.get_all_events() == before
    assert ledger.get_pending_reviews() == [pred]


def test_application_details_keep_missing_unknown_and_zero_values_distinct():
    pred = Prediction("SPARSE-DETAILS", {"purpose": "A999", "checking_status": "",
                                       "existing_credits": 0}, "reject", .6, [])
    ledger.log_event("prediction", asdict(pred))
    app = AppTest.from_file(str(PAGE)).run()
    assert not app.exception
    rendered = application_text(app)
    assert "Unknown category: A999" in rendered
    assert "Not provided" in rendered
    assert any(item.value == "0" for item in app.text)
    assert "Unknown / no savings account" not in rendered
    assert "No checking account" not in rendered


def test_case_selection_shows_public_details_and_never_gold_metadata():
    app = open_page()
    assert len(app.selectbox[0].options) == 5
    selected = app.selectbox[0].options[-1]
    app.selectbox[0].select(selected).run()
    assert not app.exception
    assert app.session_state["rq_active_case_id"] == selected.removeprefix("🟨 GOLD · ")
    assert any(item.value == "94%" for item in app.metric)
    rendered = " ".join(
        str(item.value)
        for kind in ("markdown", "caption", "text", "json", "info", "warning", "metric")
        for item in app.get(kind)
    )
    assert "9,000" in rendered
    assert "is_gold" not in rendered
    assert "gold_correct_decision" not in rendered
    assert not app.json, "Do not dump internal Prediction objects to the review UI."
    assert len(app.get("plotly_chart")) == 1
    assert {item.label for item in app.button} == {
        "Refresh queue", "Approve application", "Reject application"
    }


@pytest.mark.parametrize("reviewer,reason", [("   ", "Checked."), ("alice", " \n ")])
def test_blank_inputs_keep_case_and_draft_for_correction(reviewer, reason):
    app = open_page()
    started_at = app.session_state["rq_started_at"]
    fill_review(app, reviewer=reviewer, reason=reason)
    button(app, "Approve application").click().run()
    assert not app.exception
    assert app.error
    assert len(ledger.get_pending_reviews()) == 5
    assert not [e for e in ledger.get_all_events() if e["event_type"] == "review"]
    assert app.text_area[0].value == reason
    assert app.session_state["rq_started_at"] == started_at


@pytest.mark.parametrize(
    "label,action", [("Approve application", "approve"), ("Reject application", "reject")]
)
def test_submission_emits_action_and_advances_exactly_once(label, action):
    app = open_page()
    app.session_state["rq_started_at"] = time.perf_counter() - 20
    fill_review(app, reviewer=" alice ", reason=" Documents checked. ")
    button(app, label).click().run()
    assert not app.exception
    submitted = [e["payload"] for e in ledger.get_all_events() if e["event_type"] == "review"]
    assert len(submitted) == 1
    saved = submitted[0]
    assert saved["case_id"] == "C-001"
    assert saved["reviewer"] == "alice"
    assert saved["action"] == action
    assert saved["reason"] == "Documents checked."
    assert saved["seconds_spent"] >= 20
    assert [pred.case_id for pred in ledger.get_pending_reviews()] == [
        "C-002", "C-003", "C-004", "C-005"
    ]
    assert app.success
    assert app.text_area[0].value == ""
    app.run()
    assert not app.exception
    assert len([e for e in ledger.get_all_events() if e["event_type"] == "review"]) == 1
    assert len(ledger.get_pending_reviews()) == 4


def test_timer_survives_rerun_but_restarts_for_a_different_case():
    app = open_page()
    started_at = time.perf_counter() - 30
    app.session_state["rq_started_at"] = started_at
    app.run()
    assert app.session_state["rq_started_at"] == started_at
    selected = app.selectbox[0].options[1]
    app.selectbox[0].select(selected).run()
    assert not app.exception
    assert app.session_state["rq_started_at"] > started_at
    assert app.session_state["rq_active_case_id"] == selected


def test_submission_failure_keeps_queue_reason_and_timer():
    app = open_page()
    started_at = app.session_state["rq_started_at"]
    fill_review(app)
    with patch.object(ledger, "submit_review", side_effect=RuntimeError("Database unavailable")):
        button(app, "Approve application").click().run()
    assert not app.exception
    assert app.error
    assert len(ledger.get_pending_reviews()) == 5
    assert not [e for e in ledger.get_all_events() if e["event_type"] == "review"]
    assert app.text_area[0].value == "Verified the application documents."
    assert app.session_state["rq_started_at"] == started_at


def test_completing_all_cases_reaches_an_empty_queue_without_reseeding():
    app = open_page()
    for index in range(5):
        fill_review(app, reason=f"Reviewed application {index + 1}.")
        button(app, "Reject application").click().run()
        assert not app.exception
    assert ledger.get_pending_reviews() == []
    assert len([e for e in ledger.get_all_events() if e["event_type"] == "review"]) == 5
    assert not app.selectbox
    assert any("No pending" in item.value for item in app.info)
    app.run()
    assert not app.exception
    assert ledger.get_pending_reviews() == []
