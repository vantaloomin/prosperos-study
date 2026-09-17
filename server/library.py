from __future__ import annotations

from server.character_content import validate_character
from server.database import Database, decode, encode, identifier, many, now, one
from server.errors import require
from server.library_formats.artwork import validate_artwork_ref
from server.library_formats.files import SourceFiles
from server.library_formats.sources import validate_new_markdown
from server.lore.documents import normalize_lore
from server.lore.files import check_entries, stage_entries
from server.models import AssetCreate, AssetPublish


def version_view(row: dict) -> dict:
    return {**row, "content": decode(row["content"])}


def get_version(connection, version_id: str) -> dict:
    return version_view(one(connection, "SELECT * FROM asset_versions WHERE id=?", (version_id,)))


def validate_dependencies(connection, content: dict):
    validate_artwork_ref(connection, content)
    dependencies = content.get("lorebook_versions", [])
    require(isinstance(dependencies, list), "Lorebook references must be a list of version IDs.")
    require(len(dependencies) <= 100, "Too many lorebook references.")
    for version_id in dependencies:
        require(isinstance(version_id, str), "Each lorebook reference must be a version ID.")
        row = one(connection, "SELECT a.kind FROM asset_versions v JOIN assets a "
                  "ON a.id=v.asset_id WHERE v.id=?", (version_id,))
        require(row["kind"] == "lorebook", "Characters may only reference lorebook versions.")


def insert_version(connection, asset_id: str, number: int, body) -> dict:
    asset = one(connection, 'SELECT kind FROM assets WHERE id=?', (asset_id,))
    if asset['kind'] in {'character', 'persona'}:
        validate_character(body.content)
    else:
        validate_new_markdown(body.content)
        body = body.model_copy(update={'content': normalize_lore(body.content)})
    validate_dependencies(connection, body.content)
    version_id = identifier()
    connection.execute("INSERT INTO asset_versions VALUES (?,?,?,?,?,?,?)",
                       (version_id, asset_id, number, body.name, encode(body.content), body.note, now()))
    connection.execute("UPDATE assets SET latest_version_id=? WHERE id=?", (version_id, asset_id))
    return get_version(connection, version_id)


class Library:
    def __init__(self, database: Database):
        self.database = database

    def list(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = many(connection, "SELECT a.kind, v.*, o.created_at AS restored_at FROM assets a JOIN asset_versions v "
                        "ON v.id=a.latest_version_id LEFT JOIN archive_origins o ON o.id=a.id ORDER BY v.name COLLATE NOCASE")
            return [version_view(row) for row in rows]

    def create(self, body: AssetCreate) -> dict:
        with self.database.connect(write=True) as connection:
            return create_asset(connection, self.database, body)

    def publish(self, asset_id: str, body: AssetPublish) -> dict:
        with self.database.connect(write=True) as connection:
            return publish_asset(connection, self.database, asset_id, body)

    def history(self, asset_id: str) -> list[dict]:
        with self.database.connect() as connection:
            asset = one(connection, "SELECT kind FROM assets WHERE id=?", (asset_id,))
            return [{**version_view(row), 'kind': asset['kind']} for row in many(connection,
                    "SELECT * FROM asset_versions WHERE asset_id=? ORDER BY number DESC", (asset_id,))]

    def references(self, version_ids: list[str]) -> list[dict]:
        with self.database.connect() as connection:
            return [one(connection, 'SELECT v.id,v.asset_id,v.name,v.number,a.kind FROM asset_versions v '
                        'JOIN assets a ON a.id=v.asset_id WHERE v.id=?', (key,)) for key in dict.fromkeys(version_ids)]


def create_asset(connection, database, body):
    asset_id = identifier()
    connection.execute('INSERT INTO assets VALUES (?,?,NULL,?)', (asset_id, body.kind, now()))
    version = insert_version(connection, asset_id, 1, body)
    if body.kind == 'lorebook':
        SourceFiles(database).stage(connection, version)
        stage_entries(database, version)
    return {**version, 'kind': body.kind}


def publish_asset(connection, database, asset_id, body):
    asset = one(connection, 'SELECT * FROM assets WHERE id=?', (asset_id,))
    require(asset['latest_version_id'] == body.expected_version_id,
            'A newer version was published. Reopen the editor before saving.', 409)
    current = get_version(connection, asset['latest_version_id'])
    sources = SourceFiles(database) if asset['kind'] == 'lorebook' else None
    if sources:
        sources.check_edit(connection, asset_id, current['id'], body.expected_source_hash)
        check_entries(connection, database, current, body.expected_entry_hashes)
    version = insert_version(connection, asset_id, current['number'] + 1, body)
    if sources:
        sources.stage(connection, version)
        stage_entries(database, version)
        sources.check_edit(connection, asset_id, current['id'], body.expected_source_hash)
        check_entries(connection, database, current, body.expected_entry_hashes)
    connection.execute('INSERT INTO asset_import_origins SELECT ?,import_id,part FROM asset_import_origins WHERE version_id=?',
                       (version['id'], current['id']))
    return {**version, 'kind': asset['kind']}
