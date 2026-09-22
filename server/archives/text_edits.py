from server.archives.candidate_text import (
    validate_candidate_heads,
    validate_candidate_result,
    validate_candidate_snapshot,
)
from server.archives.format import TEXT_EDIT_TABLES, V41_TABLES, V42_TABLES, V43_TABLES, V44_TABLES
from server.archives.scene_text import (
    validate_frozen_scene_text,
    validate_scene_text_result,
    validate_scene_text_snapshot,
)
from server.archives.text_edit_versions import (
    restored_target,
    target_snapshots,
    validate_edition_result,
    validate_edition_snapshot,
)
from server.branches import path_nodes
from server.database import decode, one
from server.errors import require
from server.passage_revisions import revised_content
from server.text_edits.models import TextTarget
from server.text_edits.service import proposed_text, read_proposal, read_receipt
from server.text_edits.targets import DOCUMENT_LIMITS, snapshot_version
from server.text_edits.versioned import VERSIONED_KINDS


def upgrade_text_edits(document):
    if document['version'] == 41:
        require(set(document['data']) == set(V41_TABLES), 'Version 41 needs its original record groups.')
        document['data'].update({table: [] for table in TEXT_EDIT_TABLES})
        document['version'] = 42
    if document['version'] == 42:
        require(set(document['data']) == set(V42_TABLES), 'Version 42 needs its original record groups.')
        require(all(target['ref']['kind'] in {'passage', 'story-brief', 'document'} for target in target_snapshots(document['data'])),
                'Version 42 supports its original text destinations only.')
        document['version'] = 43
    if document['version'] == 43:
        require(set(document['data']) == set(V43_TABLES), 'Version 43 needs its original record groups.')
        require(all(target['ref']['kind'] != 'candidate' for target in target_snapshots(document['data'])), 'Version 43 does not include author revisions of unaccepted drafts.')
        document['data']['candidate_text_heads'] = []
        document['version'] = 44
    if document['version'] == 44:
        require(set(document['data']) == set(V44_TABLES), 'Version 44 needs its original record groups.')
        require(all(target['ref']['kind'] != 'scene-block' for target in target_snapshots(document['data'])), 'Version 44 does not include scene block revisions.')
        require(all(not decode(row['state']).get('draft_edits') for row in document['data']['scene_runs'])
                and all(row['kind'] != 'text-edit' for row in document['data']['scene_decisions']), 'Version 44 does not include author scene text decisions.')
        document['version'] = 45
    return document


def validate_snapshot(connection, value, story_id):
    require(set(value) == {'ref', 'basis', 'text', 'label', 'limit', 'version'}, 'A text target snapshot has an invalid shape.')
    ref = TextTarget.model_validate(value['ref'])
    require(ref.story_id == story_id, 'A text edit crosses Story boundaries.')
    require(isinstance(value['text'], str) and isinstance(value['label'], str), 'Text edit snapshots need literal text.')
    require(value['version'] == snapshot_version(value), 'A text target fingerprint does not match its saved content.')
    basis = value['basis']
    require(isinstance(basis, dict) and type(basis.get('revision')) is int and basis['revision'] >= 0, 'A text target needs a valid revision.')
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (story_id,))
    if ref.kind in VERSIONED_KINDS:
        validate_edition_snapshot(connection, ref, value)
        return
    if ref.kind == 'candidate':
        validate_candidate_snapshot(connection, ref, value)
        return
    if ref.kind == 'scene-block':
        validate_scene_text_snapshot(connection, ref, value)
        return
    if ref.kind == 'story-brief':
        require(set(basis) == {'revision'} and basis['revision'] <= story['revision'], 'The Story brief revision is invalid.')
        require(basis['revision'] < story['revision'] or value['text'] == story['premise'], 'The current Story brief disagrees with its snapshot.')
        limit = 30000
    elif ref.kind == 'document':
        validate_document_snapshot(connection, ref, value)
        limit = DOCUMENT_LIMITS[ref.purpose]
    else:
        validate_passage_snapshot(connection, ref, value)
        limit = 100000
    require(value['limit'] == limit and len(value['text']) <= limit, 'A text target exceeds its supported limit.')


