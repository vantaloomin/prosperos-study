"""Writing-resource links are live metadata; saved model input strings stay frozen."""
from server.archives.records import related_rows
from server.archives.text_edit_versions import version_references
from server.archives.writing_requests import validate_requests
from server.database import decode, encode, many
from server.errors import require
from server.writing.extras import validate_extras
from server.writing.resources import parse_content, validate_links, version


def collect_writing(connection, data, complete):
    collect_resources(connection, data, complete)
    data['writing_extras'] = related_rows(connection, 'writing_extras', 'version_id',
                                         {row['id'] for row in data['writing_versions']})


def collect_resources(connection, data, complete):
    data['writing_pins'] = related_rows(connection, 'writing_pins', 'story_id',
                                      {row['id'] for row in data['stories']})
    if complete:
        data['writing_assets'] = many(connection, 'SELECT * FROM writing_assets ORDER BY rowid')
        data['writing_versions'] = many(connection, 'SELECT * FROM writing_versions ORDER BY rowid')
        return
    pending = {value for row in data['writing_pins']
               for value in (row['style_version_id'], row['recipe_version_id']) if value}
    pending.update(snapshot_references(data))
    pending.update(version_references(data, 'writing-field'))
    seen = set()
    while pending:
        selected = [version(connection, identity) for identity in sorted(pending)]
        assets = {item['asset_id'] for item in selected} - seen
        if not assets:
            break
        seen.update(assets)
        data['writing_assets'].extend(related_rows(connection, 'writing_assets', 'id', assets))
        versions = related_rows(connection, 'writing_versions', 'asset_id', assets)
        data['writing_versions'].extend(versions)
        kinds = {item['id']: item['kind'] for item in data['writing_assets']}
        pending = {decode(row['content'])['style'] for row in versions
                   if kinds[row['asset_id']] == 'recipe'} - {'none', 'inherit'}


def snapshot_references(data):
    from server.archives.format import JSON_FIELDS
    result = set()
    for table, fields in JSON_FIELDS.items():
        if 'snapshot' in fields:
            for row in data[table]:
                snapshot = decode(row['snapshot'])
                bindings = decode(row['bindings']) if table == 'recipe_runs' else {}
                result.update(bindings.get(value, value) for value in snapshot.get('writing_versions', []))
                result.update(snapshot.get('writer_snapshot', {}).get('writing_versions', []))
    return result


def recipe_contents(data):
    kinds = {row['id']: row['kind'] for row in data['writing_assets']}
    return [decode(row['content']) for row in data['writing_versions'] if kinds[row['asset_id']] == 'recipe']


def referenced_profiles(data):
    return {step['profile_id'] for content in recipe_contents(data)
            for step in content['steps'] if step.get('profile_id')}


def referenced_tables(data):
    return {value for content in recipe_contents(data)
            for value in (content.get('randomness') or {}).get('table_versions', {}).values()}


def validate_writing(connection, data):
    for row in data['writing_extras']:
        validate_extras(decode(row['content']))
    assets = {row['id']: row for row in data['writing_assets']}
    for row in data['writing_versions']:
        kind = assets[row['asset_id']]['kind']
        content = decode(row['content'])
        require(parse_content(kind, content) == content, 'Writing content needs its complete supported schema.')
        require(0 < len(row['name']) <= 120 and len(row['description']) <= 2000 and len(row['note']) <= 2000,
                'Invalid writing-resource labels.')
        validate_links(connection, kind, content)
    for asset in assets.values():
        head = version(connection, asset['latest_version_id'], asset['kind'])
        require(head['asset_id'] == asset['id'], 'Writing-resource head belongs to another asset.')
    for pin in data['writing_pins']:
        for kind in ('style', 'recipe'):
            if pin[f'{kind}_version_id']:
                version(connection, pin[f'{kind}_version_id'], kind)
    require(snapshot_references(data) <= {row['id'] for row in data['writing_versions']},
            'A saved writing request references missing style or recipe versions.')
    validate_requests(connection, data)


def remap_writing(row, document, mapping):
    asset = next(item for item in document['data']['writing_assets'] if mapping[item['id']] == row['asset_id'])
    if asset['kind'] == 'style':
        return row
    content = decode(row['content'])
    content['style'] = mapping.get(content['style'], content['style'])
    content['steps'] = [{**step, 'profile_id': mapping.get(step['profile_id'], step['profile_id'])}
                        for step in content['steps']]
    randomness = content.get('randomness')
    if randomness and 'table_versions' in randomness:
        randomness['table_versions'] = {key: mapping[value] for key, value in randomness['table_versions'].items()}
    return {**row, 'content': encode(content)}


def upgrade_writing(document):
    from server.archives.format import V37_TABLES, V38_TABLES, WRITING_EXTRA_TABLES, WRITING_TABLES
    if document['version'] == 37:
        require(set(document['data']) == set(V37_TABLES), 'Version 37 needs its original record groups.')
        document['data'].update({table: [] for table in WRITING_TABLES})
        document['version'] = 38
    if document['version'] == 38:
        require(set(document['data']) == set(V38_TABLES), 'Version 38 needs its original record groups.')
        document['data'].update({table: [] for table in WRITING_EXTRA_TABLES})
        document['version'] = 39
    return document
