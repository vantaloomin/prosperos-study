import hashlib
import json
from pathlib import Path

from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.mechanics.models import TableDefinition
from server.operations import previous, remember


def table_view(row):
    return {**row, "definition": decode(row["definition"])}


def table_hash(definition):
    return hashlib.sha256(json.dumps(definition, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def insert_version(connection, definition, number):
    version_id = identifier()
    connection.execute("INSERT INTO roll_table_versions VALUES (?,?,?,?,?,?)",
                       (version_id, definition["id"], number, encode(definition), table_hash(definition), now()))
    connection.execute("UPDATE roll_tables SET version_id=? WHERE id=?", (version_id, definition["id"]))
    return version_id


def initialize_tables(database):
    defaults = json.loads(Path(__file__).with_name("defaults.json").read_text(encoding="utf-8"))
    with database.connect(write=True) as connection:
        for raw in defaults:
            definition = TableDefinition.model_validate(raw).model_dump()
            exists = connection.execute("SELECT id FROM roll_tables WHERE id=?", (definition["id"],)).fetchone()
            if exists:
                continue
            connection.execute("INSERT INTO roll_tables VALUES (?,NULL)", (definition["id"],))
            insert_version(connection, definition, 1)


def catalog(connection, pins=None):
    result = {row["table_id"]: table_view(row) for row in many(connection,
              "SELECT v.* FROM roll_tables t JOIN roll_table_versions v ON t.version_id=v.id ORDER BY t.id")}
    for table_id, version_id in (pins or {}).items():
        version = table_view(one(connection, "SELECT * FROM roll_table_versions WHERE id=?", (version_id,)))
        require(version["table_id"] == table_id, "A table version belongs to a different table.")
        result[table_id] = version
    return result


def child_ids(definition):
    children = [row["child"] for row in definition["rows"] if row["child"]]
    for field in ["low_overflow", "high_overflow"]:
        overflow = definition.get(field)
        if overflow and overflow["child"]:
            children.append(overflow["child"])
    return children


def validate_graph(definitions, key, seen=()):
    require(key in definitions, f"Referenced table {key} does not exist.")
    require(key not in seen, "Child tables cannot form a cycle.")
    require(len(seen) < 8, "Table nesting is limited to eight levels.")
    for child in child_ids(definitions[key]):
        validate_graph(definitions, child, (*seen, key))


class Tables:
    def __init__(self, database):
        self.database = database

    def list(self):
        with self.database.connect() as connection:
            return list(catalog(connection).values())

    def history(self, table_id):
        with self.database.connect() as connection:
            return [table_view(row) for row in many(connection,
                    "SELECT * FROM roll_table_versions WHERE table_id=? ORDER BY number DESC", (table_id,))]

    def publish(self, table_id, body):
        payload = {"table_id": table_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "table", payload)
            if cached is not None:
                return cached
            definition = body.definition.model_dump()
            require(definition["id"] == table_id, "A table's identifier cannot change.")
            versions = catalog(connection)
            number = self._check_head(connection, table_id, versions.get(table_id), body.expected_version_id)
            definitions = {key: value["definition"] for key, value in versions.items()}
            definitions[table_id] = definition
            for key in definitions:
                validate_graph(definitions, key)
            version_id = insert_version(connection, definition, number)
            return remember(connection, body.operation_id, "table", payload, {"id": version_id})

    @staticmethod
    def _check_head(connection, table_id, current, expected):
        if current:
            require(current["id"] == expected, "This table changed. Reopen it before publishing.", 409)
            return one(connection, "SELECT MAX(number)+1 AS next FROM roll_table_versions WHERE table_id=?", (table_id,))["next"]
        require(expected is None, "This table does not exist.", 404)
        connection.execute("INSERT INTO roll_tables VALUES (?,NULL)", (table_id,))
        return 1