def validate_document_snapshot(connection, ref, value):
    branch = one(connection, 'SELECT story_id FROM branches WHERE id=?', (ref.branch_id,))
    require(branch['story_id'] == ref.story_id, 'An unsent text document crosses Stories.')
    basis = value['basis']
    require(set(basis) == {'revision', 'document_id'}, 'An unsent text document snapshot is invalid.')
    if basis['document_id'] is None:
        require(basis['revision'] == 0 and value['text'] == '', 'An unpublished document starts empty.')
        return
    current = one(connection, 'SELECT * FROM text_documents WHERE id=?', (basis['document_id'],))
    require(current['branch_id'] == ref.branch_id and current['story_id'] == ref.story_id and current['purpose'] == ref.purpose,
            'An unsent text target points to another document.')
    require(0 < basis['revision'] <= current['revision'], 'An unsent text target claims an invalid revision.')
    require(basis['revision'] < current['revision'] or value['text'] == current['text'], 'The current unsent text disagrees with its snapshot.')


def validate_passage_snapshot(connection, ref, value):
    basis = value['basis']
    require(set(basis) == {'revision', 'head_id', 'role', 'removed'}, 'A passage target snapshot is invalid.')
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (ref.branch_id,))
    require(branch['story_id'] == ref.story_id and basis['revision'] <= branch['revision'], 'A passage target has an invalid telling or revision.')
    current = {row['id'] for row in path_nodes(connection, branch['head_id'], include_removed=True)}
    require(basis['head_id'] in current, 'A passage target head is outside its telling.')
    path = {row['id']: row for row in path_nodes(connection, basis['head_id'], include_removed=True)}
    require(ref.node_id in path, 'The passage is outside its frozen target path.')
    node = path[ref.node_id]
    require(value['text'] == node['text'] and basis['role'] == node['role'] and type(basis['removed']) is bool
            and basis['removed'] == bool(node['metadata'].get('removed')), 'A passage target disagrees with its immutable source.')


def validate_text_edits(connection, data):
    validate_candidate_heads(connection, data)
    validate_frozen_scene_text(connection, data)
    for row in data['text_documents']:
        branch = one(connection, 'SELECT story_id FROM branches WHERE id=?', (row['branch_id'],))
        require(branch['story_id'] == row['story_id'] and len(row['text']) <= DOCUMENT_LIMITS[row['purpose']], 'An unsent text document is invalid.')
    for row in data['text_edit_proposals']:
        proposal = read_proposal(connection, row['id'])
        validate_snapshot(connection, proposal['target'], proposal['story_id'])
        proposed_text(proposal)
        from server.archives.side_edits import validate_proposal_origin
        validate_proposal_origin(connection, proposal)
        require(len(proposal['explanation']) <= 2000, 'An edit explanation is too long.')
        receipt = connection.execute('SELECT id FROM text_edit_receipts WHERE proposal_id=?', (row['id'],)).fetchone()
        require((proposal['status'] == 'applied') == bool(receipt), 'An applied edit needs exactly one receipt.')
        if proposal['undo_of']:
            original = read_receipt(connection, proposal['undo_of'])
            require(original['story_id'] == proposal['story_id'] and original['after_target']['ref'] == proposal['target']['ref'],
                    'An inverse edit points outside its original destination.')
    for row in data['text_edit_receipts']:
        validate_receipt(connection, read_receipt(connection, row['id']))
    for node in data['nodes']:
        metadata = decode(node['metadata'])
        if metadata.get('source') == 'text_edit':
            receipt = read_receipt(connection, metadata['edit_receipt_id'])
            require(receipt['after_target']['ref'].get('node_id') == node['id'], 'An edited passage has an invalid receipt.')


def validate_receipt(connection, receipt):
    before, after = receipt['before_target'], receipt['after_target']
    for target in (before, after):
        validate_snapshot(connection, target, receipt['story_id'])
    proposal = read_proposal(connection, receipt['proposal_id'])
    require(proposal['story_id'] == receipt['story_id'] and proposal['target']['version'] == before['version'], 'An edit receipt changed its proposed target.')
    require(all(receipt[key] == proposal[key] for key in ('selection', 'action', 'replacement', 'explanation', 'origin', 'undo_of')), 'An edit receipt changed the reviewed proposal.')
    require(proposed_text(proposal) == after['text'], 'An edit receipt does not reproduce the applied text.')
    require(before['ref']['kind'] == after['ref']['kind'], 'An edit receipt changed destination kind.')
    if before['ref']['kind'] in VERSIONED_KINDS:
        validate_edition_result(connection, receipt)
    elif before['ref']['kind'] == 'candidate':
        validate_candidate_result(receipt)
    elif before['ref']['kind'] == 'scene-block':
        validate_scene_text_result(connection, receipt)
    elif before['ref']['kind'] == 'passage':
        validate_rebuilt_path(connection, receipt)
    else:
        validate_field_result(receipt)


