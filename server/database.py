import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from server.errors import require

SCHEMA = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


def identifier() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(UTC).isoformat()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decode(value: str):
    return json.loads(value)


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get("ROLEPLAY_DB", "data/roleplay.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from server.asset_migration import migrate_asset_kinds
        migrate_asset_kinds(self.path)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
        from server.library_formats.files import migrate_sources
        migrate_sources(self)

    @contextmanager
    def connect(self, write: bool = False):
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()


def one(connection, sql: str, values=()) -> dict:
    row = connection.execute(sql, values).fetchone()
    require(row is not None, "This item could not be found.", 404)
    return dict(row)


def many(connection, sql: str, values=()) -> list[dict]:
    return [dict(row) for row in connection.execute(sql, values).fetchall()]
