"""Portable resources use local mapping slots instead of connection configuration."""
from copy import deepcopy

from server.database import decode, one
from server.writing.extras import portable_metadata
from server.writing.resources import version


def export_bundle(connection, version_id, include_samples=False):
    root = version(connection, version_id)
    resources = [root]
    if root['kind'] == 'recipe' and root['content']['style'] not in {'none', 'inherit'}:
        resources.append(version(connection, root['content']['style'], 'style'))
    keys = {item['id']: f'resource-{index + 1}' for index, item in enumerate(resources)}
    slots, references, exported, omitted = {}, [], [], 0
    for item in resources:
        content = deepcopy(item['content'])
        if item['kind'] == 'style' and not include_samples:
            omitted += len(content['examples'])
            content['examples'] = []
        if item['kind'] == 'recipe':
            content['style'] = keys.get(content['style'], content['style'])
            for step in content['steps']:
                if step['profile_id']:
                    step['profile_id'] = reference_slot(connection, 'model', step['profile_id'], slots, references)
            for key, identity in (content.get('randomness') or {}).get('table_versions', {}).items():
                content['randomness']['table_versions'][key] = reference_slot(connection, 'table', identity, slots, references)
        extras = {key: value for key, value in item['unsupported'].items()
                  if include_samples or not key.startswith('content.examples[')}
        exported.append({key: item[key] for key in ('kind', 'name', 'description', 'note')}
                        | {'key': keys[item['id']], 'content': content, 'unsupported': portable_metadata(extras)})
    return {'format': 'prospero-writing-bundle', 'version': 1, 'root': keys[root['id']],
            'resources': exported, 'references': references, 'omitted_samples': omitted}


def reference_slot(connection, kind, identity, slots, references):
    if (kind, identity) in slots:
        return slots[kind, identity]
    key = f'{kind}-{len(slots) + 1}'
    slots[kind, identity] = key
    if kind == 'model':
        row = one(connection, 'SELECT v.name FROM profiles p JOIN profile_versions v ON v.id=p.latest_version_id '
                  'WHERE p.id=?', (identity,))
        reference = {'key': key, 'kind': kind, 'name': row['name']}
    else:
        row = one(connection, 'SELECT * FROM roll_table_versions WHERE id=?', (identity,))
        reference = {'key': key, 'kind': kind, 'name': decode(row['definition'])['name'], 'table_id': row['table_id']}
    references.append(reference)
    return key
