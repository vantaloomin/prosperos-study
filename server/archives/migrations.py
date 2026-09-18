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
from server.memory.summary_catalog import SUMMARY_KEYS
from server.prompts import DEFAULT_PROMPTS, PROMPT_LABELS
from server.scenes.catalog import DRAFT_KEYS, PLAN_KEYS, SCENE_PROMPTS
from server.scenes.continuity_catalog import CONTINUITY_KEYS
from server.scenes.patch_catalog import PATCH_KEYS
from server.scenes.revision_catalog import REVISION_KEYS

ENRICHMENT_KEYS = {'authoring-enrich'}
LEGACY_PROMPTS = set(PROMPT_LABELS) - {'beat-assessment', 'background-interpretation'} - AUTHORING_KEYS - SUMMARY_KEYS

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
        require(set(document['prompt_heads']) == set(PROMPT_LABELS) - AUTHORING_KEYS - SUMMARY_KEYS, 'Version 15 needs its original prompts.')
        require(not document['authoring_profiles'], 'Version 15 cannot contain Library assistant defaults.')
        document['data'].update({table: [] for table in AUTHORING_TABLES})
        add_prompts(document, sorted(AUTHORING_KEYS - ENRICHMENT_KEYS), 15)
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
    return upgrade_nineteen(document)


def upgrade_nineteen(document):
    if document['version'] == 19:
        require(set(document['prompt_heads']) == set(PROMPT_LABELS) - ENRICHMENT_KEYS - SUMMARY_KEYS, 'Version 19 needs its original supported prompts.')
        require(not ENRICHMENT_KEYS.intersection(document['authoring_profiles']), 'Version 19 cannot contain enrichment defaults.')
        add_prompts(document, sorted(ENRICHMENT_KEYS), 19)
        document['version'] = 20
    return upgrade_twenty(document)


def upgrade_twenty(document):
    from server.archives.format import SUMMARY_TABLES, V20_TABLES
    if document['version'] == 20:
        require(set(document['data']) == set(V20_TABLES), 'Version 20 needs its original record groups.')
        require(set(document['prompt_heads']) == set(PROMPT_LABELS) - SUMMARY_KEYS, 'Version 20 needs its original prompts.')
        document['data'].update({table: [] for table in SUMMARY_TABLES})
        add_prompts(document, sorted(SUMMARY_KEYS), 20)
        document['version'] = 21
    return upgrade_twenty_one(document)


def upgrade_twenty_one(document):
    from server.archives.format import MAINTENANCE_TABLES, V21_TABLES
    if document['version'] == 21:
        require(set(document['data']) == set(V21_TABLES), 'Version 21 needs its original record groups.')
        document['data'].update({table: [] for table in MAINTENANCE_TABLES})
        document['version'] = 22
    return upgrade_twenty_two(document)


def upgrade_twenty_two(document):
    from server.archives.format import CONTROL_TABLES, V22_TABLES, V27_TABLES
    if document['version'] == 22:
        require(set(document['data']) == set(V22_TABLES), 'Version 22 needs its original record groups.')
        document['data'].update({table: [] for table in CONTROL_TABLES})
        document['version'] = 23
    if document['version'] == 23:
        document['version'] = 24
    if document['version'] == 24:
        document['version'] = 25
    if document['version'] == 25:
        document['version'] = 26
    if document['version'] == 26:
        document['version'] = 27
    if document['version'] == 27:
        require(set(document['data']) == set(V27_TABLES), 'Version 27 needs its original record groups.')
        document['data']['archive_identities'] = []
        document['version'] = 28
    return upgrade_twenty_eight(document)


def upgrade_twenty_eight(document):
    if document['version'] == 28:
        # Plans extend continuity JSON; legacy records and frozen inputs stay untouched.
        document['version'] = 29
    if document['version'] == 29:
        from server.archives.format import PLAN_TABLES, V29_TABLES
        require(set(document['data']) == set(V29_TABLES), 'Version 29 needs its original record groups.')
        document['data'].update({table: [] for table in PLAN_TABLES})
        document['version'] = 30
    if document['version'] == 30:
        from server.archives.format import V30_TABLES
        require(set(document['data']) == set(V30_TABLES), 'Version 30 needs its original record groups.')
        document['data']['candidate_activity'] = []
        document['data']['path_revisions'] = []
        document['version'] = 31
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
