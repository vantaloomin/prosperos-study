"""Author-confirmed plan changes; use the continuity schema and never change prose."""
import hashlib

from pydantic import Field, model_validator

from server.branches import path_nodes
from server.continuity import continuity_view
from server.database import encode, identifier, now, one
from server.errors import DomainError, require
from server.memory.chunks import compile_chunks
from server.memory.plan_state import bind_plan_head, plan_head
from server.models import Input
from server.operations import previous, remember
from server.scenes.continuity_models import ContinuityChange, validate_change
from server.stories import check_revision


class PlanEdit(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    expected_version_id: str | None = None
    change: ContinuityChange
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def plans_only(self):
        if self.change.kind != 'plan':
            raise ValueError('This editor changes plans only.')
        return self


def plan_sources(connection, head_id):
    for position, node in enumerate(path_nodes(connection, head_id), start=1):
        if node['role'] == 'ooc':
            continue
        # Position plus exact prose hash survives archive ID remapping; edited paths
        # cannot reuse evidence from the discarded passage.
        digest = hashlib.sha256(node['text'].encode('utf-8')).hexdigest()
        source_id = f'passage:{position}:{digest}'
        for chunk in compile_chunks(source_id, f'Passage {position}', node['text']):
            yield {**chunk.evidence(), 'node_id': node['id']}


def validate_author_change(connection, head_id, version_id, change):
    sources = {source['id']: source for source in plan_sources(connection, head_id)}
    existing = {entry['id']: entry for entry in continuity_view(connection, head_id, version_id)['entries']}
    require(change['kind'] == 'plan', 'Author continuity edits currently support plans only.')
    try:
        validate_change(change, sources, existing, required_source=None)
    except DomainError as error:
        raise DomainError(error.message, 400) from error


class Plans:
    def __init__(self, database):
        self.database = database

    def view(self, branch_id):
        with self.database.connect() as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            version = plan_head(connection, branch_id)
            view = continuity_view(connection, branch['head_id'], version)
            return {**view, 'revision': branch['revision'], 'version_id': version}

    def sources(self, branch_id, offset=0):
        with self.database.connect() as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            from itertools import islice
            selected = list(islice(plan_sources(connection, branch['head_id']), offset, offset + 9))
            return {'items': selected[:8], 'revision': branch['revision'],
                    'next_offset': offset + 8 if len(selected) > 8 else None}

    def save(self, branch_id, body):
        payload = {'branch_id': branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'continuity-plan', payload)
            if cached is not None:
                return cached
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
            check_revision(branch, body.expected_revision)
            current = plan_head(connection, branch_id)
            require(current == body.expected_version_id, 'Plans changed in another view. Reopen the plan before saving.', 409)
            require(branch['head_id'], 'Add accepted prose before recording a source-backed plan.', 409)
            change = body.change.model_dump()
            validate_author_change(connection, branch['head_id'], current, change)
            version = identifier()
            connection.execute('INSERT INTO continuity_edits VALUES (?,?,?,?,?,?,?,?)',
                               (version, version, branch_id, branch['head_id'], current, encode([change]), body.note, now()))
            bind_plan_head(connection, branch_id, version)
            connection.execute('UPDATE branches SET revision=revision+1,updated_at=? WHERE id=?', (now(), branch_id))
            connection.execute('UPDATE stories SET updated_at=? WHERE id=?', (now(), branch['story_id']))
            return remember(connection, body.operation_id, 'continuity-plan', payload,
                            {'id': version, 'entry_id': change['target_id'] or f"{version}:{change['id']}"})
