"""Scoped edit provenance survives optional omission of private discussion."""
from server.archives.format import SIDE_EDIT_TABLES, V47_TABLES
from server.archives.text_edits import validate_snapshot
from server.database import decode, encode, one
from server.errors import require
from server.side_edits import EditOutput, parse_output
from server.side_targets import read_context
from server.side_work import (
    EDIT_TASKS,
    SideWork,
    effective_prompt,
    exact_receipt,
    selection_for,
    work_context,
    writing_labels,
)
from server.text_edits.service import proposed_text, read_proposal


def upgrade_side_edits(document):
    if document['version'] == 47:
        require(set(document['data']) == set(V47_TABLES), 'Version 47 needs its original record groups.')
        require(all(not {'side_work', 'work_prompt'} & set(decode(row['snapshot'])) for row in document['data']['side_turns']),
                'Version 47 does not include scoped Companion work.')
        require(all(decode(row['origin']) == {'kind': 'author'} for table in ('text_edit_proposals', 'text_edit_receipts') for row in document['data'][table]),
                'Version 47 does not include Companion edit origins.')
        document['data'].update({table: [] for table in SIDE_EDIT_TABLES})
        document['version'] = 48
    return document


def validate_work(work, editing=False):
    keys = {'version', 'task', 'action', 'authority', 'request_ref'} | ({'selection'} if work.get('task') in EDIT_TASKS else set())
    require(set(work) == keys and work['version'] == 1, 'Unsupported Companion work scope.')
    SideWork.model_validate({key: work[key] for key in ('task', 'action', 'authority')})
    require(isinstance(work['request_ref'], str) and 8 <= len(work['request_ref']) <= 100, 'The Companion request reference is invalid.')
    require(not editing or work['task'] in EDIT_TASKS, 'A discussion cannot authorize an edit.')


def validate_origin(connection, row):
    detail = decode(row['detail'])
    require(set(detail) == {'version', 'request', 'target', 'generated', 'writing'} and detail['version'] == 1,
            'Unsupported Companion edit provenance.')
    validate_work(detail['request'], editing=True)
    validate_snapshot(connection, detail['target'], row['story_id'])
    generated = EditOutput.model_validate(detail['generated']).model_dump()
    require(len(set(generated['source_ids'])) == len(generated['source_ids']), 'An edit repeats source references.')
    proposed_text({'target': detail['target'], 'selection': detail['request']['selection'], 'action': detail['request']['action'], 'replacement': generated['replacement']})
    require(set(detail['writing']) == {'style', 'recipe'}, 'A writing label is incomplete.')
    for label in detail['writing'].values():
        require(label is None or (set(label) == {'name', 'number'} and isinstance(label['name'], str) and type(label['number']) is int and label['number'] >= 1),
                'An edit writing label is invalid.')
    return detail


def validate_proposal_origin(connection, proposal):
    origin = proposal['origin']
    if origin == {'kind': 'author'}:
        return
    if origin.get('kind') == 'recipe':
        from server.archives.recipes import validate_proposal_origin as validate_recipe_origin
        validate_recipe_origin(connection, proposal)
        return
    require(set(origin) == {'kind', 'edit_origin_id'} and origin['kind'] == 'companion', 'This edit proposal has an unsupported origin.')
    row = one(connection, 'SELECT * FROM companion_edit_origins WHERE id=?', (origin['edit_origin_id'],))
    detail = decode(row['detail'])
    require(row['story_id'] == proposal['story_id'] and detail['target']['ref'] == proposal['target']['ref'],
            'A Companion edit changed its original destination.')


