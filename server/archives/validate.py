import json
import sqlite3

from pydantic import ValidationError

from server.archives.artwork import validate_artwork
from server.archives.assessments import validate_assessments
from server.archives.authoring import validate_authoring
from server.archives.background import validate_background
from server.archives.characters import validate_openings
from server.archives.configuration import validate_configuration_links
from server.archives.continuity import validate_continuity
from server.archives.format import JSON_FIELDS, MAX_ARCHIVE_BYTES, TABLES, ArchiveDocument
from server.archives.identities import validate_identities
from server.archives.interpretations import validate_interpretations
from server.archives.knowledge import validate_knowledge
from server.archives.library_imports import validate_imports
from server.archives.library_sources import validate_sources
from server.archives.links import validate_ownership
from server.archives.lore import validate_lore
from server.archives.lore_sources import validate_entry_sources
from server.archives.maintenance import validate_maintenance
from server.archives.memory_controls import validate_controls
from server.archives.migrations import upgrade
from server.archives.passage_revisions import validate_passage_revisions
from server.archives.patches import validate_patches
from server.archives.plans import validate_plan_edits
from server.archives.reviews import validate_draft_reviews
from server.archives.revisions import validate_revisions
from server.archives.roles import validate_role_snapshot
from server.archives.scenes import validate_scenes
from server.archives.side_memory import validate_side_memory
from server.archives.summaries import validate_summaries
from server.archives.summary_context import validate_writer_summaries
from server.archives.writer_memory import validate_writer_memory
from server.character_content import validate_character
from server.database import SCHEMA, decode, one
from server.errors import DomainError, require
from server.library import validate_dependencies
from server.manifests import expand_dependencies
from server.mechanics.config import configured_tables, read_settings
from server.mechanics.models import TableDefinition
from server.mechanics.tables import table_hash
from server.models import AssetCreate, StoryCreate
from server.prompts import ALL_PROMPT_LABELS as PROMPT_LABELS
from server.prompts import original_prompt
from server.providers.config import SavedProfileConfig


