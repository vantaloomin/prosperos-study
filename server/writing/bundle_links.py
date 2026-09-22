from server.database import decode, many, one
from server.errors import require
from server.writing.resources import version


def local_options(connection):
    models = many(connection, 'SELECT p.id,v.id AS version_id,v.name FROM profiles p '
                  'JOIN profile_versions v ON v.id=p.latest_version_id ORDER BY v.name,p.id')
    tables = many(connection, 'SELECT id,table_id,number,definition FROM roll_table_versions ORDER BY table_id,number DESC')
    styles = many(connection, "SELECT v.id,v.name,v.number FROM writing_versions v JOIN writing_assets a "
                  "ON a.id=v.asset_id WHERE a.kind='style' AND a.archived=0 ORDER BY v.name,v.number DESC")
    return {'model': models, 'style': styles,
            'table': [{key: row[key] for key in ('id', 'table_id', 'number')}
                      | {'name': decode(row['definition'])['name']} for row in tables]}


def resolve_mapping(connection, reference, identity):
    if reference.kind == 'model':
        if identity is None:
            return None, 'Story / workspace task default', None
        row = one(connection, 'SELECT p.id,v.id AS version_id,v.name FROM profiles p '
                  'JOIN profile_versions v ON v.id=p.latest_version_id WHERE p.id=?', (identity,))
        return identity, row['name'], row['version_id']
    if reference.kind == 'style':
        if identity is None:
            return 'none', 'No style profile', None
        row = version(connection, identity, 'style')
        require(not row['archived'], 'Unarchive the selected style before mapping it.')
        return identity, f"{row['name']} · v{row['number']}", identity
    require(reference.table_id, 'A table mapping needs its table identifier.')
    if identity is None:
        identity = one(connection, 'SELECT version_id FROM roll_tables WHERE id=?', (reference.table_id,))['version_id']
    row = one(connection, 'SELECT * FROM roll_table_versions WHERE id=?', (identity,))
    require(row['table_id'] == reference.table_id, 'A mapped table version belongs to a different table.')
    return identity, f"{decode(row['definition'])['name']} · v{row['number']}", identity


def dependency_slots(items, references):
    resources = {item['key']: item for item in items}
    used = set()
    for item in items:
        if item['kind'] != 'recipe':
            continue
        content = item['content']
        style = content['style']
        if style in resources:
            require(resources[style]['kind'] == 'style', 'A recipe needs a style resource, not another recipe.')
        elif style not in {'none', 'inherit'}:
            check_reference(style, 'style', references, used)
        for step in content['steps']:
            if step['profile_id']:
                check_reference(step['profile_id'], 'model', references, used)
        for table, key in (content.get('randomness') or {}).get('table_versions', {}).items():
            check_reference(key, 'table', references, used)
            require(references[key].table_id == table, 'A table slot names a different table.')
    require(used == set(references), 'Bundle references must be used by a resource.')


def check_reference(key, kind, references, used):
    require(key in references and references[key].kind == kind, f'A {kind} dependency has no matching mapping slot.')
    used.add(key)


def map_content(item, mappings, resource_ids):
    from copy import deepcopy
    content = deepcopy(item['content'])
    if item['kind'] != 'recipe':
        return content
    style = content['style']
    content['style'] = resource_ids.get(style, mappings.get(style, style))
    for step in content['steps']:
        if step['profile_id']:
            step['profile_id'] = mappings[step['profile_id']]
    if content.get('randomness'):
        content['randomness']['table_versions'] = {
            key: mappings[value] for key, value in content['randomness'].get('table_versions', {}).items()}
    return content
