"""Keep live configuration links; opaque provider inputs remain frozen evidence."""
from server.archives.format import JSON_FIELDS
from server.archives.records import related_rows
from server.database import decode, many
from server.errors import require
from server.mechanics.config import parse_settings


def configuration_references(data):
    prompts, tables = set(), set()
    for row in data["stories"]:
        settings = decode(row["settings"])
        prompts.update(settings.get("prompt_versions", {}).values())
        tables.update(parse_settings(settings.get("randomness", {})).table_versions.values())
    for row in data["nodes"]:
        prompts.add(decode(row["metadata"]).get("prompt_version_id"))
    for table, fields in JSON_FIELDS.items():
        if "snapshot" in fields:
            for row in data[table]:
                snapshot_references(decode(row["snapshot"]), prompts, tables)
    return {"prompt_versions": prompts - {None}, "roll_table_versions": tables}


def snapshot_references(snapshot, prompts, tables):
    prompts.add(snapshot.get("prompt", {}).get("id"))
    prompts.update(item['id'] for item in snapshot.get('prompt_sections', []))
    tables.update(item["id"] for item in snapshot.get("tables", {}).values())
    tables.update(snapshot.get("settings", {}).get("table_versions", {}).values())
    if 'writer_snapshot' in snapshot:
        snapshot_references(snapshot['writer_snapshot'], prompts, tables)
    if 'recipe' in snapshot:
        tables.update(item['id'] for item in snapshot['result']['tables'].values())


def validate_configuration_links(data):
    for table, ids in configuration_references(data).items():
        available = {row["id"] for row in data[table]}
        require(ids <= available, "The archive is missing configuration versions referenced by saved history.")


def collect_configuration(connection, data, scope):
    prompts = {row["key"]: row["version_id"] for row in many(connection, "SELECT * FROM prompt_heads")}
    tables = {row["id"]: row["version_id"] for row in many(connection, "SELECT * FROM roll_tables")}
    if scope == "workspace":
        for table in ("prompt_versions", "roll_tables", "roll_table_versions"):
            data[table] = many(connection, f"SELECT * FROM {table} ORDER BY rowid")
        return prompts
    settings = decode(data["stories"][0]["settings"])
    prompts.update(settings.get("prompt_versions", {}))
    tables.update(parse_settings(settings.get("randomness", {})).table_versions)
    refs = configuration_references(data)
    refs["prompt_versions"].update(prompts.values())
    refs["roll_table_versions"].update(tables.values())
    for table, ids in refs.items():
        data[table] = related_rows(connection, table, "id", ids)
    # The effective catalog includes every available table, including child dependencies.
    data["roll_tables"] = [{"id": key, "version_id": value} for key, value in tables.items()]
    return prompts
