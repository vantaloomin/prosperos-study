"""Convert complete scoped outputs into proposals, with author-bound application."""
import json

from pydantic import Field, ValidationError

from server.database import decode, encode, identifier, many, now, one
from server.errors import DomainError, require
from server.memory.side_archive import permitted_sources
from server.side_targets import read_context
from server.side_work import EDIT_TASKS, writing_labels
from server.structured_text import json_payload
from server.text_edits.models import ExactInput
from server.text_edits.service import apply_in, create_in, proposal_view


class EditOutput(ExactInput):
    replacement: str = Field(max_length=100000)
    explanation: str = Field(max_length=2000)
    source_ids: list[str] = Field(max_length=50)


def parse_output(output, snapshot):
    try:
        value = EditOutput.model_validate(json.loads(json_payload(output)))
    except (ValueError, ValidationError):
        raise DomainError('The Companion did not return a complete structured text proposal. The original output is saved; retry is explicit.', 502) from None
    allowed = {source['id'] for source in permitted_sources(snapshot)}
    require(len(value.source_ids) == len(set(value.source_ids)) and set(value.source_ids) <= allowed,
            'The proposed edit cites a source outside this request’s frozen scope. No edit was applied.', 502)
    return value.model_dump()


def finish_edit(connection, database, reply_id, snapshot, output):
    work = snapshot.get('side_work')
    if not work or work['task'] not in EDIT_TASKS:
        return
    if connection.execute('SELECT 1 FROM side_edit_results WHERE reply_id=?', (reply_id,)).fetchone():
        return
    generated = parse_output(output, snapshot)
    pin = read_context(connection, snapshot['context_id'])['snapshot']
    target = pin['target']['snapshot']
    identity = identifier()
    detail = {'version': 1, 'request': work, 'target': target, 'generated': generated, 'writing': writing_labels(snapshot)}
    connection.execute('INSERT INTO companion_edit_origins VALUES (?,?,?,?)', (identity, target['ref']['story_id'], encode(detail), now()))
    proposal = create_in(connection, target, work['selection'], work['action'], generated['replacement'], generated['explanation'],
                         origin={'kind': 'companion', 'edit_origin_id': identity})
    error = ''
    if work['authority'] == 'apply':
        connection.execute('SAVEPOINT companion_apply')
        try:
            apply_in(connection, proposal['id'], 0, 'Companion revision', True, database=database)
        except DomainError as failure:
            connection.execute('ROLLBACK TO companion_apply')
            error = failure.message
            connection.execute("UPDATE text_edit_proposals SET status='conflict' WHERE id=?", (proposal['id'],))
        finally:
            connection.execute('RELEASE companion_apply')
    connection.execute('INSERT INTO side_edit_results VALUES (?,?,?,?)', (reply_id, identity, proposal['id'], error))


def edit_result(connection, reply_id):
    row = connection.execute('SELECT * FROM side_edit_results WHERE reply_id=?', (reply_id,)).fetchone()
    if row is None:
        return None
    origin = one(connection, 'SELECT detail FROM companion_edit_origins WHERE id=?', (row['origin_id'],))
    proposals = many(connection, "SELECT id FROM text_edit_proposals WHERE json_extract(origin,'$.edit_origin_id')=? ORDER BY created_at,id", (row['origin_id'],))
    return {**dict(row), 'origin': decode(origin['detail']), 'proposals': [proposal_view(connection, value['id']) for value in proposals]}
