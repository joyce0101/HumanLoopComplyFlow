"""Exercise the review workflow through Streamlit's real AppTest runtime."""

from pathlib import Path
import time
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest


PAGE = Path(__file__).resolve().parents[1] / "pages" / "2_Review_Queue.py"


def open_page():
    app = AppTest.from_file(str(PAGE), default_timeout=20).run()
    assert not app.exception
    assert app.selectbox, "The page must expose a pending-case selector."
    return app


def button(app, label):
    return next(item for item in app.button if item.label == label)


def fill_review(app, reviewer="alice", reason="Verified the application documents."):
    app.text_input(key="rq_reviewer").input(reviewer)
    app.text_area[0].input(reason)


def test_case_selection_shows_public_details_and_never_gold_metadata():
    app = open_page()
    assert app.selectbox[0].options == ["C-001", "C-002", "C-003", "C-004", "C-005"]
    assert any("Mock" in item.value for item in app.warning)
    app.selectbox[0].select("C-005").run()
    assert not app.exception
    assert app.session_state["rq_active_case_id"] == "C-005"
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
    assert button(app, "Modify terms").disabled


@pytest.mark.parametrize("reviewer,reason", [("   ", "Checked."), ("alice", " \n ")])
def test_blank_inputs_keep_case_and_draft_for_correction(reviewer, reason):
    app = open_page()
    started_at = app.session_state["rq_started_at"]
    fill_review(app, reviewer=reviewer, reason=reason)
    button(app, "Approve application").click().run()
    assert not app.exception
    assert app.error
    assert len(app.session_state["rq_pending_reviews"]) == 5
    assert app.session_state["rq_submitted_reviews"] == []
    assert app.text_area[0].value == reason
    assert app.session_state["rq_started_at"] == started_at


@pytest.mark.parametrize(
    "label,action", [("Approve application", "approve"), ("Reject application", "reject")]
)
def test_submission_emits_action_and_advances_exactly_once(label, action, capsys):
    app = open_page()
    app.session_state["rq_started_at"] = time.perf_counter() - 20
    fill_review(app, reviewer=" alice ", reason=" Documents checked. ")
    button(app, label).click().run()
    assert not app.exception
    submitted = app.session_state["rq_submitted_reviews"]
    assert len(submitted) == 1
    saved = submitted[0]
    assert saved.case_id == "C-001"
    assert saved.reviewer == "alice"
    assert saved.action == action
    assert saved.reason == "Documents checked."
    assert saved.seconds_spent >= 20
    assert [pred.case_id for pred in app.session_state["rq_pending_reviews"]] == [
        "C-002", "C-003", "C-004", "C-005"
    ]
    assert app.success
    assert app.text_area[0].value == ""
    assert "C-001" in capsys.readouterr().out
    app.run()
    assert not app.exception
    assert len(app.session_state["rq_submitted_reviews"]) == 1
    assert len(app.session_state["rq_pending_reviews"]) == 4


def test_timer_survives_rerun_but_restarts_for_a_different_case():
    app = open_page()
    started_at = time.perf_counter() - 30
    app.session_state["rq_started_at"] = started_at
    app.run()
    assert app.session_state["rq_started_at"] == started_at
    app.selectbox[0].select("C-002").run()
    assert not app.exception
    assert app.session_state["rq_started_at"] > started_at
    assert app.session_state["rq_active_case_id"] == "C-002"


def test_submission_failure_keeps_queue_reason_and_timer():
    app = open_page()
    started_at = app.session_state["rq_started_at"]
    fill_review(app)
    # The mock sink prints before any session-state transition. Reproduce an
    # unavailable output sink while exercising the real page failure handling.
    with patch("builtins.print", side_effect=OSError("Output unavailable")):
        button(app, "Approve application").click().run()
    assert not app.exception
    assert app.error
    assert len(app.session_state["rq_pending_reviews"]) == 5
    assert app.session_state["rq_submitted_reviews"] == []
    assert app.text_area[0].value == "Verified the application documents."
    assert app.session_state["rq_started_at"] == started_at


def test_completing_all_cases_reaches_an_empty_queue_without_reseeding():
    app = open_page()
    for index in range(5):
        fill_review(app, reason=f"Reviewed application {index + 1}.")
        button(app, "Reject application").click().run()
        assert not app.exception
    assert app.session_state["rq_pending_reviews"] == []
    assert len(app.session_state["rq_submitted_reviews"]) == 5
    assert not app.selectbox
    assert any("No pending" in item.value for item in app.info)
    app.run()
    assert not app.exception
    assert app.session_state["rq_pending_reviews"] == []
