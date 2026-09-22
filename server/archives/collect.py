from server.archives.artwork import collect_artwork
from server.archives.authoring import collect_authoring
from server.archives.configuration import collect_configuration
from server.archives.format import ARCHIVE_VERSION, TABLES
from server.archives.identities import collect_identities
from server.archives.inspiration import collect_inspiration
from server.archives.library_imports import collect_imports
from server.archives.library_sources import collect_sources
from server.archives.migration_sources import collect_migration_sources
from server.archives.presets import collect_presets, preset_profiles
from server.archives.records import related_rows
from server.archives.style_analysis import collect_analyses
from server.archives.text_edit_versions import asset_references
from server.archives.writing import collect_writing
from server.archives.writing import referenced_profiles as writing_profiles
from server.authoring.context import defaults
from server.database import decode, encode, many, now, one
from server.errors import require
from server.profiles import primary_id

STORY_TABLES = ("manifests", "branches", "nodes", "adoptions", "mechanic_opportunities", "side_threads", 'background_states', 'manuscripts', 'branch_comparisons', 'text_documents', 'text_edit_proposals', 'text_edit_receipts', 'companion_edit_origins', 'recipe_runs')
RELATED = (
    ('recipe_jobs', 'run_id', 'recipe_runs'), ('recipe_attempts', 'job_id', 'recipe_jobs'), ('recipe_results', 'run_id', 'recipe_runs'),
    ('side_contexts', 'thread_id', 'side_threads'), ('side_context_heads', 'thread_id', 'side_threads'),
    ('side_drafts', 'thread_id', 'side_threads'),
    ('side_thread_curation', 'thread_id', 'side_threads'),
    ('branch_curation', 'branch_id', 'branches'),
    ('relationship_jobs', 'branch_id', 'branches'), ('relationship_attempts', 'job_id', 'relationship_jobs'),
    ('branch_cleanup_timing', 'branch_id', 'branches'),
    ('branch_cleanup_settings', 'branch_id', 'branches'),
    ('path_revisions', 'branch_id', 'branches'),
    ('continuity_edits', 'branch_id', 'branches'), ('branch_continuity_edits', 'branch_id', 'branches'),
    ('memory_control_versions', 'branch_id', 'branches'), ('branch_memory_controls', 'branch_id', 'branches'),
    ('summary_pending', 'branch_id', 'branches'), ('summary_wakeups', 'branch_id', 'branches'),
    ('summary_batches', 'branch_id', 'branches'), ('summary_batch_runs', 'batch_id', 'summary_batches'),
    ('summary_runs', 'branch_id', 'branches'), ('summary_jobs', 'run_id', 'summary_runs'),
    ('summary_attempts', 'job_id', 'summary_jobs'), ('summary_versions', 'run_id', 'summary_runs'),
    ("generations", "branch_id", "branches"), ("candidates", "generation_id", "generations"),
    ("generation_attempts", "candidate_id", "candidates"), ("node_mechanics", "node_id", "nodes"),
    ('candidate_activity', 'candidate_id', 'candidates'),
    ('candidate_cleanups', 'candidate_id', 'candidates'),
    ('candidate_text_heads', 'candidate_id', 'candidates'),
    ("review_runs", "branch_id", "branches"), ("review_jobs", "run_id", "review_runs"),
    ("review_attempts", "job_id", "review_jobs"), ("side_turns", "thread_id", "side_threads"),
    ("side_replies", "turn_id", "side_turns"),
    ('side_edit_results', 'reply_id', 'side_replies'),
    ("scene_runs", "branch_id", "branches"), ("scene_jobs", "run_id", "scene_runs"),
    ("scene_attempts", "job_id", "scene_jobs"), ("scene_decisions", "run_id", "scene_runs"),
    ('continuity_commits', 'node_id', 'nodes'),
    ('assessment_runs', 'branch_id', 'branches'), ('assessment_jobs', 'run_id', 'assessment_runs'),
    ('assessment_attempts', 'job_id', 'assessment_jobs'),
    ('branch_background', 'branch_id', 'branches'), ('node_background', 'node_id', 'nodes'),
    ('background_runs', 'branch_id', 'branches'), ('background_jobs', 'run_id', 'background_runs'),
    ('background_attempts', 'job_id', 'background_jobs'),
)


def collect_library(connection, data, complete):
    if complete:
        data["assets"] = many(connection, "SELECT * FROM assets ORDER BY rowid")
        data["asset_versions"] = many(connection, "SELECT * FROM asset_versions ORDER BY rowid")
        return
    pending = {item["asset_id"] for row in data["manifests"] for item in decode(row["attachments"])}
    pending.update(asset_references(data))
    visited = set()
    while pending:
        asset_ids = pending - visited
        if not asset_ids:
            break
        visited.update(asset_ids)
        data["assets"].extend(related_rows(connection, "assets", "id", asset_ids))
        versions = related_rows(connection, "asset_versions", "asset_id", asset_ids)
        data["asset_versions"].extend(versions)
        refs = {ref for row in versions for ref in decode(row["content"]).get("lorebook_versions", [])}
        pending = {row["asset_id"] for row in related_rows(connection, "asset_versions", "id", refs)}


