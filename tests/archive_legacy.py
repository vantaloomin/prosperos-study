from server.archives.format import (
    ASSESSMENT_TABLES,
    AUTHORING_TABLES,
    BACKGROUND_TABLES,
    CONTROL_TABLES,
    INTERPRETATION_TABLES,
    MAINTENANCE_TABLES,
    SUMMARY_TABLES,
)


def remove_interpretations(document):
    remove_authoring(document)
    for table in INTERPRETATION_TABLES:
        assert document['data'].pop(table) == []
    document['prompt_heads'].pop('background-interpretation')
    document['data']['prompt_versions'] = [row for row in document['data']['prompt_versions'] if row['key'] != 'background-interpretation']


def remove_assessments(document):
    remove_interpretations(document)
    for table in ASSESSMENT_TABLES + BACKGROUND_TABLES:
        assert document['data'][table] == []
        del document['data'][table]
    document['prompt_heads'].pop('beat-assessment')
    document['data']['prompt_versions'] = [row for row in document['data']['prompt_versions'] if row['key'] != 'beat-assessment']


def remove_authoring(document):
    remove_summaries(document)
    assert document['data'].pop('library_media') == []
    for table in AUTHORING_TABLES:
        assert document['data'].pop(table) == []
    keys = {'authoring-draft', 'authoring-critique', 'authoring-tighten', 'authoring-enrich'}
    for key in keys:
        document['prompt_heads'].pop(key)
    document['data']['prompt_versions'] = [row for row in document['data']['prompt_versions'] if row['key'] not in keys]
    document.pop('authoring_profiles', None)


def remove_summaries(document):
    remove_maintenance(document)
    for table in SUMMARY_TABLES:
        assert document['data'].pop(table) == []
    document['prompt_heads'].pop('memory-summary')
    document['data']['prompt_versions'] = [row for row in document['data']['prompt_versions'] if row['key'] != 'memory-summary']


def remove_maintenance(document):
    remove_controls(document)
    for table in MAINTENANCE_TABLES:
        assert document['data'].pop(table) == []


def remove_controls(document):
    remove_v061_records(document)
    for table in ('continuity_edits', 'branch_continuity_edits'):
        assert document['data'].pop(table) == []
    assert document['data'].pop('archive_identities') == []
    for table in CONTROL_TABLES:
        assert document['data'].pop(table) == []


def remove_v061_records(document):
    remove_v062_prompts(document)
    # Reconstruct the exact older format, which had no activity or omission rows.
    document['data'].pop('candidate_activity')
    assert document['data'].pop('path_revisions') == []


def remove_v062_prompts(document):
    from server.database import decode, encode
    from server.prompts import LEGACY_PROMPT_LABELS
    keys = set(document['prompt_heads']) - set(LEGACY_PROMPT_LABELS)
    for key in keys:
        document['prompt_heads'].pop(key)
    document['data']['prompt_versions'] = [row for row in document['data']['prompt_versions'] if row['key'] not in keys]
    for story in document['data']['stories']:
        settings = decode(story['settings'])
        if 'prompt_versions' in settings:
            settings['prompt_versions'] = {key: value for key, value in settings['prompt_versions'].items() if key not in keys}
        story['settings'] = encode(settings)
