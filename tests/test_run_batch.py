"""Batch page behavior and integration with the real A-owned model/gate."""

import hashlib
from pathlib import Path
import runpy
from unittest.mock import patch

import pytest
from loopledger import ledger, metrics as backend_metrics
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "1_Run_Batch.py"


def page_functions():
    functions = runpy.run_path(str(PAGE), run_name="batch_test")
    assert callable(functions.get("run_mock_batch")), "The batch runner is not implemented."
    assert callable(functions.get("run_model_batch")), "The model preview is not implemented."
    return functions


def open_page():
    app = AppTest.from_file(str(PAGE), default_timeout=30)
    app.run()
    assert not app.exception
    assert not app.radio
    assert app.slider, "The page must let the user select a batch size."
    return app


def start_batch(app, n):
    app.slider(key="rb_batch_size").set_value(n)
    next(item for item in app.button if item.label == "Run batch").click().run()
    assert not app.exception


def test_page_does_no_work_before_run_is_clicked():
    app = open_page()
    assert not app.dataframe
    assert "rq_pending_reviews" not in app.session_state
    app.slider(key="rb_batch_size").set_value(8).run()
    assert not app.exception
    assert not app.dataframe
    assert "rq_pending_reviews" not in app.session_state


def test_saved_batch_counts_routes_and_preserves_results_on_rerun():
    app = open_page()
    start_batch(app, 8)
    metrics = {item.label: item.value for item in app.metric}
    assert metrics == {
        "Processed": "8", "Auto-approve": "0", "Auto-reject": "0",
        "Needs review": "8", "Failed": "0",
    }
    assert len(app.dataframe[0].value) == 8
    pending = ledger.get_pending_reviews()
    assert len(pending) == 8
    assert all(not case.is_gold for case in pending)
    ids = [case.case_id for case in pending]
    app.run()
    assert not app.exception
    assert [case.case_id for case in ledger.get_pending_reviews()] == ids
    assert len(app.dataframe[0].value) == 8


def test_new_batch_preserves_existing_reviews_and_never_reuses_ids():
    from loopledger.schemas import ReviewAction

    app = open_page()
    start_batch(app, 8)
    pending = ledger.get_pending_reviews()
    reviewed_id = pending[0].case_id
    old_ids = {case.case_id for case in pending}
    ledger.submit_review(ReviewAction(reviewed_id, "alice", "reject", "Checked documents.", 20.0))
    start_batch(app, 4)
    final_ids = {case.case_id for case in ledger.get_pending_reviews()}
    assert len(final_ids) == 11
    assert reviewed_id not in final_ids
    assert len(final_ids - old_ids) == 4
    assert backend_metrics.system_stats()["reviewed"] == 1


def test_saved_batches_are_readable_by_an_independent_review_session():
    app = open_page()
    start_batch(app, 4)
    review_page = AppTest.from_file(str(ROOT / "pages/2_Review_Queue.py"))
    review_page.run()
    assert not review_page.exception
    assert len(review_page.selectbox[0].options) == 4
    assert {p.case_id for p in ledger.get_pending_reviews()} == {row["Case"] for row in app.dataframe[0].value.to_dict("records")}


@pytest.fixture(scope="module")
def trained_model(tmp_path_factory):
    from loopledger import model

    path = tmp_path_factory.mktemp("batch-model") / "credit_model.joblib"
    model.train(model_path=path)
    return path


def test_model_preview_uses_real_predictions_and_requires_explicit_identity_assumption(trained_model):
    functions = page_functions()
    result = functions["run_model_batch"](4, "TEST-REAL", model_path=trained_model)
    assert len(result["rows"]) == 4
    assert all(row["Routing"] == "Manual review" for row in result["rows"])
    assert all("Identity verification missing" in row["Reasons"] for row in result["rows"])
    assert len(result["pending_reviews"]) == 4
    assert all(0.5 <= pred.confidence <= 1 for pred in result["pending_reviews"])
    assert all(len(pred.features) >= 20 for pred in result["pending_reviews"])
    assert all(len(pred.top_factors) == 5 for pred in result["pending_reviews"])