def referenced_profiles(data, primary):
    from server.archives.recipes import recipe_references
    result = {primary} - {None}
    result.update(recipe_references(data)['profiles'])
    for row in data["stories"]:
        settings = decode(row["settings"])
        result.update(settings.get("step_profiles", {}).values())
        result.update({settings.get("primary_profile_id")} - {None})
    for table in ("candidates", "side_replies"):
        result.update(decode(row["profile"])["profile_id"] for row in data[table])
    for table in ("review_jobs", "scene_jobs", 'assessment_jobs', 'background_jobs', 'authoring_jobs', 'summary_jobs', 'relationship_jobs', 'style_analysis_jobs', 'recipe_jobs'):
        result.update(decode(row["snapshot"])["profile"]["profile_id"] for row in data[table])
    result.update(profile['profile_id'] for row in data['assessment_runs']
                  for profile in decode(row['snapshot'])['writer_profiles'])
    return result


def redact_profiles(data):
    from server.writing.recipe_bindings import redact_plan
    for row in data['recipe_runs']:
        row['snapshot'] = encode(redact_plan(decode(row['snapshot'])))
    for row in data["profile_versions"]:
        row["credential_ref"] = None
    for table in ("candidates", "side_replies"):
        for row in data[table]:
            profile = decode(row["profile"])
            profile["credential_ref"] = None
            row["profile"] = encode(profile)
    for table in ("review_jobs", "scene_jobs", 'assessment_jobs', 'background_jobs', 'authoring_jobs', 'summary_jobs', 'relationship_jobs', 'style_analysis_jobs', 'recipe_jobs'):
        for row in data[table]:
            snapshot = decode(row["snapshot"])
            snapshot["profile"]["credential_ref"] = None
            row["snapshot"] = encode(snapshot)
    for row in data['assessment_runs']:
        snapshot = decode(row['snapshot'])
        for profile in snapshot['writer_profiles']:
            profile['credential_ref'] = None
        row['snapshot'] = encode(snapshot)


def collect(connection, options):
    data = {table: [] for table in TABLES}
    if options.scope == "story":
        require(bool(options.story_id), "Choose a story to archive.")
        data["stories"] = [one(connection, "SELECT * FROM stories WHERE id=?", (options.story_id,))]
    else:
        data["stories"] = many(connection, "SELECT * FROM stories ORDER BY rowid")
    story_ids = {row["id"] for row in data["stories"]}
    for table in STORY_TABLES:
        data[table] = related_rows(connection, table, "story_id", story_ids)
    if not options.include_sidebar:
        data["side_threads"] = []
    for table, field, parent in RELATED:
        data[table] = related_rows(connection, table, field, {row["id"] for row in data[parent]})
    collect_library(connection, data, options.scope == "workspace")
    collect_authoring(connection, data, options.scope == 'workspace')
    collect_sources(connection, data)
    collect_imports(connection, data)
    collect_migration_sources(connection, data)
    collect_artwork(connection, data)
    collect_writing(connection, data, options.scope == 'workspace')
    collect_presets(connection, data)
    collect_inspiration(connection, data, options.scope == 'workspace')
    collect_analyses(connection, data, options.scope == 'workspace')
    return complete_configuration(connection, options, data)


def complete_configuration(connection, options, data):
    primary = primary_id(connection)
    if options.scope == "story":
        primary = decode(data["stories"][0]["settings"]).get("primary_profile_id") or primary
    profiles = many(connection, "SELECT id FROM profiles") if options.scope == "workspace" else []
    profile_ids = {row["id"] for row in profiles} | referenced_profiles(data, primary) | writing_profiles(data) | preset_profiles(data)
    data["profiles"] = related_rows(connection, "profiles", "id", profile_ids)
    data["profile_versions"] = related_rows(connection, "profile_versions", "profile_id", profile_ids)
    prompt_heads = collect_configuration(connection, data, options.scope)
    redact_profiles(data)
    collect_identities(connection, data)
    branches = {row["id"]: row for row in data["branches"]}
    require(not options.branch_id or options.branch_id in branches, "The selected path is outside this archive.")
    preferred = [row for row in branches.values() if row["story_id"] == options.story_id]
    selected = branches.get(options.branch_id) or next(iter(preferred or branches.values()), None)
    return {"format": "roleplay-archive", "version": ARCHIVE_VERSION, "scope": options.scope, "created_at": now(),
            "title": data["stories"][0]["title"] if options.scope == "story" else "Workspace backup",
            "include_sidebar": options.include_sidebar, "primary_profile_id": primary,
            "selection": {"storyId": selected["story_id"], "branchId": selected["id"]} if selected else {},
            "prompt_heads": prompt_heads,
            "authoring_profiles": defaults(connection) if options.scope == "workspace" else {},
            "data": data}
