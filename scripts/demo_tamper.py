"""Demonstrate audit tampering on a new SQLite backup; never edit the source."""

import argparse
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from uuid import uuid4

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loopledger import ledger


@contextmanager
def database_scope(path: Path):
    """Select a database for this single-threaded CLI and restore the environment."""
    previous = os.environ.get("LOOPLEDGER_DB_PATH")
    os.environ["LOOPLEDGER_DB_PATH"] = str(path.resolve())
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("LOOPLEDGER_DB_PATH", None)
        else:
            os.environ["LOOPLEDGER_DB_PATH"] = previous


def make_tampered_copy(source: Path, output: Path, event_id: int = 10) -> dict:
    """Copy a consistent SQLite snapshot and edit one payload without rehashing.

    An existing output is always refused. The source connection is read-only;
    SQLite backup also captures committed WAL content, unlike copying .db bytes.
    """
    source, output = Path(source).resolve(), Path(output).resolve()
    if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id < 1:
        raise ValueError("event_id must be a positive integer")
    if source == output:
        raise ValueError("Output must differ from the source database")
    if not source.is_file():
        raise FileNotFoundError(f"Source database does not exist: {source}")
    if output.exists():
        raise FileExistsError(f"Output already exists; choose a new path: {output}")
    created = False
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10)) as original:
            if original.execute("SELECT 1 FROM events WHERE id=?", (event_id,)).fetchone() is None:
                raise ValueError(f"Event #{event_id} does not exist in the source")
            output.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents accidental overwrite, including a race
            # after the existence check above.
            with output.open("xb"):
                created = True
            with closing(sqlite3.connect(output, timeout=10)) as copied:
                deadline = time.monotonic() + 10

                def check_backup_deadline(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise TimeoutError("SQLite backup exceeded 10 seconds; source was not modified")

                original.backup(copied, pages=128, progress=check_backup_deadline)
        with database_scope(output):
            before = ledger.verify_chain()
            if before != (True, None):
                raise ValueError(f"Source snapshot is already inconsistent at #{before[1]}")
            with closing(sqlite3.connect(output, timeout=10)) as copied:
                with copied:
                    payload = json.loads(copied.execute(
                        "SELECT payload FROM events WHERE id=?", (event_id,),
                    ).fetchone()[0])
                    payload["_demo_tamper_marker"] = uuid4().hex
                    copied.execute(
                        "UPDATE events SET payload=? WHERE id=?",
                        (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), event_id),
                    )
            after = ledger.verify_chain()
            if after != (False, event_id):
                raise RuntimeError(f"Expected a broken chain at #{event_id}, received {after}")
        return {
            "source": str(source), "output": str(output), "source_opened_read_only": True,
            "before": {"chain_intact": before[0], "first_broken_event_id": before[1]},
            "after": {"chain_intact": after[0], "first_broken_event_id": after[1]},
        }
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(os.environ.get("LOOPLEDGER_DB_PATH", ledger.DB_PATH)))
    parser.add_argument("--output", type=Path, required=True, help="New database file; existing files are refused")
    parser.add_argument("--event-id", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        result = make_tampered_copy(args.source, args.output, args.event_id)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Tamper demo failed: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
