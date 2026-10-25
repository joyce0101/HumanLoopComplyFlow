"""Local demo reviewer *account authentication*, not government ID proofing.

PBKDF2-HMAC-SHA256 with unique 16-byte salt; no plaintext passwords stored.
Self-registration is fine for a local hackathon but does NOT prove that a
particular real-world person owns the account. Database is private and excluded
from Git, independent from the audit/event database.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

DEFAULT_AUTH_DB = Path(__file__).resolve().parents[1] / "reviewer_accounts.db"
ITERATIONS = 390_000
USER_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def _db_path() -> Path:
    return Path(os.environ.get("LOOPLEDGER_AUTH_DB_PATH", str(DEFAULT_AUTH_DB)))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS reviewers (
        username TEXT PRIMARY KEY,
        salt BLOB NOT NULL,
        password_hash BLOB NOT NULL,
        created_at INTEGER NOT NULL,
        failures INTEGER NOT NULL DEFAULT 0,
        lock_until INTEGER NOT NULL DEFAULT 0
    )""")
    connection.commit()
    return connection


def register(username: str, password: str) -> None:
    username = username.strip()
    if not USER_PATTERN.fullmatch(username):
        raise ValueError("Username must have 3-32 characters: letters, digits, _.-")
    if not isinstance(password, str) or len(password) < 10:
        raise ValueError("Password must have at least 10 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    with _connect() as connection:
        try:
            connection.execute(
                "INSERT INTO reviewers (username,salt,password_hash,created_at) VALUES (?,?,?,?)",
                (username, salt, digest, int(time.time())),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Reviewer account already exists") from exc


def authenticate(username: str, password: str, *, now: int | None = None) -> bool:
    if not isinstance(username, str) or not isinstance(password, str):
        return False
    tick = int(time.time()) if now is None else now
    with _connect() as connection:
        row = connection.execute("SELECT * FROM reviewers WHERE username=?", (username.strip(),)).fetchone()
        if row is None or tick < row["lock_until"]:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), row["salt"], ITERATIONS)
        success = hmac.compare_digest(digest, row["password_hash"])
        if success:
            connection.execute("UPDATE reviewers SET failures=0,lock_until=0 WHERE username=?", (username.strip(),))
        else:
            failures = row["failures"] + 1
            wait_until = tick + 30 if failures >= 5 else 0
            connection.execute("UPDATE reviewers SET failures=?,lock_until=? WHERE username=?",
                               (0 if wait_until else failures, wait_until, username.strip()))
        return success
