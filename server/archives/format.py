import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from server.models import Input

ARCHIVE_VERSION = 37
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
V1_TABLES = (
    "stories", "assets", "asset_versions", "manifests", "branches", "nodes", "adoptions",
    "profiles", "profile_versions", "prompt_versions", "roll_tables", "roll_table_versions",
    "generations", "candidates", "generation_attempts", "node_mechanics", "mechanic_opportunities",
    "review_runs", "review_jobs", "review_attempts", "side_threads", "side_turns", "side_replies",
)
SCENE_TABLES = ("scene_runs", "scene_jobs", "scene_attempts", "scene_decisions")
V8_TABLES = V1_TABLES + SCENE_TABLES + ('continuity_commits',)
ASSESSMENT_TABLES = ('assessment_runs', 'assessment_jobs', 'assessment_attempts')
V9_TABLES = V8_TABLES + ASSESSMENT_TABLES
BACKGROUND_TABLES = ('background_states', 'branch_background', 'node_background')
V10_TABLES = V9_TABLES + BACKGROUND_TABLES
INTERPRETATION_TABLES = ('background_runs', 'background_jobs', 'background_attempts')
V11_TABLES = V10_TABLES + INTERPRETATION_TABLES
V12_TABLES = V11_TABLES + ('asset_sources',)
IMPORT_TABLES = ('library_imports', 'asset_import_origins')
V15_TABLES = V12_TABLES + IMPORT_TABLES
AUTHORING_TABLES = ('authoring_runs', 'authoring_jobs', 'authoring_attempts')
V17_TABLES = V15_TABLES + AUTHORING_TABLES
V20_TABLES = V17_TABLES + ('library_media',)
SUMMARY_TABLES = ('summary_runs', 'summary_jobs', 'summary_attempts', 'summary_versions')
V21_TABLES = V20_TABLES + SUMMARY_TABLES
MAINTENANCE_TABLES = ('summary_pending', 'summary_wakeups', 'summary_batches', 'summary_batch_runs')
V22_TABLES = V21_TABLES + MAINTENANCE_TABLES
CONTROL_TABLES = ('memory_control_versions', 'branch_memory_controls')
V27_TABLES = V22_TABLES + CONTROL_TABLES
V29_TABLES = V27_TABLES + ('archive_identities',)
PLAN_TABLES = ('continuity_edits', 'branch_continuity_edits')
V30_TABLES = V29_TABLES + PLAN_TABLES
V31_TABLES = V30_TABLES + ('candidate_activity', 'path_revisions')
CLEANUP_TABLES = ('branch_cleanup_settings', 'candidate_cleanups')
V32_TABLES = V31_TABLES + CLEANUP_TABLES
V33_TABLES = V32_TABLES + ('branch_cleanup_timing',)
RELATIONSHIP_TABLES = ('relationship_jobs', 'relationship_attempts')
V36_TABLES = V33_TABLES + RELATIONSHIP_TABLES
TABLES = V36_TABLES + ('manuscripts',)
JSON_FIELDS = {
    'relationship_jobs': ('snapshot', 'result', 'usage'), 'relationship_attempts': ('result', 'usage'),
    'candidate_cleanups': ('snapshot', 'usage', 'edits'),
    'manuscripts': ('document',),
    'continuity_edits': ('changes',),
    'memory_control_versions': ('payload',),
    'summary_batches': ('snapshot',),
    'summary_runs': ('snapshot',), 'summary_jobs': ('snapshot', 'result', 'usage'),
    'summary_attempts': ('result', 'usage'), 'summary_versions': ('result',),
    'authoring_runs': ('snapshot',), 'authoring_jobs': ('snapshot', 'result', 'usage'),
    'authoring_attempts': ('result', 'usage'),
    'library_imports': ('conversion',),
    "stories": ("settings",), "asset_versions": ("content",), "manifests": ("attachments",),
    "nodes": ("metadata",), "profile_versions": ("config",), "roll_table_versions": ("definition",),
    "generations": ("snapshot",), "candidates": ("profile", "usage"), "generation_attempts": ("usage",),
    "node_mechanics": ("state",), "mechanic_opportunities": ("snapshot",),
    "review_runs": ("snapshot", "selections"), "review_jobs": ("snapshot", "result", "usage"),
    "review_attempts": ("result", "usage"), "side_turns": ("snapshot",),
    "side_replies": ("profile", "usage", "coverage"),
    "scene_runs": ("snapshot", "state"), "scene_jobs": ("snapshot", "result", "usage"),
    "scene_attempts": ("result", "usage"), "scene_decisions": ("payload",),
    'continuity_commits': ('changes',),
    'assessment_runs': ('snapshot',), 'assessment_jobs': ('snapshot', 'result', 'usage'),
    'assessment_attempts': ('result', 'usage'),
    'background_states': ('snapshot',),
    'background_runs': ('snapshot',), 'background_jobs': ('snapshot', 'result', 'usage'),
    'background_attempts': ('result', 'usage'),
}


class ArchiveDocument(Input):
    format: Literal["roleplay-archive"] = "roleplay-archive"
    version: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37] = ARCHIVE_VERSION
    scope: Literal["story", "workspace"]
    title: str = Field(min_length=1, max_length=200)
    created_at: str
    include_sidebar: bool
    selection: dict[str, str] = Field(default_factory=dict)
    primary_profile_id: str | None = None
    authoring_profiles: dict[str, str] = Field(default_factory=dict)
    prompt_heads: dict[str, str]
    data: dict[str, list[dict]]
    library_drafts: dict[str, Annotated[str, StringConstraints(strip_whitespace=False)] | None] = Field(default_factory=dict)
    lore_drafts: dict[str, dict[str, Annotated[str, StringConstraints(strip_whitespace=False)] | None]] = Field(default_factory=dict)


class ArchiveCreate(Input):
    scope: Literal["story", "workspace"]
    story_id: str | None = None
    branch_id: str | None = None
    include_sidebar: bool = False


class ArchiveUpload(Input):
    content: str = Field(min_length=1, max_length=MAX_ARCHIVE_BYTES)


class ArchiveRestore(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    sha256: str = Field(min_length=64, max_length=64)


def canonical(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def summary(document):
    data = document["data"]
    return {"version": document["version"], "scope": document["scope"], "title": document["title"], "include_sidebar": document["include_sidebar"],
            "stories": [{"id": story["id"], "title": story["title"], "archived": bool(story["archived"])}
                        for story in data["stories"]],
            "counts": {key: len(rows) for key, rows in data.items()}, "selection": document["selection"],
            "running_jobs": sum(row["status"] in {"running", "queued", "cleaning"}
                                for key in ("candidates", "review_jobs", "side_replies", "scene_jobs", "assessment_jobs", 'background_jobs', 'authoring_jobs', 'summary_jobs', 'relationship_jobs') for row in data[key])}
