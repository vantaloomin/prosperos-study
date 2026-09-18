"""Ground optional writer retrieval descriptions in reviewed editions."""
from server.database import decode, many
from server.errors import require
from server.memory.scoped_aids import validate_aid


def validate_writer_aids(connection, scope, memory, passages):
    aids = memory.get('summary_aids', [])
    if not aids:
        return True
    require(memory['receipt_version'] >= 3 and len({aid['chunk_id'] for aid in aids}) == len(aids),
            'Writer summary aids are duplicated or use an unsupported receipt.')
    by_id = {item['id']: item for item in passages}
    versions = many(connection, 'SELECT * FROM summary_versions')
    nodes = {node['id'] for node in scope.path}
    bound = True
    for row in aids:
        item = by_id.get(row['chunk_id'])
        require(item is not None and 'adjacent_to' not in item, 'A reviewed aid refers to unselected writer evidence.')
        aid = {key: value for key, value in row.items() if key != 'chunk_id'}
        validate_aid(aid, item['text'])
        eligible = [version for version in versions if reviewed_match(connection, version, scope, item, aid, nodes)]
        require(bool(eligible), 'A writer retrieval aid differs from reviewed evidence on this path.')
        matched = any(scope.identities.matches(version['id'], aid['version_id']) for version in eligible)
        require(matched or not scope.bound, 'A writer retrieval aid claims another reviewed edition.')
        bound = bound and matched
    return bound


def reviewed_match(connection, version, scope, item, aid, nodes):
    if version['origin'] != 'reviewed' or not version['enabled'] or version['node_id'] not in nodes:
        return False
    snapshot = connection.execute('SELECT snapshot FROM summary_runs WHERE id=?', (version['run_id'],)).fetchone()
    links = decode(snapshot['snapshot'])['source_links']
    if not all(link['node_id'] in nodes for link in links):
        return False
    node_id = scope.path[item['passage_number'] - 1]['id']
    sources = {link['id'] for link in links if link['node_id'] == node_id
               and all(link[key] == item[key] for key in ('start', 'end', 'sha256'))}
    proposal = {key: value for key, value in aid.items() if key not in {'version_id', 'source_sha256'}}
    return proposal['source_id'] in sources and proposal in decode(version['result'])['items']
