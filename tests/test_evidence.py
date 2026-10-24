"""D report contract tests, using isolated backend stubs (no real DB writes)."""

import importlib.util
import json
import sys
import types
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest


def _load_evidence_with_fake_backend(
    *, reviewers=None, stats=None, events=None, integrity=(True, None), calls=None
):
    """Load the real D source while injecting only backend function stubs."""
    import loopledger

    if reviewers is None:
        reviewers = [{
            "reviewer": "Demo",
            "n_reviews": 1,
            "avg_seconds": 42.0,
            "override_rate": 1.0,
            "gold_catch_rate": None,
            "short_reason_rate": 0.0,
            "flag": "insufficient_data",
        }]
    if stats is None:
        stats = {
            "total": 1, "auto_approved": 0, "auto_rejected": 0,
            "sent_to_review": 1, "reviewed": 1, "pending": 0,
        }
    if events is None:
        events = [
            {"id": 1, "event_type": "prediction", "hash": "abc123"},
            {"id": 2, "event_type": "review", "hash": "def456"},
        ]

    def _record(name, value):
        if calls is not None:
            calls.append(name)
        return deepcopy(value)

    ledger = types.ModuleType("loopledger.ledger")
    ledger.get_all_events = lambda: _record("events", events)
    ledger.verify_chain = lambda: _record("verify", integrity)
    metrics = types.ModuleType("loopledger.metrics")
    metrics.system_stats = lambda: _record("system", stats)

    class FakeFrame:
        def to_dict(self, orient):
            assert orient == "records"
            return _record("reviewer", reviewers)

    metrics.reviewer_stats = lambda: FakeFrame()
    location = Path(loopledger.__file__).resolve().parent / "evidence.py"
    spec = importlib.util.spec_from_file_location("loopledger._evidence_contract_test", location)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "loopledger.ledger": ledger,
        "loopledger.metrics": metrics,
    }):
        spec.loader.exec_module(module)
    return module


def test_report_json_contract():
    report = _load_evidence_with_fake_backend().build_report_json()
    assert report["system_stats"]["total"] == 1
    assert report["integrity"]["chain_intact"] is True
    assert report["event_counts"]["review"] == 1
    assert len(report["regulatory_mapping"]) == 4
    assert len(report["report_id"]) == 16
    assert "Local SQLite ledger snapshot" in report["data_origin"]
    json.dumps(report, allow_nan=False)


def test_markdown_report_contract():
    markdown = _load_evidence_with_fake_backend().build_report()
    assert "LoopLedger" in markdown
    assert "Reviewer Oversight Indicators" in markdown
    assert "Article 14" in markdown
    assert "PASS" in markdown
    assert "N/A (no control cases)" in markdown
    assert "Automatically rejected" in markdown


def test_failure_flag_exported():
    module = _load_evidence_with_fake_backend(integrity=(False, 2))
    assert module.build_report_json()["integrity"]["first_broken_event_id"] == 2
    assert "FAIL" in module.build_report()


def test_render_from_one_report_never_requeries_backend():
    calls = []
    module = _load_evidence_with_fake_backend(calls=calls)
    data = module.build_report_json()
    assert calls == ["events", "verify", "reviewer", "system"]
    original = list(calls)
    markdown = module.render_report(data)
    assert calls == original
    assert data["report_id"] in markdown
    assert data["generated_at"] in markdown
    assert data["integrity"]["chain_intact"]


def test_bundle_reuses_exact_json_snapshot_and_report_id():
    calls = []
    module = _load_evidence_with_fake_backend(calls=calls)
    data, markdown = module.build_report_bundle()
    assert calls == ["events", "verify", "reviewer", "system"]
    assert f'**Report ID:** `{data["report_id"]}`' in markdown
    assert data["generated_at"] in markdown
    json.dumps(data, allow_nan=False)


def test_missing_timing_and_override_rates_are_na_not_crashes():
    reviewers = [{
        "reviewer": "Missing", "n_reviews": 1,
        "avg_seconds": None, "override_rate": None,
        "gold_catch_rate": None, "short_reason_rate": 0.0,
        "flag": "insufficient_data",
    }]
    markdown = _load_evidence_with_fake_backend(reviewers=reviewers).build_report()
    row = next(line for line in markdown.splitlines() if line.startswith("| Missing |"))
    assert "| N/A | N/A | N/A (no control cases) | 0.0% |" in row


def test_zero_gold_catch_rate_is_zero_not_missing():
    reviewers = [{
        "reviewer": "Rubber", "n_reviews": 6, "avg_seconds": 2.0,
        "override_rate": 0.0, "gold_catch_rate": 0.0,
        "short_reason_rate": 1.0, "flag": "review_signals",
    }]
    markdown = _load_evidence_with_fake_backend(reviewers=reviewers).build_report()
    row = next(line for line in markdown.splitlines() if line.startswith("| Rubber |"))
    assert "| 0.0% | 0.0% | 100.0% |" in row


def test_empty_report_and_no_reviews_yet():
    module = _load_evidence_with_fake_backend(reviewers=[], events=[])
    data, markdown = module.build_report_bundle()
    assert data["integrity"]["tip_hash"] is None
    assert "EMPTY_LEDGER" in markdown
    assert "No reviews yet" in markdown
    json.dumps(data, allow_nan=False)


def test_nonfinite_reviewer_values_are_json_null_and_render_na():
    reviewers = [{
        "reviewer": "NaN", "n_reviews": 1,
        "avg_seconds": float("nan"), "override_rate": float("nan"),
        "gold_catch_rate": float("nan"), "short_reason_rate": float("nan"),
        "flag": "insufficient_data",
    }]
    module = _load_evidence_with_fake_backend(reviewers=reviewers)
    data, markdown = module.build_report_bundle()
    row = data["reviewer_metrics"][0]
    assert row["avg_seconds"] is None
    assert row["gold_catch_rate"] is None
    assert "N/A (no control cases)" in markdown
    json.dumps(data, allow_nan=False)


def test_gold_denominator_description_matches_b():
    data = _load_evidence_with_fake_backend().build_report_json()
    rule = data["methodology"]["gold_catch_rate"]
    assert "recommendation" in rule and "differs" in rule
    assert "Correct-AI controls are excluded" in rule
    assert "approve/reject" in rule
    assert "Legacy unsupported answer labels" in rule


def test_invalid_rates_are_not_silently_reported():
    module = _load_evidence_with_fake_backend()
    data = module.build_report_json()
    data["reviewer_metrics"][0]["override_rate"] = 2.0
    with pytest.raises(ValueError, match="between 0 and 1"):
        module.render_report(data)


def test_bad_type_is_rejected():
    module = _load_evidence_with_fake_backend()
    with pytest.raises(TypeError):
        module.render_report("not a report")
