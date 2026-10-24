"""B's reversible tamper demo, functional acceptance and real compliance UI."""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from streamlit.testing.v1 import AppTest

from loopledger import ledger, metrics
from scripts.demo_check import run_check
from scripts.demo_reset import seed_demo, seed_oversight_demo
from scripts.demo_tamper import database_scope, make_tampered_copy


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "source.db"
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(path))
    ledger.init_db()
    seed_demo()
    return path


def test_tamper_copy_detects_exact_event_and_leaves_source_bytes_unchanged(database, tmp_path):
    before = hashlib.sha256(database.read_bytes()).digest()
    original_events = ledger.get_all_events()
    output = tmp_path / "damaged.db"
    result = make_tampered_copy(database, output, 10)
    assert result["before"] == {"chain_intact": True, "first_broken_event_id": None}
    assert result["after"] == {"chain_intact": False, "first_broken_event_id": 10}
    assert os.environ["LOOPLEDGER_DB_PATH"] == str(database)
    assert ledger.verify_chain() == (True, None)
    assert ledger.get_all_events() == original_events
    assert hashlib.sha256(database.read_bytes()).digest() == before
    with database_scope(output):
        assert ledger.verify_chain() == (False, 10)
        assert len(ledger.get_all_events()) == 20


def test_source_and_existing_output_are_never_overwritten(database, tmp_path):
    before = database.read_bytes()
    with pytest.raises(ValueError, match="differ"):
        make_tampered_copy(database, database)
    output = tmp_path / "existing.db"
    output.write_bytes(b"keep this user's file")
    with pytest.raises(FileExistsError):
        make_tampered_copy(database, output)
    assert output.read_bytes() == b"keep this user's file"
    assert database.read_bytes() == before


@pytest.mark.parametrize("event_id", [0, -1, True, 1.5])
def test_invalid_event_id_refuses_to_create_a_copy(database, tmp_path, event_id):
    output = tmp_path / "refused.db"
    with pytest.raises(ValueError):
        make_tampered_copy(database, output, event_id)
    assert not output.exists()


def test_missing_source_or_event_leaves_no_new_database(database, tmp_path):
    missing = tmp_path / "missing.db"
    output = tmp_path / "refused.db"
    with pytest.raises(FileNotFoundError):
        make_tampered_copy(missing, output)
    assert not missing.exists()
    assert not output.exists()
    with pytest.raises(ValueError, match="does not exist"):
        make_tampered_copy(database, output, 999)
    assert not output.exists()


def test_already_broken_source_refuses_a_successful_demo_and_cleans_own_copy(database, tmp_path):
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE events SET ts='pre-existing corruption' WHERE id=2")
    before = database.read_bytes()
    output = tmp_path / "refused.db"
    with pytest.raises(ValueError, match="already inconsistent"):
        make_tampered_copy(database, output)
    assert not output.exists()
    assert database.read_bytes() == before
    assert os.environ["LOOPLEDGER_DB_PATH"] == str(database)


def test_sqlite_backup_includes_committed_wal_events(database, tmp_path):
    with closing(sqlite3.connect(database)) as keeper:
        assert keeper.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        keeper.execute("BEGIN")
        assert keeper.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 20
        ledger.log_event("export", {"source": "committed WAL event"})
        assert Path(str(database) + "-wal").exists()
        result = make_tampered_copy(database, tmp_path / "wal-copy.db", 21)
        assert result["after"]["first_broken_event_id"] == 21
        assert ledger.verify_chain() == (True, None)
        assert len(ledger.get_all_events()) == 21


def test_database_scope_restores_absent_and_nested_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("LOOPLEDGER_DB_PATH", raising=False)
    first, second = tmp_path / "first.db", tmp_path / "second.db"
    with database_scope(first):
        assert os.environ["LOOPLEDGER_DB_PATH"] == str(first.resolve())
        with database_scope(second):
            assert os.environ["LOOPLEDGER_DB_PATH"] == str(second.resolve())
        assert os.environ["LOOPLEDGER_DB_PATH"] == str(first.resolve())
    assert "LOOPLEDGER_DB_PATH" not in os.environ


def test_functional_seed_uses_binary_actions_and_real_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(tmp_path / "functional.db"))
    ledger.init_db()
    seed_oversight_demo(binary_only=True)
    events = ledger.get_all_events()
    assert len(events) == 44
    assert len(ledger.get_pending_reviews()) == 2
    assert {e["payload"]["action"] for e in events if e["event_type"] == "review"} == {"approve", "reject"}
    assert all(e["payload"]["gold_correct_decision"] != "modify" for e in events if e["event_type"] == "prediction")
    gates = [e["payload"] for e in events if e["event_type"] == "gate"]
    assert sum(g["needs_review"] for g in gates) == 14
    assert any("Gold-standard oversight test" in g["reasons"] for g in gates)
    assert all("Case ID mismatch" not in g["reasons"] for g in gates)
    frame = metrics.reviewer_stats().set_index("reviewer")
    assert frame.loc["careful_reviewer", "gold_catch_rate"] == 1.0
    assert frame.loc["rubber_stamp", "gold_catch_rate"] == 0.0


