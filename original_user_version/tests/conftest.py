"""Page tests must never write to the developer's working database."""

import pytest


@pytest.fixture(autouse=True)
def isolated_application_database(tmp_path, monkeypatch):
    from loopledger import ledger

    path = tmp_path / "application.db"
    monkeypatch.setenv("LOOPLEDGER_DB_PATH", str(path))
    ledger.init_db()
    return path
