"""D-owned contract tests for evidence exports; independent of unfinished B modules."""
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch


def _load_evidence_with_fake_backend():
    """Load the real D source while injecting only the backend function stubs."""
    import loopledger
    package_root = Path(loopledger.__file__).resolve().parent
    ledger = types.ModuleType("loopledger.ledger")
    ledger.get_all_events = lambda: [
        {"id": 1, "event_type": "prediction", "hash": "abc123"},
        {"id": 2, "event_type": "review", "hash": "def456"},
    ]
    ledger.verify_chain = lambda: (True, None)
    metrics = types.ModuleType("loopledger.metrics")
    metrics.system_stats = lambda: {
        "total": 1, "auto_approved": 0, "sent_to_review": 1,
        "reviewed": 1, "pending": 0,
    }

    class FakeFrame:
        def to_dict(self, orient):
            assert orient == "records"
            return [{
                "reviewer": "Demo", "n_reviews": 1, "avg_seconds": 42.0,
                "override_rate": 1.0, "gold_catch_rate": None,
                "short_reason_rate": 0.0, "flag": "insufficient_data",
            }]

    metrics.reviewer_stats = lambda: FakeFrame()
    location = package_root / "evidence.py"
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
    json.dumps(report, allow_nan=False)


def test_markdown_report_contract():
    markdown = _load_evidence_with_fake_backend().build_report()
    assert "LoopLedger" in markdown
    assert "Reviewer Oversight Indicators" in markdown
    assert "Article 14" in markdown
    assert "PASS" in markdown
    assert "N/A (no control cases)" in markdown


def test_failure_flag_exported():
    module = _load_evidence_with_fake_backend()
    module.verify_chain = lambda: (False, 2)
    assert module.build_report_json()["integrity"]["first_broken_event_id"] == 2
    assert "FAIL" in module.build_report()
