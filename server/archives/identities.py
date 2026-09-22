"""Shared frozen-to-live identities; never rewrite serialized provider evidence."""
from collections import defaultdict

from server.archives.records import related_rows
from server.database import decode, many
from server.errors import require

TABLE = 'archive_identities'
GLOBAL = 'global'
CONFIGURATION = {'profiles', 'profile_versions', 'prompt_versions', 'roll_table_versions'}


def records(data):
    # Configuration heads already have live links. Only source metadata needs
    # their frozen identities; retaining every workspace head bloats restores.
    referenced = {value for row in data['nodes'] for value in decode(row.get('metadata', '{}')).values()
                  if isinstance(value, str)}
    # Recipe source versions retain original model/table identities inside frozen
    # requests after restore, even when no accepted prose names those records.
    from server.archives.writing import referenced_profiles, referenced_tables
    referenced.update(referenced_profiles(data))
    referenced.update(referenced_tables(data))
    from server.archives.text_edit_versions import version_references
    referenced.update(version_references(data, 'prompt'))
    referenced.update(value for row in data.get('recipe_runs', []) for value in decode(row['bindings']).values())
    result = {row['id']: (kind, row.get('story_id', GLOBAL) if kind == 'nodes' else GLOBAL)
              for kind, rows in data.items() if kind not in {TABLE, 'roll_tables'}
              for row in rows if 'id' in row and (kind not in CONFIGURATION or row['id'] in referenced)}
    result.update({row['operation_id']: ('adoption-operations', GLOBAL) for row in data['adoptions']})
    return result


def alias(record_id, source_id, kind, namespace):
    return {'record_id': record_id, 'source_id': source_id, 'record_kind': kind, 'source_story_id': namespace}


def restore_identities(connection, data, mapping):
    values = [alias(mapping[identity], identity, kind, namespace) for identity, (kind, namespace) in records(data).items()]
    connection.executemany('INSERT OR IGNORE INTO archive_identities VALUES (?,?,?,?)',
                           ((row['record_id'], row['source_id'], row['record_kind'], row['source_story_id']) for row in values))


def collect_identities(connection, data):
    catalog = records(data)
    existing = related_rows(connection, TABLE, 'record_id', catalog)
    # Older restores already kept an exact identity map locally. Reuse it rather
    # than guessing from repeated prose or titles; this does not mutate the DB.
    reverse = {}
    for row in many(connection, 'SELECT identity_map FROM archive_restores ORDER BY rowid'):
        inverse = {current: old for old, current in decode(row['identity_map']).items()}
        reverse.update({current: inverse for current in inverse})
    values = existing + [item for identity, (kind, namespace) in catalog.items()
                         for item in historical_aliases(identity, kind, namespace, reverse)]
    unique = {(row['record_id'], row['source_id'], row['source_story_id']): row for row in values}
    data[TABLE] = sorted(unique.values(), key=lambda row: (row['record_id'], row['source_story_id'], row['source_id']))


def historical_aliases(identity, kind, namespace, reverse):
    current, seen = identity, set()
    while current in reverse:
        require(current not in seen, 'Stored archive identity history is cyclic.')
        seen.add(current)
        mapping = reverse[current]
        current = mapping[current]
        namespace = mapping.get(namespace, namespace)
        yield alias(identity, current, kind, namespace)


def validate_identities(data):
    catalog = records(data)
    for row in data[TABLE]:
        require(set(row) == {'record_id', 'source_id', 'record_kind', 'source_story_id'},
                'An archive identity has missing or unknown fields.')
        require(all(type(value) is str and 0 < len(value) <= 200 for value in row.values()),
                'An archive source identity is invalid.')
        require(row['record_id'] in catalog and catalog[row['record_id']][0] == row['record_kind'],
                'An archive identity refers to a missing record or another record kind.')
        require(row['record_kind'] == 'nodes' or row['source_story_id'] == GLOBAL,
                'Only prose identities have a Story namespace.')
    validate_node_namespaces(data)


def validate_node_namespaces(data):
    stories = {row['id']: {row['id']} for row in data['stories']}
    for row in data[TABLE]:
        if row['record_kind'] == 'stories':
            stories[row['record_id']].add(row['source_id'])
    nodes = {row['id']: row for row in data['nodes']}
    sources, targets = defaultdict(set), defaultdict(set)
    for row in data[TABLE]:
        if row['record_kind'] != 'nodes':
            continue
        node = nodes[row['record_id']]
        namespace = row['source_story_id']
        require(namespace in stories[node['story_id']], 'A prose identity uses another Story namespace.')
        require(namespace != node['story_id'] or row['source_id'] == node['id'],
                'A prose identity changes its current Story identity.')
        sources[node['id'], namespace].add(row['source_id'])
        targets[node['story_id'], namespace, row['source_id']].add(node['id'])
    require(all(len(values) == 1 for values in [*sources.values(), *targets.values()]),
            'A prose identity is ambiguous within its original Story.')


class SourceIdentities:
    def __init__(self, connection, ids):
        self.aliases, self.namespaces = defaultdict(set), {}
        for row in related_rows(connection, TABLE, 'record_id', ids):
            self.aliases[row['record_id']].add(row['source_id'])
            if row['record_kind'] == 'nodes':
                self.namespaces[row['record_id'], row['source_story_id']] = row['source_id']

    def matches(self, live, frozen):
        return live == frozen or frozen in self.aliases.get(live, ())

    def node_id(self, node, namespace):
        if node['story_id'] == namespace:
            return node['id']
        value = self.namespaces.get((node['id'], namespace))
        require(value is not None, 'This older restored writer receipt lacks the original prose identity needed to verify its path fingerprint.')
        return value