def test_reset_cli_accepts_functional_profile(tmp_path):
    output = subprocess.run(
        [sys.executable, str(ROOT / "scripts/demo_reset.py"), "--db", str(tmp_path / "cli.db"),
         "--profile", "functional"], capture_output=True, text=True, check=True, timeout=30,
    )
    result = json.loads(output.stdout)
    assert result["profile"] == "functional"
    assert (result["events"], result["pending"], result["chain_intact"]) == (44, 2, True)


def test_functional_cli_produces_clean_and_tampered_reports_without_touching_default_db(tmp_path):
    default_database = ROOT / "loopledger.db"
    before = hashlib.sha256(default_database.read_bytes()).digest()
    directory = tmp_path / "acceptance"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/demo_check.py"), "--output-dir", str(directory)],
        capture_output=True, text=True, check=True, timeout=90,
    )
    summary = json.loads(completed.stdout)
    assert summary["status"] == "passed"
    assert len(summary["passed_steps"]) == 7
    assert summary["events"] == 46
    assert (summary["system_stats"]["reviewed"], summary["system_stats"]["pending"]) == (14, 0)
    assert json.loads((directory / "summary.json").read_text(encoding="utf-8")) == summary
    clean_report = json.loads((directory / "clean-report.json").read_text(encoding="utf-8"))
    bad_report = json.loads((directory / "tampered-report.json").read_text(encoding="utf-8"))
    assert clean_report["integrity"]["chain_intact"] is True
    assert bad_report["integrity"]["chain_intact"] is False
    assert bad_report["integrity"]["first_broken_event_id"] == 10
    assert "PASS" in (directory / "clean-report.md").read_text(encoding="utf-8")
    assert "FAIL" in (directory / "tampered-report.md").read_text(encoding="utf-8")
    with database_scope(directory / "clean.db"):
        assert all(e["payload"]["action"] in ("approve", "reject")
                   for e in ledger.get_all_events() if e["event_type"] == "review")
        assert ledger.verify_chain() == (True, None)
    assert hashlib.sha256(default_database.read_bytes()).digest() == before


def test_functional_check_refuses_existing_artifacts_without_changing_environment(tmp_path, monkeypatch):
    original = tmp_path / "original.db"
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(original))
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_check(tmp_path)
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert os.environ["LOOPLEDGER_DB_PATH"] == str(original)
    assert not original.exists()


def test_tamper_cli_reports_failure_and_accepts_database_environment(database, tmp_path):
    command = [sys.executable, str(ROOT / "scripts/demo_tamper.py"), "--output", str(tmp_path / "cli-copy.db")]
    completed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
    result = json.loads(completed.stdout)
    assert result["source"] == str(database.resolve())
    assert result["after"]["first_broken_event_id"] == 10
    failed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert failed.returncode != 0
    assert "already exists" in failed.stderr


def test_functional_cli_timeout_exits_without_touching_existing_database(database, tmp_path):
    before = database.read_bytes()
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/demo_check.py"),
         "--output-dir", str(tmp_path / "timeout-output"), "--timeout-seconds", "0.001"],
        capture_output=True, text=True, timeout=15,
    )
    assert completed.returncode != 0
    assert "timed out" in completed.stderr
    assert database.read_bytes() == before


def test_real_compliance_ui_verifies_downloads_and_recovers_without_page_edits(database, tmp_path, monkeypatch):
    before = database.read_bytes()
    app = AppTest.from_file(str(ROOT / "pages/4_Compliance.py"), default_timeout=30).run()
    app.radio(key="cp_source").set_value("Backend interfaces").run()

    def click(label):
        next(button for button in app.button if button.label == label).click().run()
        assert not app.exception

    click("Verify chain")
    assert app.session_state["cp_chain"]["status"] == "passed"
    click("Generate report")
    assert app.session_state["cp_export"] is not None
    damaged = tmp_path / "ui-tampered.db"
    make_tampered_copy(database, damaged)
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(damaged))
    click("Verify chain")
    assert app.session_state["cp_chain"]["status"] == "inconsistent"
    assert app.session_state["cp_chain"]["broken_id"] == 10
    assert app.session_state["cp_export"] is None
    click("Generate report")
    data = json.loads(app.session_state["cp_export"]["json_text"])
    assert data["integrity"]["chain_intact"] is False
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(database))
    click("Verify chain")
    assert app.session_state["cp_chain"]["status"] == "passed"
    assert app.session_state["cp_export"] is None
    assert database.read_bytes() == before
