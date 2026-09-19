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
        self.node_listeners = []
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
            watermark = self.node_watermark(connection) if write and self.node_listeners else None
            yield connection
            nodes = self.new_nodes(connection, watermark) if watermark is not None else []
            connection.commit()
            for listener in self.node_listeners:
                if nodes:
                    try:
                        listener(nodes)
                    except Exception:
                        pass  # Cache notifications cannot turn a committed write into a failure.
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def node_watermark(connection):
        return connection.execute('SELECT COALESCE(MAX(rowid),0) FROM nodes').fetchone()[0]

    @staticmethod
    def new_nodes(connection, watermark):
        # Bounded notifications, including large imports. Missing cache entries are
        # always prepared normally when actually needed by foreground retrieval.
        return many(connection, 'SELECT id,role,text FROM nodes WHERE rowid>? AND length(text)<=64000 '
                    'ORDER BY rowid DESC LIMIT 64', (watermark,))


def one(connection, sql: str, values=()) -> dict:
    row = connection.execute(sql, values).fetchone()
    require(row is not None, "This item could not be found.", 404)
    return dict(row)


def many(connection, sql: str, values=()) -> list[dict]:
    return [dict(row) for row in connection.execute(sql, values).fetchall()]
