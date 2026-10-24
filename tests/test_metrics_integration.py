"""Real B metrics through unchanged C/D consumers, without backend stubs."""

import json
from pathlib import Path
import runpy

import pytest
from streamlit.testing.v1 import AppTest

from loopledger import evidence, ledger, metrics
from scripts.demo_reset import seed_oversight_demo


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def persisted_demo(tmp_path, monkeypatch):
    database = tmp_path / "integration.db"
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(database))
    ledger.init_db()
    seed_oversight_demo()
    return database


def test_real_backend_dashboard_renders_persisted_rates_and_flags(persisted_demo):
    before = persisted_demo.read_bytes()
    app = AppTest.from_file(str(ROOT / "pages/3_Oversight_Dashboard.py"), default_timeout=30).run()
    app.radio(key="od_source").set_value("Backend metrics").run()
    assert not app.exception
    assert not app.error
    counts = {item.label: item.value for item in app.metric}
    assert counts == {
        "Total applications": "16", "Auto-approved": "1", "Auto-rejected": "1",
        "Sent for review": "14", "Reviewed": "12", "Pending": "2",
    }
    frame = app.dataframe[0].value.set_index("Reviewer")
    assert frame.loc["careful_reviewer", "Gold catch rate"] == "100.0%"
    assert frame.loc["rubber_stamp", "Gold catch rate"] == "0.0%"
    assert "🟢" in frame.loc["careful_reviewer", "Status"]
    assert "🔴" in frame.loc["rubber_stamp", "Status"]
    assert len(app.get("plotly_chart")) == 2
    assert "gold_correct_decision" not in frame.columns
    assert persisted_demo.read_bytes() == before


def test_dashboard_reports_actual_missing_dependency_without_session_fallback(persisted_demo, monkeypatch):
    import sys
    import types

    app = AppTest.from_file(str(ROOT / "pages/3_Oversight_Dashboard.py"), default_timeout=30).run()
    monkeypatch.setitem(sys.modules, "loopledger.metrics", types.ModuleType("loopledger.metrics"))
    app.radio(key="od_source").set_value("Backend metrics").run()
    assert not app.exception
    assert app.error
    assert "not available" in app.error[0].value
    assert not app.dataframe


def test_real_report_and_compliance_bundle_share_current_metrics(persisted_demo):
    before = persisted_demo.read_bytes()
    report = evidence.build_report_json()
    assert report["total_events"] == 44
    assert report["system_stats"] == metrics.system_stats()
    assert report["integrity"]["chain_intact"] is True
    assert {r["reviewer"]: r["gold_catch_rate"] for r in report["reviewer_metrics"]} == {
        "careful_reviewer": 1.0, "rubber_stamp": 0.0,
    }
    json.dumps(report, allow_nan=False)
    markdown = evidence.build_report()
    assert "100.0%" in markdown
    assert "review_signals" in markdown
    assert report["report_id"] in markdown
    functions = runpy.run_path(str(ROOT / "pages/4_Compliance.py"), run_name="metrics_compliance_test")
    bundle = functions["build_export_bundle"](
        "Backend interfaces", {"status": "passed", "intact": True, "broken_id": None},
    )
    assert json.loads(bundle["json_text"])["report_id"] == report["report_id"]
    assert report["report_id"] in bundle["markdown"]
    assert "100.0%" in bundle["markdown"]
    assert "review_signals" in bundle["markdown"]
    assert persisted_demo.read_bytes() == before


def test_real_reports_encode_unmeasured_gold_as_null(tmp_path, monkeypatch):
    from dataclasses import asdict
    from loopledger.schemas import Prediction, ReviewAction

    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(tmp_path / "ordinary.db"))
    ledger.init_db()
    pred = Prediction("ordinary", {}, "approve", 0.6, [])
    ledger.log_event("prediction", asdict(pred))
    ledger.submit_review(ReviewAction("ordinary", "alice", "approve", "Documents checked.", 30.0))
    report = evidence.build_report_json()
    assert report["reviewer_metrics"][0]["gold_catch_rate"] is None
    json.dumps(report, allow_nan=False)
    assert "N/A (no control cases)" in evidence.build_report()


def test_empty_reports_and_tampered_chain_are_not_fabricated_success(tmp_path, monkeypatch):
    import sqlite3

    path = tmp_path / "chain.db"
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(path))
    ledger.init_db()
    assert evidence.build_report_json()["reviewer_metrics"] == []
    assert "No reviews yet" in evidence.build_report()
    seed_oversight_demo()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE events SET ts='altered' WHERE id=10")
    report = evidence.build_report_json()
    assert report["integrity"]["chain_intact"] is False
    assert report["integrity"]["first_broken_event_id"] == 10
    assert "FAIL" in evidence.build_report()