def parse_archive(content, *, verification=None):
    require(len(content.encode("utf-8")) <= MAX_ARCHIVE_BYTES, "Archives are limited to 128 MiB.")
    try:
        document = upgrade(ArchiveDocument.model_validate_json(content).model_dump())
        result = validate_archive(document)
        if verification is not None:
            verification.update(result)
        return document
    except DomainError:
        raise
    except (ValidationError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        raise DomainError("This archive has invalid records or an unsupported format. No stories were changed.", 400) from None


def validate_archive(document):
    require(set(document["data"]) == set(TABLES), "This archive's record groups do not match the supported format.")
    validate_entry_sources(document)
    validate_artwork(document['data'])
    validate_identities(document['data'])
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN")
        connection.execute("PRAGMA defer_foreign_keys=ON")
        for table in TABLES:
            insert_records(connection, table, document["data"][table])
        connection.executemany("INSERT INTO prompt_heads VALUES (?,?)", document["prompt_heads"].items())
        require(not connection.execute("PRAGMA foreign_key_check").fetchall(), "This archive has missing linked records.")
        validate_links(connection, document)
        validate_passage_revisions(connection, document['data'])
        validate_content(connection, document)
        validate_openings(connection, document['data'])
        validate_imports(connection, document['data'])
        validate_ownership(connection, document)
        validate_scenes(connection, document)
        validate_revisions(connection, document)
        validate_patches(connection, document)
        acyclic(document['data']['continuity_edits'], 'parent_id')
        validate_plan_edits(connection, document['data'])
        validate_continuity(connection, document)
        validate_draft_reviews(connection, document)
        validate_side_memory(document['data'])
        validate_assessments(connection, document['data'])
        validate_lore(connection, document['data'])
        validate_background(connection, document['data'])
        validate_interpretations(connection, document['data'])
        validate_authoring(connection, document)
        acyclic(document['data']['summary_versions'], 'parent_id')
        validate_summaries(connection, document['data'])
        validate_writer_summaries(connection, document['data'])
        validate_maintenance(connection, document['data'])
        acyclic(document['data']['memory_control_versions'], 'parent_id')
        validate_controls(connection, document['data'])
        validate_knowledge(connection, document['data'])
        report = validate_writer_memory(connection, document["data"])
        connection.rollback()
        return report


def insert_records(connection, table, rows):
    columns = [dict(row) for row in connection.execute(f"PRAGMA table_info({table})")]
    names = [column["name"] for column in columns]
    for row in rows:
        require(set(row) == set(names), f"An archive record in {table} has missing or unknown fields.")
        for column in columns:
            validate_scalar(row[column["name"]], column)
        for field in JSON_FIELDS.get(table, ()):
            json.loads(row[field])
    placeholders = ",".join("?" for _ in names)
    connection.executemany(f"INSERT INTO {table} ({','.join(names)}) VALUES ({placeholders})",
                           ([row[name] for name in names] for row in rows))


def validate_scalar(value, column):
    if value is None:
        require(not column["notnull"] and not column["pk"], "A required archive value is missing.")
        return
    expected = int if column["type"] == "INTEGER" else str
    require(type(value) is expected, "An archive value has the wrong type.")
    if column["pk"] and isinstance(value, str):
        require(bool(value) and len(value) <= 200, "An archive identifier is invalid.")


def acyclic(rows, parent_field):
    parents = {row["id"]: row[parent_field] for row in rows}
    complete = set()
    for start in parents:
        trail, node = set(), start
        while node and node not in complete:
            require(node in parents and node not in trail, "Archive ancestry is missing or cyclic.")
            trail.add(node)
            node = parents[node]
        complete.update(trail)


def validate_links(connection, document):
    data = document["data"]
    acyclic(data["nodes"], "parent_id")
    acyclic(data["branches"], "forked_from")
    relations = (
        ("nodes", "parent_id", "nodes"), ("nodes", "manifest_id", "manifests"),
        ("branches", "forked_from", "branches"), ("branches", "head_id", "nodes"),
        ("branches", "fork_node_id", "nodes"), ("branches", "manifest_id", "manifests"),
        ("adoptions", "old_manifest_id", "manifests"), ("adoptions", "new_manifest_id", "manifests"),
        ("mechanic_opportunities", "branch_id", "branches"),
    )
    for table, field, target in relations:
        bad = connection.execute(f"SELECT 1 FROM {table} a LEFT JOIN {target} b ON a.{field}=b.id "
                                 f"WHERE a.{field} IS NOT NULL AND (b.id IS NULL OR a.story_id<>b.story_id) LIMIT 1").fetchone()
        require(bad is None, "An archive link crosses stories or refers to missing history.")
    validate_heads(connection, document)


def validate_heads(connection, document):
    for row in document["data"]["stories"]:
        manifest = one(connection, "SELECT story_id FROM manifests WHERE id=?", (row["manifest_id"],))
        require(manifest["story_id"] == row["id"], "A story's attachment manifest is inconsistent.")
    for table, target, owner in (("assets", "asset_versions", "asset_id"), ("profiles", "profile_versions", "profile_id")):
        for row in document["data"][table]:
            version = one(connection, f"SELECT {owner} FROM {target} WHERE id=?", (row["latest_version_id"],))
            require(version[owner] == row["id"], "A library or model head belongs to another item.")
    selected = document["selection"]
    if selected:
        require(set(selected) == {"storyId", "branchId"}, "The archived selection is invalid.")
        branch = one(connection, "SELECT story_id FROM branches WHERE id=?", (selected["branchId"],))
        require(branch["story_id"] == selected["storyId"], "The archived selection crosses stories.")
    if document["primary_profile_id"]:
        one(connection, "SELECT id FROM profiles WHERE id=?", (document["primary_profile_id"],))


def validate_content(connection, document):
    data = document["data"]
    require(set(document["prompt_heads"]) == set(PROMPT_LABELS), "The archive needs a supported prompt for every role.")
    for row in data["stories"]:
        settings = decode(row["settings"])
        StoryCreate.model_validate({"title": row["title"], "premise": row["premise"], "settings": settings})
        configured_tables(connection, read_settings(row))
        validate_story_profiles(connection, settings)
        for key in PROMPT_LABELS:
            original_prompt(connection, key, row)
    for row in data["asset_versions"]:
        content = decode(row["content"])
        AssetCreate.model_validate({"kind": "lorebook", "name": row["name"], "content": content, "note": row["note"]})
        validate_dependencies(connection, content)
        if one(connection, 'SELECT kind FROM assets WHERE id=?', (row['asset_id'],))['kind'] == 'persona':
            validate_character(content)
    for row in data["manifests"]:
        expand_dependencies(connection, decode(row["attachments"]))
    validate_models_and_tables(data)
    validate_sources(document)
    validate_configuration_links(data)
    validate_runs(connection, data)


def validate_story_profiles(connection, settings):
    ids = set(settings.get("step_profiles", {}).values()) | {settings.get("primary_profile_id")}
    for profile_id in ids - {None}:
        one(connection, "SELECT id FROM profiles WHERE id=?", (profile_id,))


def validate_profile(profile):
    require(not profile.get("credential_ref"), "Credentials and vault references cannot be imported.")
    SavedProfileConfig.model_validate(profile["config"])


def validate_models_and_tables(data):
    for row in data["profile_versions"]:
        validate_profile({**row, "config": decode(row["config"])})
    for table in ("candidates", "side_replies"):
        for row in data[table]:
            validate_profile(decode(row["profile"]))
    for table in ("review_jobs", "scene_jobs", 'assessment_jobs', 'background_jobs', 'authoring_jobs', 'summary_jobs'):
        for row in data[table]:
            snapshot = decode(row['snapshot'])
            validate_profile(snapshot['profile'])
            validate_role_snapshot(snapshot, row['step'])
    for row in data['assessment_runs']:
        for profile in decode(row['snapshot'])['writer_profiles']:
            validate_profile(profile)
    for row in data["roll_table_versions"]:
        definition = decode(row["definition"])
        TableDefinition.model_validate(definition)
        require(row["table_id"] == definition["id"] and row["hash"] == table_hash(definition), "An archived table is inconsistent.")
    for row in data["nodes"]:
        require(row["role"] in {"user", "assistant", "narrator", "ooc"}, "An archived message role is unsupported.")


def validate_runs(connection, data):
    for table in ("generations", "review_runs", "mechanic_opportunities", "scene_runs", 'assessment_runs', 'background_runs', 'summary_runs'):
        for row in data[table]:
            snapshot = decode(row["snapshot"])
            require(snapshot["branch"]["id"] == row["branch_id"], "A saved run refers to a different branch.")
            one(connection, "SELECT id FROM branches WHERE id=?", (row["branch_id"],))
    for table in ("candidates", "review_jobs", "side_replies", "scene_jobs", 'assessment_jobs', 'background_jobs', 'authoring_jobs', 'summary_jobs'):
        for row in data[table]:
            require(row["status"] in {"queued", "running", "done", "error", "cancelled", "interrupted"}, "An archived job status is unsupported.")
    for row in data["node_mechanics"]:
        opportunity = decode(row["state"]).get("last_opportunity_id")
        if opportunity:
            one(connection, "SELECT id FROM mechanic_opportunities WHERE id=?", (opportunity,))
