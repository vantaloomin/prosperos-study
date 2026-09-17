from server.archives.format import TABLES
from server.archives.remap import identities, remap_record
from server.database import identifier, one


def insert_row(connection, table, row):
    columns = ",".join(row)
    placeholders = ",".join("?" for _ in row)
    connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(row.values()))


def import_versions(connection, table, rows, document, mapping):
    owner = "key" if table == "prompt_versions" else "table_id"
    for row in rows:
        local = remap_record(table, row, document, mapping)
        maximum = one(connection, f"SELECT COALESCE(MAX(number),0) AS n FROM {table} WHERE {owner}=?", (row[owner],))["n"]
        local["number"] = maximum + 1
        insert_row(connection, table, local)


def import_table_heads(connection, document, mapping):
    for row in document["data"]["roll_tables"]:
        connection.execute("INSERT OR IGNORE INTO roll_tables VALUES (?,?)", (row["id"], mapping[row["version_id"]]))


def restore(connection, document):
    mapping = identities(document["data"])
    connection.execute("PRAGMA defer_foreign_keys=ON")
    import_table_heads(connection, document, mapping)
    for table in TABLES:
        import_group(connection, table, document, mapping)
    selected = document["selection"]
    return {"selection": {key: mapping[value] for key, value in selected.items()},
            "story_ids": [mapping[row["id"]] for row in document["data"]["stories"]],
            "identity_map": mapping, "receipt_id": identifier()}


def import_group(connection, table, document, mapping):
    if table == "roll_tables":
        return
    rows = document["data"][table]
    if table == 'library_media':
        from server.library_formats.artwork import store_artwork
        for row in rows:
            store_artwork(connection, row)
        return
    if table in {"prompt_versions", "roll_table_versions"}:
        import_versions(connection, table, rows, document, mapping)
        return
    for row in rows:
        insert_row(connection, table, remap_record(table, row, document, mapping))
