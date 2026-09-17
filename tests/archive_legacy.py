from server.archives.format import (
    ASSESSMENT_TABLES,
    AUTHORING_TABLES,
    BACKGROUND_TABLES,
    INTERPRETATION_TABLES,
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
    assert document['data'].pop('library_media') == []
    for table in AUTHORING_TABLES:
        assert document['data'].pop(table) == []
    keys = {'authoring-draft', 'authoring-critique', 'authoring-tighten'}
    for key in keys:
        document['prompt_heads'].pop(key)
    document['data']['prompt_versions'] = [row for row in document['data']['prompt_versions'] if row['key'] not in keys]
    document.pop('authoring_profiles', None)
