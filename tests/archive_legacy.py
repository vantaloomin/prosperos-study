from server.archives.format import (
    ASSESSMENT_TABLES,
    AUTHORING_TABLES,
    BACKGROUND_TABLES,
    BRANCH_TOOL_TABLES,
    CONTROL_TABLES,
    INTERPRETATION_TABLES,
    MAINTENANCE_TABLES,
    SIDE_ORGANIZATION_TABLES,
    SUMMARY_TABLES,
    TEXT_EDIT_TABLES,
    WRITING_EXTRA_TABLES,
    WRITING_TABLES,
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


def remove_v070_records(document):
    for table in ('relationship_jobs', 'relationship_attempts'):
        assert document['data'].pop(table) == []
    for table in ('branch_cleanup_settings', 'candidate_cleanups', 'branch_cleanup_timing'):
        assert document['data'].pop(table) == []


def remove_v062_prompts(document, *, keep_memory=False):
    remove_v07_records(document, keep_memory=keep_memory)
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


def remove_v07_records(document, *, keep_memory=False):
    for table in ('style_analysis_jobs', 'style_analysis_attempts', 'recipe_runs', 'recipe_jobs', 'recipe_attempts', 'recipe_results'):
        assert document['data'].pop(table) == []
    for table in WRITING_TABLES + WRITING_EXTRA_TABLES + BRANCH_TOOL_TABLES + SIDE_ORGANIZATION_TABLES + TEXT_EDIT_TABLES + ('candidate_text_heads', 'side_drafts', 'side_contexts', 'side_context_heads', 'companion_edit_origins', 'side_edit_results'):
        assert document['data'].pop(table) == []
    if not keep_memory:
        remove_v070_records(document)
    from server.database import decode, encode
    from server.section_prompts import SECTION_LABELS
    assert document['data'].pop('manuscripts') == []
    document['prompt_heads'] = {key: value for key, value in document['prompt_heads'].items() if key not in SECTION_LABELS}
    document['data']['prompt_versions'] = [row for row in document['data']['prompt_versions'] if row['key'] not in SECTION_LABELS]
    for story in document['data']['stories']:
        settings = decode(story['settings'])
        if 'prompt_versions' in settings:
            settings['prompt_versions'] = {key: value for key, value in settings['prompt_versions'].items() if key not in SECTION_LABELS}
        story['settings'] = encode(settings)
    for rows in document['data'].values():
        for row in rows:
            if 'snapshot' in row:
                snapshot = decode(row['snapshot'])
                assert not snapshot.get('prompt_sections'), 'Build historical requests with prompt_sections disabled.'
                assert not snapshot.get('writer_snapshot', {}).get('prompt_sections'), 'Build historical writer requests with prompt_sections disabled.'
