from server.database import decode, one
from server.errors import require
from server.phrases.detection import digest
from server.text_edits.candidates import source_candidate


def saved_output(connection, candidate, attempt):
    if attempt == candidate['attempt']:
        require(candidate['status'] == 'done', 'An edited draft needs a completed source attempt.')
        return candidate['output']
    row = one(connection, 'SELECT * FROM generation_attempts WHERE candidate_id=? AND attempt=?', (candidate['id'], attempt))
    require(row['status'] == 'done', 'An edited draft cannot use partial provider output.')
    return row['output']


def validate_candidate_snapshot(connection, ref, value):
    candidate, _ = source_candidate(connection, ref)
    basis = value['basis']
    require(set(basis) == {'revision', 'draft_id', 'attempt', 'original_sha256', 'edit_receipt_id', 'cleanup_id'}, 'A draft text snapshot has an invalid shape.')
    require(type(basis['attempt']) is int and basis['attempt'] >= 1, 'An edited draft needs a completed attempt identity.')
    original = saved_output(connection, candidate, basis['attempt'])
    require(digest(original) == basis['original_sha256'], 'An edited draft lost its original provider output.')
    require(value['limit'] == 100000 and len(value['text']) <= 100000, 'An edited draft exceeds its text limit.')
    if basis['draft_id'] is None:
        require(basis['revision'] == 0 and basis['edit_receipt_id'] is None, 'An unedited draft has an invalid revision.')
        validate_base_wording(connection, candidate, value, original)
        return
    head = one(connection, 'SELECT * FROM candidate_text_heads WHERE id=?', (basis['draft_id'],))
    require(head['candidate_id'] == candidate['id'] and head['attempt'] == basis['attempt'], 'An author revision changed its candidate attempt.')
    require(0 < basis['revision'] <= head['revision'] and basis['cleanup_id'] is None, 'An author revision has an invalid sequence or source.')
    receipt = one(connection, 'SELECT after_target FROM text_edit_receipts WHERE id=?', (basis['edit_receipt_id'],))
    after = decode(receipt['after_target'])
    require(all(after[key] == value[key] for key in ('ref', 'basis', 'text')), 'An author revision disagrees with its immutable edit receipt.')


def validate_base_wording(connection, candidate, value, original):
    basis = value['basis']
    if basis['cleanup_id'] is None:
        require(value['text'] == original, 'The unedited draft differs from its original provider text.')
        return
    cleanup = one(connection, 'SELECT * FROM candidate_cleanups WHERE id=?', (basis['cleanup_id'],))
    require(cleanup['candidate_id'] == candidate['id'] and cleanup['attempt'] == basis['attempt'] and cleanup['status'] == 'done',
            'An edited draft points outside its completed cleanup.')
    require(value['text'] == cleanup['cleaned'], 'The selected cleanup differs from the edit source.')


def validate_candidate_result(receipt):
    before, after = receipt['before_target'], receipt['after_target']
    source, result = before['basis'], after['basis']
    require(before['ref'] == after['ref'], 'A draft edit changed its destination.')
    require(result['revision'] == source['revision'] + 1 and result['edit_receipt_id'] == receipt['id'], 'A draft edit changed its revision sequence or receipt.')
    require(result['attempt'] == source['attempt'] and result['original_sha256'] == source['original_sha256'], 'A draft edit changed the provider attempt.')
    require(source['draft_id'] is None or source['draft_id'] == result['draft_id'], 'A draft edit changed its working-copy identity.')
    require(receipt['result'] == {'candidate_id': before['ref']['candidate_id'], 'draft_id': result['draft_id'], 'attempt': result['attempt']},
            'A draft edit result disagrees with its source.')


def validate_candidate_heads(connection, data):
    for head in data['candidate_text_heads']:
        row = one(connection, 'SELECT after_target FROM text_edit_receipts WHERE id=?', (head['receipt_id'],))
        target = decode(row['after_target'])
        require(target['ref']['kind'] == 'candidate' and target['ref']['candidate_id'] == head['candidate_id'], 'A draft head has another target’s receipt.')
        require(target['basis']['draft_id'] == head['id'] and target['basis']['attempt'] == head['attempt']
                and target['basis']['revision'] == head['revision'] and target['text'] == head['text'], 'A draft head disagrees with its applied revision.')
        candidate = one(connection, 'SELECT * FROM candidates WHERE id=?', (head['candidate_id'],))
        if candidate['accepted_node_id'] and candidate['attempt'] == head['attempt']:
            node = one(connection, 'SELECT * FROM nodes WHERE id=?', (candidate['accepted_node_id'],))
            require(node['text'] == head['text'] and decode(node['metadata']).get('edit_receipt_id') == head['receipt_id'], 'The accepted draft differs from its selected author revision.')
    for node in data['nodes']:
        metadata = decode(node['metadata'])
        if metadata.get('source') != 'generated' or not metadata.get('edit_receipt_id'):
            continue
        receipt = one(connection, 'SELECT after_target FROM text_edit_receipts WHERE id=?', (metadata['edit_receipt_id'],))
        target = decode(receipt['after_target'])
        require(target['ref']['kind'] == 'candidate' and target['ref']['candidate_id'] == metadata.get('candidate_id') and target['text'] == node['text'],
                'Generated prose lost its selected author revision.')