def validate_turn(connection, snapshot):
    work = snapshot.get('side_work')
    if not work:
        require('work_prompt' not in snapshot, 'A discussion changed its prompt without a task scope.')
        return
    validate_work(work)
    require(snapshot['work_prompt'] == effective_prompt({key: value for key, value in snapshot.items() if key != 'work_prompt'}),
            'A Companion task changed its fixed output boundary.')
    context = decode(snapshot['content'])
    require(all(context.get(key) == value for key, value in work_context(snapshot).items()), 'Frozen task inputs differ from their saved scope.')
    if work['task'] in EDIT_TASKS:
        pin = read_context(connection, snapshot['context_id'])['snapshot']
        require(pin['target']['kind'] == 'text', 'A text action has no exact target.')
        selected = selection_for(work['action'], pin['target']['snapshot']['text'], pin['target']['selection'])
        require(work['selection'] == selected and 'writing_guidance' in snapshot, 'A text action changed its selected range or writing guidance.')
    else:
        require('writing_guidance' not in snapshot, 'A factual or discussion task acquired prose styling.')


def validate_side_edits(connection, data):
    origins = {row['id']: validate_origin(connection, row) for row in data['companion_edit_origins']}
    turns = {row['id']: decode(row['snapshot']) for row in data['side_turns']}
    for snapshot in turns.values():
        validate_turn(connection, snapshot)
    results = {row['reply_id']: row for row in data['side_edit_results']}
    for reply in data['side_replies']:
        snapshot = turns[reply['turn_id']]
        work = snapshot.get('side_work')
        if work and not snapshot.get('retrieval'):
            validate_receipts(reply, snapshot)
        required = work and work['task'] in EDIT_TASKS and reply['status'] == 'done'
        require(bool(required) == (reply['id'] in results), 'A complete scoped reply needs exactly one edit result; partial replies cannot own one.')
        if required:
            result = results[reply['id']]
            origin = origins[result['origin_id']]
            pin = read_context(connection, snapshot['context_id'])['snapshot']
            require(origin == {'version': 1, 'request': work, 'target': pin['target']['snapshot'],
                               'generated': parse_output(reply['output'], snapshot), 'writing': writing_labels(snapshot)},
                    'A Companion result differs from its frozen request or original output.')
            proposal = read_proposal(connection, result['proposal_id'])
            require(proposal['origin'] == {'kind': 'companion', 'edit_origin_id': result['origin_id']}
                    and proposal['target'] == origin['target'] and proposal['selection'] == work['selection']
                    and proposal['action'] == work['action'], 'A generated proposal changed its original scope.')
            if proposal['revision'] == 0:
                require(all(proposal[key] == origin['generated'][key] for key in ('replacement', 'explanation')), 'A proposal changed its generated wording without an author revision.')
            usage = decode(reply['usage'])
            require(usage and usage[-1].get('completed') is True and usage[-1]['reported'].get('finish_reason') in {None, 'stop'}
                    and not usage[-1]['reported'].get('output_limit_uncertain'),
                    'An edit was produced from incomplete provider output.')


def validate_receipts(reply, snapshot):
    from server.side_context import assemble_context
    coverage = set()
    for index, item in enumerate(decode(reply['usage'])):
        content = item['content']
        expected = exact_receipt(content)
        require(all(item.get(key) == expected[key] for key in ('content_sha256', 'source_ids')), 'An edit request receipt changed its saved bytes.')
        require(content == assemble_context(snapshot, decode(reply['profile']), item['source_ids']), 'A request changed its task, evidence or writing inputs.')
        require(index != 0 or content == snapshot['content'], 'A reply changed its common starting inputs.')
        coverage.update(item['source_ids'])
    require(sorted(coverage) == decode(reply['coverage']), 'Scoped reply coverage differs from its request receipts.')


def remap_origin(connection, row, mapping):
    from server.archives.remap import fields
    from server.archives.text_edit_versions import bind_restored_editions
    from server.archives.text_edits import remap_text_edit
    value = decode(row['detail'])
    target = remap_text_edit('text_edit_proposals', {'target': encode(value['target'])}, mapping)
    value['target'] = decode(bind_restored_editions(connection, 'text_edit_proposals', target)['target'])
    return {**fields(row, mapping), 'detail': encode(value)}
