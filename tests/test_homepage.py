"""Homepage links remain internal and never disturb workflow session data."""

from dataclasses import asdict
import hashlib
from pathlib import Path
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from loopledger import ledger
from loopledger.schemas import Prediction, ReviewAction


ROOT = Path(__file__).resolve().parents[1]


def open_home():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert len(app.get("page_link")) == 4, "Homepage needs four business-page entry points."
    return app


def test_homepage_registers_four_distinct_internal_page_targets():
    app = open_home()
    links = app.get("page_link")
    assert {link.proto.label for link in links} == {
        "Open Run Batch", "Open Review Queue", "Open Oversight Dashboard", "Open Compliance",
    }
    assert all(not link.proto.external for link in links)
    assert len({link.proto.page_script_hash for link in links}) == 4
    assert all(not link.proto.disabled for link in links)


def test_homepage_does_not_seed_workflow_data_or_write_database():
    database = ROOT / "loopledger.db"
    before = hashlib.sha256(database.read_bytes()).digest()
    app = open_home()
    for key in ("rq_pending_reviews", "rq_submitted_reviews", "rb_last_batch", "cp_chain", "cp_export"):
        assert key not in app.session_state
    app.run()
    assert not app.exception
    assert hashlib.sha256(database.read_bytes()).digest() == before


def test_home_review_home_round_trip_preserves_existing_pending_and_completed_reviews():
    pred = Prediction("KEEP", {"credit_amount": 3000, "duration": 24, "age": 35},
                      "approve", 0.8, [("age", -0.1), ("duration", 0.1), ("credit_amount", 0.2)])
    action = ReviewAction("DONE", "alice", "reject", "Documents checked.", 20.0)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20)
    ledger.log_event("prediction", asdict(pred))
    ledger.log_event("prediction", asdict(Prediction("DONE", {}, "approve", .6, [])))
    ledger.submit_review(action)
    app.run()
    assert not app.exception
    app.switch_page("pages/2_Review_Queue.py").run()
    assert not app.exception
    assert len(app.selectbox[0].options) == 1
    assert ledger.get_pending_reviews() == [pred]
    app.switch_page("app.py").run()
    assert not app.exception
    assert len(app.get("page_link")) == 4
    assert ledger.get_pending_reviews() == [pred]
    assert ledger.get_all_events()[-1]["payload"] == asdict(action)


def test_older_streamlit_can_show_homepage_with_a_text_diagram_fallback():
    with patch.object(st, "mermaid_chart", None):
        app = open_home()
    assert app.code
    assert "Human review" in app.code[0].value