def test_model_preview_verified_identity_preserves_case_ids_and_uses_typed_gate(trained_model):
    functions = page_functions()
    result = functions["run_model_batch"](
        4, "VERIFIED", model_path=trained_model, identity_verified=True,
    )
    assert all(row["Routing"] != "Failed" for row in result["rows"])
    assert all("Identity verification missing" not in row["Reasons"] for row in result["rows"])
    assert all("Case ID mismatch" not in row["Reasons"] for row in result["rows"])
    assert [row["Case"] for row in result["rows"]] == [
        "VERIFIED-0001", "VERIFIED-0002", "VERIFIED-0003", "VERIFIED-0004",
    ]
    assert [pred.case_id for pred, _ in result["decisions"]] == [row["Case"] for row in result["rows"]]
    assert all(pred.features["identity_verified"] is True for pred in result["pending_reviews"])


def test_model_preview_failure_is_a_failed_row_not_an_automatic_decision(trained_model):
    from loopledger import model

    functions = page_functions()
    actual_predict = model.predict
    calls = 0

    def fail_second_prediction(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("Invalid test application")
        return actual_predict(*args, **kwargs)

    with patch.object(model, "predict", side_effect=fail_second_prediction):
        result = functions["run_model_batch"](4, "TEST-PARTIAL", model_path=trained_model)
    rows = result["rows"]
    assert len(rows) == 4
    assert rows[1]["Routing"] == "Failed"
    assert rows[1]["AI decision"] == "—"
    assert rows[1]["Confidence"] == "—"
    assert "Invalid test application" in rows[1]["Error"]
    assert len(result["pending_reviews"]) == 3


def test_invalid_gate_reason_cannot_leave_a_failed_case_in_pending_results(trained_model):
    from loopledger import gate
    from loopledger.schemas import GateResult

    functions = page_functions()
    with patch.object(
        gate, "evaluate_risk",
        return_value=GateResult(needs_review=True, reasons=[None]),
    ):
        result = functions["run_model_batch"](1, "BAD-GATE", model_path=trained_model)
    assert result["rows"][0]["Routing"] == "Failed"
    assert "Risk gate returned an invalid routing result" in result["rows"][0]["Error"]
    assert result["pending_reviews"] == []


def test_missing_model_does_not_fall_back_to_mock_or_replace_previous_results(tmp_path):
    from loopledger import model

    app = open_page()
    start_batch(app, 4)
    previous_id = app.session_state["rb_last_batch"]["batch_id"]
    queue_ids = [case.case_id for case in ledger.get_pending_reviews()]
    with patch.object(model, "MODEL_FILE", tmp_path / "missing.joblib"):
        start_batch(app, 4)
    assert app.error
    assert app.session_state["rb_last_batch"]["batch_id"] == previous_id
    assert [case.case_id for case in ledger.get_pending_reviews()] == queue_ids


def test_prediction_helper_remains_a_pure_preview_without_database_writes(trained_model):
    result = page_functions()["run_model_batch"](4, "PREVIEW", model_path=trained_model)
    assert len(result["rows"]) == 4
    assert not ledger.get_all_events()
    assert not ledger.get_pending_reviews()


@pytest.mark.parametrize("n", [0, -1, True, 201])
def test_invalid_batch_size_is_rejected_before_processing(n):
    functions = page_functions()
    with pytest.raises(ValueError):
        functions["run_mock_batch"](n, "INVALID")


def test_model_preview_rejects_counts_larger_than_the_holdout(trained_model):
    functions = page_functions()
    # The real data has 250 held-out rows. Force a smaller dataset to exercise
    # A's sampler bound rather than merely checking the page's 200-row limit.
    from loopledger import model

    features, labels = model.load_data()
    with patch.object(model, "load_data", return_value=(features.iloc[:40], labels.iloc[:40])):
        with pytest.raises(ValueError, match="10"):
            functions["run_model_batch"](11, "TOO-MANY", model_path=trained_model)


def test_page_tests_do_not_modify_the_working_database():
    path = ROOT / "loopledger.db"
    before = hashlib.sha256(path.read_bytes()).digest()
    app = open_page()
    start_batch(app, 4)
    assert hashlib.sha256(path.read_bytes()).digest() == before