def validate_field_result(receipt):
    before, after = receipt['before_target'], receipt['after_target']
    require(before['ref'] == after['ref'], 'A field edit changed its destination.')
    increment = 1
    if before['ref']['kind'] == 'document':
        if before['basis']['document_id'] is not None:
            require(before['basis']['document_id'] == after['basis']['document_id'], 'A field edit changed its document identity.')
            increment = int(before['text'] != after['text'])
        result = {'document_id': after['basis']['document_id']}
    else:
        result = {'story_id': before['ref']['story_id']}
    require(after['basis']['revision'] == before['basis']['revision'] + increment, 'A field edit changed its revision sequence.')
    require(receipt['result'] == result, 'A field edit result disagrees with its destination.')


def validate_rebuilt_path(connection, receipt):
    before, after = receipt['before_target'], receipt['after_target']
    require(after['basis']['revision'] == 0, 'An edited telling receipt must record its initial revision.')
    original = path_nodes(connection, before['basis']['head_id'], include_removed=True)
    revised = path_nodes(connection, after['basis']['head_id'], include_removed=True)
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (after['ref']['branch_id'],))
    require(branch['forked_from'] == before['ref']['branch_id'] and branch['fork_node_id'] == before['ref']['node_id'], 'An edited telling lost its original source.')
    require(len(original) == len(revised), 'An edited telling must preserve its complete passage suffix.')
    position = next(index for index, node in enumerate(original) if node['id'] == before['ref']['node_id'])
    require([node['id'] for node in original[:position]] == [node['id'] for node in revised[:position]], 'An edit changed the earlier prefix.')
    replacement = revised[position]
    metadata = {'source': 'text_edit', 'replaces': original[position]['id'], 'edit_receipt_id': receipt['id']}
    if not replacement['text']:
        metadata.update(removed=True, original_node_id=original[position]['id'], source_branch_id=before['ref']['branch_id'])
    require(replacement['metadata'] == metadata and replacement['id'] == after['ref']['node_id'] and replacement['text'] == after['text'], 'An edited passage lost its receipt or exact wording.')
    for source, target in zip(original[position:], revised[position:], strict=True):
        require(source['role'] == target['role'] and source['manifest_id'] == target['manifest_id'], 'An edit changed a passage role or Library pin.')
    for source, target in zip(original[position + 1:], revised[position + 1:], strict=True):
        text, role, expected = revised_content(connection, source, None)
        if expected.get('removed'):
            expected['source_branch_id'] = expected.get('source_branch_id') or before['ref']['branch_id']
        require(target['text'] == text and target['metadata'] == expected, 'An edit changed a later passage or its source identity.')
    require(receipt['result'] == {'branch_id': after['ref']['branch_id'], 'node_id': after['ref']['node_id'],
        'source_branch_id': before['ref']['branch_id'], 'source_head_id': before['basis']['head_id'],
        'preserved_suffix_count': len(original) - position - 1, 'state_boundary_node_id': original[position]['parent_id']},
        'An edit result disagrees with its source path.')


def remap_text_edit(table, row, mapping):
    from server.archives.remap import fields
    from server.database import encode
    result = dict(row)
    if 'origin' in row:
        result['origin'] = encode(fields(decode(row['origin']), mapping))
    for key in ('target',) if table == 'text_edit_proposals' else ('before_target', 'after_target'):
        value = decode(row[key])
        value['ref'] = fields(restored_target(value['ref'], mapping), mapping)
        value['basis'] = fields(value['basis'], mapping)
        value['version'] = snapshot_version(value)
        result[key] = encode(value)
    if table == 'text_edit_receipts':
        result['result'] = encode(fields(decode(row['result']), mapping))
    return result
