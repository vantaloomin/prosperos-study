from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.memory.control_models import ControlSave
from server.memory.control_sources import (
    available_sources,
    characters,
    library_sources,
    pinned_items,
)
from server.memory.control_state import control_head, control_view
from server.operations import previous, remember
from server.stories import check_revision


def prepare_controls(connection, branch, body):
    needed = {source_id for entry in body.entries for source_id in entry.source_ids}
    sources = {source['id']: source for source in available_sources(connection, branch, include_library=any(key.startswith('version:') for key in needed)) if source['id'] in needed}
    require(needed <= sources.keys(), 'Some evidence is outside this accepted path or pinned edition. Refresh the source selection.', 409)
    character_ids = {item['id'] for item in characters(pinned_items(connection, branch))} if any(entry.character_id for entry in body.entries) else set()
    require(all(not entry.character_id or entry.character_id in character_ids for entry in body.entries),
            'A selected Character is no longer enabled in this Story. Refresh the character selection.', 409)
    require(all(entry.kind == 'knowledge' or all('node_id' in sources[key] for key in entry.source_ids) for entry in body.entries),
            'Canon and Character grants currently belong to character knowledge decisions only.', 409)
    payload = {'entries': [{**entry.model_dump(exclude={'source_ids'}, exclude_none=True), 'sources': [sources[key] for key in entry.source_ids]}
                           for entry in body.entries]}
    if any(entry.character_id for entry in body.entries) or any('version_id' in source for source in sources.values()):
        payload['manifest_id'] = branch['manifest_id']
    return payload


class Controls:
    def __init__(self, database):
        self.database = database

    def view(self, branch_id):
        with self.database.connect() as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            return {**control_view(connection, branch), 'revision': branch['revision'],
                    'characters': characters(pinned_items(connection, branch))}

    def sources(self, branch_id, category='prose', offset=0):
        with self.database.connect() as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            sources = list(library_sources(pinned_items(connection, branch))) if category == 'library' else available_sources(connection, branch)
            return {'items': sources[offset:offset + 12], 'matches': len(sources), 'revision': branch['revision'],
                    'next_offset': offset + 12 if offset + 12 < len(sources) else None}

    def save(self, branch_id, body: ControlSave):
        payload = {'branch_id': branch_id, **body.model_dump(), 'entries': [entry.model_dump(exclude_none=True) for entry in body.entries]}
        with self.database.connect() as connection:
            cached = previous(connection, body.operation_id, 'memory-controls', payload)
            if cached is not None:
                return cached
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            check_revision(branch, body.expected_revision)
            require(branch['head_id'] is not None, 'Add accepted prose before recording source-backed author decisions.', 409)
            prepared = prepare_controls(connection, branch, body)
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'memory-controls', payload)
            if cached is not None:
                return cached
            require(branch == one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,)), 'The path changed. Review the evidence again.', 409)
            current = control_head(connection, branch_id)
            require(current == body.expected_version_id, 'Author decisions changed in another view. Reopen them before saving.', 409)
            version_id = identifier()
            connection.execute('INSERT INTO memory_control_versions VALUES (?,?,?,?,?,?,?,?)',
                (version_id, branch['story_id'], branch_id, branch['head_id'], current, encode(prepared), now(), 'author'))
            connection.execute('INSERT INTO branch_memory_controls VALUES (?,?) ON CONFLICT(branch_id) DO UPDATE SET version_id=excluded.version_id',
                               (branch_id, version_id))
            return remember(connection, body.operation_id, 'memory-controls', payload, {'id': version_id})

    def history(self, branch_id, offset=0):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM branches WHERE id=?', (branch_id,))
            return many(connection, 'WITH RECURSIVE versions AS (SELECT v.*,0 AS depth FROM memory_control_versions v WHERE id=? '
                'UNION ALL SELECT v.*,p.depth+1 FROM memory_control_versions v JOIN versions p ON v.id=p.parent_id) '
                'SELECT id,branch_id,node_id,created_at FROM versions ORDER BY depth LIMIT 25 OFFSET ?', (control_head(connection, branch_id), offset))

    def version(self, branch_id, version_id):
        with self.database.connect() as connection:
            row = connection.execute('WITH RECURSIVE versions AS (SELECT v.* FROM memory_control_versions v WHERE id=? '
                'UNION ALL SELECT v.* FROM memory_control_versions v JOIN versions p ON v.id=p.parent_id) '
                'SELECT * FROM versions WHERE id=?', (control_head(connection, branch_id), version_id)).fetchone()
            require(row is not None, 'This author decision version is outside the selected branch history.', 404)
            return {**dict(row), 'payload': decode(row['payload'])}
