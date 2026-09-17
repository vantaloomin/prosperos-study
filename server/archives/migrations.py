"""Deterministic in-memory upgrades leave the user's original backup untouched."""
from server.archives.format import (
    ASSESSMENT_TABLES,
    BACKGROUND_TABLES,
    INTERPRETATION_TABLES,
    SCENE_TABLES,
    V1_TABLES,
    V8_TABLES,
    V9_TABLES,
    V10_TABLES,
)
from server.authoring.catalog import AUTHORING_KEYS
from server.errors import require
from server.library_formats.sources import source_record
from server.prompts import DEFAULT_PROMPTS, PROMPT_LABELS
from server.scenes.catalog import DRAFT_KEYS, PLAN_KEYS, SCENE_PROMPTS
from server.scenes.continuity_catalog import CONTINUITY_KEYS
from server.scenes.patch_catalog import PATCH_KEYS
from server.scenes.revision_catalog import REVISION_KEYS

LEGACY_PROMPTS = set(PROMPT_LABELS) - {'beat-assessment', 'background-interpretation'} - AUTHORING_KEYS

def upgrade(document):
    if document["version"] == 1:
        upgrade_one(document)
    if document["version"] == 2:
        upgrade_two(document)
    if document["version"] == 3:
        document["version"] = 4
    if document['version'] == 4:
        require(set(document['prompt_heads']) == LEGACY_PROMPTS - set(REVISION_KEYS) - set(PATCH_KEYS) - set(CONTINUITY_KEYS),
                'Version 4 needs its original supported prompts.')
        add_prompts(document, REVISION_KEYS, 4)
        document['version'] = 5
    if document['version'] == 5:
        require(set(document['prompt_heads']) == LEGACY_PROMPTS - set(PATCH_KEYS) - set(CONTINUITY_KEYS),
                'Version 5 needs its original supported prompts.')
        add_prompts(document, PATCH_KEYS, 5)
        document['version'] = 6
    if document['version'] == 6:
        require(set(document['data']) == set(V8_TABLES) - {'continuity_commits'}, 'Version 6 needs its original record groups.')
        require(set(document['prompt_heads']) == LEGACY_PROMPTS - set(CONTINUITY_KEYS), 'Version 6 needs its original supported prompts.')
        document['data']['continuity_commits'] = []
        add_prompts(document, CONTINUITY_KEYS, 6)
        document['version'] = 7
    if document['version'] == 7:
        document['version'] = 8
    if document['version'] == 8:
        require(set(document['data']) == set(V8_TABLES), 'Version 8 needs its original record groups.')
        require(set(document['prompt_heads']) == LEGACY_PROMPTS, 'Version 8 needs its original supported prompts.')
        add_prompts(document, ['beat-assessment'], 8)
        document['data'].update({table: [] for table in ASSESSMENT_TABLES})
        document['version'] = 9
    return upgrade_nine(document)


def upgrade_nine(document):
    if document['version'] == 9:
        require(set(document['data']) == set(V9_TABLES), 'Version 9 needs its original record groups.')
        document['data'].update({table: [] for table in BACKGROUND_TABLES})
        document['version'] = 10
    return upgrade_ten(document)


def upgrade_ten(document):
    if document['version'] == 10:
        require(set(document['data']) == set(V10_TABLES), 'Version 10 needs its original record groups.')
        require(set(document['prompt_heads']) == LEGACY_PROMPTS | {'beat-assessment'}, 'Version 10 needs its original prompts.')
        document['data'].update({table: [] for table in INTERPRETATION_TABLES})
        add_prompts(document, ['background-interpretation'], 10)
        document['version'] = 11
    return upgrade_eleven(document)


def upgrade_eleven(document):
    from server.archives.format import V11_TABLES
    from server.archives.library_sources import lore_versions
    if document['version'] == 11:
        require(set(document['data']) == set(V11_TABLES), 'Version 11 needs its original record groups.')
        require(not document.get('library_drafts'), 'Legacy archives cannot contain Markdown working files.')
        document['data']['asset_sources'] = [source_record(row) for row in lore_versions(document['data'])]
        document['version'] = 12
    return upgrade_twelve(document)


def upgrade_twelve(document):
    from server.archives.format import IMPORT_TABLES, V12_TABLES
    if document['version'] == 12:
        require(set(document['data']) == set(V12_TABLES), 'Version 12 needs its original record groups.')
        document['data'].update({table: [] for table in IMPORT_TABLES})
        document['version'] = 13
    return upgrade_thirteen(document)


def upgrade_thirteen(document):
    if document['version'] == 13:
        require(not document.get('lore_drafts'), 'Version 13 cannot contain entry working-file drafts.')
        document['lore_drafts'] = {}
        document['version'] = 14
    if document['version'] == 14:
        document['version'] = 15
    return upgrade_fifteen(document)


def upgrade_fifteen(document):
    from server.archives.format import AUTHORING_TABLES, V15_TABLES
    if document['version'] == 15:
        require(set(document['data']) == set(V15_TABLES), 'Version 15 needs its original record groups.')
        require(set(document['prompt_heads']) == set(PROMPT_LABELS) - AUTHORING_KEYS, 'Version 15 needs its original prompts.')
        require(not document['authoring_profiles'], 'Version 15 cannot contain Library assistant defaults.')
        document['data'].update({table: [] for table in AUTHORING_TABLES})
        add_prompts(document, sorted(AUTHORING_KEYS), 15)
        document['version'] = 16
    return upgrade_sixteen(document)


def upgrade_sixteen(document):
    if document['version'] == 16:
        require(all(row['kind'] in ('character', 'lorebook') for row in document['data']['assets']),
                'Version 16 cannot contain persona assets.')
        document['version'] = 17
    return upgrade_seventeen(document)


def upgrade_seventeen(document):
    from server.archives.format import V17_TABLES
    if document['version'] == 17:
        require(set(document['data']) == set(V17_TABLES), 'Version 17 needs its original record groups.')
        document['data']['library_media'] = []
        document['version'] = 18
    if document['version'] == 18:
        document['version'] = 19
    return document


def add_prompts(document, keys, source_version):
    for key in keys:
        version_id = f"{key}-archive-upgrade-v{source_version}"
        document["data"]["prompt_versions"].append({"id": version_id, "key": key, "number": 1,
                                                     "template": DEFAULT_PROMPTS[key], "created_at": document["created_at"]})
        document["prompt_heads"][key] = version_id


def upgrade_one(document):
    require(set(document["data"]) == set(V1_TABLES), "This archive's record groups do not match format version 1.")
    legacy_keys = LEGACY_PROMPTS - set(SCENE_PROMPTS)
    require(set(document["prompt_heads"]) == legacy_keys, "Version 1 needs its original supported prompts.")
    add_prompts(document, PLAN_KEYS, 1)
    document["data"].update({table: [] for table in SCENE_TABLES})
    document["version"] = 2


def upgrade_two(document):
    require(set(document["data"]) == set(V8_TABLES) - {'continuity_commits'}, "This archive's record groups do not match format version 2.")
    require(set(document["prompt_heads"]) == LEGACY_PROMPTS - set(DRAFT_KEYS) - set(REVISION_KEYS) - set(PATCH_KEYS) - set(CONTINUITY_KEYS),
            "Version 2 needs its original supported prompts.")
    add_prompts(document, DRAFT_KEYS, 2)
    document["version"] = 3
