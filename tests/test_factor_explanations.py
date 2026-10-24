"""Ten real contributions with field-specific hover text and intact stored evidence."""

from dataclasses import asdict, replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from loopledger import ledger, model
from loopledger.schemas import Prediction


PAGE = Path(__file__).resolve().parents[1] / "pages/2_Review_Queue.py"


def prediction():
    return model.predict(model.sample_cases(1)[0], case_id="EXPLANATION")


def open_prediction(pred):
    ledger.log_event("prediction", asdict(pred))
    before = ledger.get_all_events()
    app = AppTest.from_file(str(PAGE), default_timeout=30).run()
    assert not app.exception
    assert ledger.get_all_events() == before
    return app


def trace(app):
    return json.loads(app.get("plotly_chart")[0].proto.spec)["data"][0]


def test_model_returns_ten_actual_contributions_in_absolute_order():
    pred = prediction()
    assert len(pred.top_factors) == 10
    assert len({name for name, _ in pred.top_factors}) == 10
    magnitudes = [abs(value) for _, value in pred.top_factors]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_ten_factor_chart_has_individual_hover_explanations_and_original_values():
    pred = prediction()
    app = open_prediction(pred)
    data = trace(app)
    assert len(data["y"]) == 10
    assert data["x"] == [value for _, value in pred.top_factors]
    assert len(data["customdata"]) == 10
    assert all(row[0] and len(row[0]) > 50 for row in data["customdata"])
    assert "%{customdata[0]}" in data["hovertemplate"]
    assert "log-odds" in data["hovertemplate"]
    hover = json.dumps(data["customdata"]).replace("<br>", " ")
    assert "cat__" not in str(data["y"])
    assert "num__" not in str(data["y"])
    assert "Recorded application value" in hover
    assert "not a probability" in hover
    assert any(m.value == f"{pred.confidence:.0%}" for m in app.metric)


def test_old_five_factors_are_extended_only_in_display_and_not_written_back():
    current = prediction()
    legacy = replace(current, top_factors=current.top_factors[:5])
    app = open_prediction(legacy)
    before = ledger.get_all_events()
    assert len(trace(app)["y"]) == 10
    assert any("recomputed" in item.value for item in app.caption)
    app.run()
    assert not app.exception
    assert ledger.get_all_events() == before
    assert ledger.get_pending_reviews()[0].top_factors == legacy.top_factors
    assert ledger.verify_chain() == (True, None)


@pytest.mark.parametrize("mismatch", ["confidence", "factor"])
def test_changed_model_output_never_replaces_historical_contributions(mismatch):
    pred = prediction()
    legacy = replace(pred, top_factors=pred.top_factors[:5])
    if mismatch == "confidence":
        legacy.confidence = .501
    else:
        name, value = legacy.top_factors[0]
        legacy.top_factors = [(name, value + .2), *legacy.top_factors[1:]]
    app = open_prediction(legacy)
    assert trace(app)["x"] == [value for _, value in legacy.top_factors]
    assert len(trace(app)["y"]) == 5
    assert any("Stored factors only" in item.value for item in app.caption)
    assert app.text_area


def test_missing_model_keeps_existing_factors_and_review_form_usable():
    pred = prediction()
    legacy = replace(pred, top_factors=pred.top_factors[:5])
    with patch.object(model, "predict", side_effect=FileNotFoundError("Model missing")):
        app = open_prediction(legacy)
    assert len(trace(app)["y"]) == 5
    assert app.text_area
    assert not app.error


def test_encoded_unknown_and_missing_fields_get_honest_tooltips_without_padding():
    pred = Prediction("SPARSE-HOVER", {"purpose": "A41", "savings_status": "A65",
                                      "gold_correct_decision": "PRIVATE-ANSWER"}, "approve", .87, [
        ("cat__purpose_A41", -.7), ("cat__savings_status_A65", -.4),
        ("num__duration", .3), ("cat__checking_status_A999", .2), ("future__signal", 0.0),
    ])
    app = open_prediction(pred)
    data = trace(app)
    hover = json.dumps(data["customdata"])
    assert len(data["y"]) == 5
    assert "Used car" in hover
    assert "Unknown / no savings account" in hover
    assert "Not provided" in hover
    assert "Unknown category: A999" in hover
    assert "No field description available" in hover
    assert "PRIVATE-ANSWER" not in hover
    assert data["marker"]["color"][-1] == "#94a3b8"
