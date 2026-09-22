"""Manuscript references and frozen prompt sections survive independent restore."""
from server.agent_templates import validate_agent_settings
from server.archives.format import JSON_FIELDS
from server.database import decode, one
from server.errors import require
from server.manuscript.models import ManuscriptDocument
from server.manuscript.service import validate_document
from server.prompt_sections import SECTION_ROLES
from server.roles import role_key
from server.section_prompts import SECTION_LABELS


def validate_v07(connection, data):
    for story in data['stories']:
        validate_agent_settings(decode(story['settings']))
    for row in data['manuscripts']:
        require(row['revision'] >= 0, 'A manuscript has an invalid revision.')
        validate_document(connection, row['story_id'], ManuscriptDocument.model_validate(decode(row['document'])))
    for table, columns in JSON_FIELDS.items():
        if 'snapshot' in columns and table != 'recipe_jobs':
            for row in data[table]:
                validate_sections(connection, decode(row['snapshot']))


def validate_sections(connection, snapshot):
    if 'writer_snapshot' in snapshot:
        validate_sections(connection, snapshot['writer_snapshot'])
    sections = snapshot.get('prompt_sections', [])
    require(isinstance(sections, list) and len(sections) in {0, 2}, 'Invalid mode-guidance sections.')
    if not sections:
        return
    require(role_key(snapshot['prompt']['key']) in SECTION_ROLES, 'This role must not receive mode-guidance sections.')
    require(sections[0]['key'] in {'section:mode-active', 'section:mode-passive'}
            and sections[1]['key'] in {'section:agency-reserved', 'section:agency-shared'}, 'Mode guidance is out of order.')
    for section in sections:
        require(set(section) == {'id', 'key', 'template', 'user_character'}
                and isinstance(section['user_character'], str) and len(section['user_character']) <= 200,
                'Invalid character identity in mode guidance.')
        row = one(connection, 'SELECT * FROM prompt_versions WHERE id=?', (section['id'],))
        require(row['key'] == section['key'] and row['key'] in SECTION_LABELS
                and section['template'] == row['template'].replace('{user_character}', section['user_character']),
                'Mode guidance differs from its recorded prompt version.')


def remap_manuscript(document, mapping):
    # Chapter and scene IDs belong to this manuscript only. Only Story links need remapping.
    def scene(item):
        return {**item, **{key: mapping[item[key]] for key in ('branch_id', 'head_id', 'from_node_id', 'through_node_id')}}
    return {**document,
            'chapters': [{**chapter, 'scenes': [scene(item) for item in chapter['scenes']]} for chapter in document['chapters']],
            'bookmarks': [{**item, 'node_id': mapping[item['node_id']]} for item in document['bookmarks']]}
