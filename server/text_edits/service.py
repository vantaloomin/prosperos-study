from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.operations import previous, remember
from server.text_edits.models import TextSelection, TextTarget
from server.text_edits.selection import apply_selection
from server.text_edits.targets import check_current, read_target, save_document, write_target

PROPOSAL_JSON = ('target', 'selection', 'origin')
RECEIPT_JSON = ('before_target', 'after_target', 'selection', 'origin', 'result')


def view(row, fields):
    return {**row, **{key: decode(row[key]) for key in fields}}


def read_proposal(connection, identity):
    return view(one(connection, 'SELECT * FROM text_edit_proposals WHERE id=?', (identity,)), PROPOSAL_JSON)


def read_receipt(connection, identity):
    return view(one(connection, 'SELECT * FROM text_edit_receipts WHERE id=?', (identity,)), RECEIPT_JSON)


def proposal_view(connection, identity):
    value = read_proposal(connection, identity)
    receipt = connection.execute('SELECT id FROM text_edit_receipts WHERE proposal_id=?', (identity,)).fetchone()
    return {**value, 'after_text': proposed_text(value), 'receipt': read_receipt(connection, receipt['id']) if receipt else None}


def proposed_text(proposal):
    text = apply_selection(proposal['target']['text'], TextSelection.model_validate(proposal['selection']),
                           proposal['action'], proposal['replacement'])
    require(len(text) <= proposal['target']['limit'], 'The proposed text exceeds this destination’s limit.')
    return text


def create_in(connection, target, selection, action, replacement, explanation='', *, origin=None, undo_of=None, status='pending'):
    identity = identifier()
    value = {'target': target, 'selection': selection, 'action': action, 'replacement': replacement}
    proposed_text(value)
    connection.execute('INSERT INTO text_edit_proposals VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?)',
        (identity, target['ref']['story_id'], encode(target), encode(selection), action, replacement, explanation,
         encode(origin or {'kind': 'author'}), status, undo_of, now(), now()))
    return proposal_view(connection, identity)


def apply_in(connection, identity, expected_revision, branch_name, acknowledge_state_reset=False, *, database=None):
    proposal = read_proposal(connection, identity)
    require(proposal['revision'] == expected_revision, 'This proposal changed in another view. Review its latest wording.', 409)
    if proposal['status'] == 'applied':
        receipt = one(connection, 'SELECT id FROM text_edit_receipts WHERE proposal_id=?', (identity,))
        return read_receipt(connection, receipt['id'])
    require(proposal['status'] == 'pending', 'Only a reviewed pending proposal can be applied. Rebase conflicts explicitly.', 409)
    if proposal['undo_of']:
        prior = connection.execute('SELECT id FROM text_edit_receipts WHERE undo_of=?', (proposal['undo_of'],)).fetchone()
        require(prior is None, 'This change has already been undone.', 409)
    ref = TextTarget.model_validate(proposal['target']['ref'])
    require(ref.kind != 'passage' or acknowledge_state_reset, 'Review the preserved prose and the earlier state boundary before creating a revised telling.', 409)
    before = check_current(connection, ref, proposal['target']['version'])
    after_text = proposed_text(proposal)
    receipt_id = identifier()
    after_ref, result = write_target(connection, ref, after_text, receipt_id, branch_name, database)
    after = read_target(connection, after_ref)
    require(after['text'] == after_text, 'The destination did not preserve the proposed text.', 409)
    connection.execute('INSERT INTO text_edit_receipts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (receipt_id, proposal['story_id'], identity, encode(before), encode(after), encode(proposal['selection']),
         proposal['action'], proposal['replacement'], proposal['explanation'], encode(proposal['origin']),
         encode(result), proposal['undo_of'], now()))
    connection.execute("UPDATE text_edit_proposals SET status='applied',updated_at=? WHERE id=?", (now(), identity))
    return read_receipt(connection, receipt_id)


def run(database, body, kind, identity, action):
    payload = {'id': identity, **body.model_dump()}
    with database.connect(write=True) as connection:
        saved = previous(connection, body.operation_id, kind, payload)
        if saved is not None:
            return saved
        return remember(connection, body.operation_id, kind, payload, action(connection))


def create_proposal(database, body):
    def action(connection):
        target = check_current(connection, body.target, body.expected_version)
        return create_in(connection, target, body.selection.model_dump(), body.action, body.replacement, body.explanation)
    return run(database, body, 'text-edit-create', None, action)


def change_proposal(database, identity, body):
    def action(connection):
        value = read_proposal(connection, identity)
        require(value['status'] in {'pending', 'conflict'} and value['revision'] == body.expected_revision,
                'This proposal was changed or decided in another view.', 409)
        proposed_text({**value, 'replacement': body.replacement})
        connection.execute('UPDATE text_edit_proposals SET replacement=?,explanation=?,revision=revision+1,updated_at=? WHERE id=?',
                           (body.replacement, body.explanation, now(), identity))
        return proposal_view(connection, identity)
    return run(database, body, 'text-edit-change', identity, action)


def dismiss_proposal(database, identity, body):
    def action(connection):
        value = read_proposal(connection, identity)
        require(value['revision'] == body.expected_revision and value['status'] != 'applied', 'This proposal has already changed or been applied.', 409)
        if value['status'] == 'dismissed':
            return proposal_view(connection, identity)
        connection.execute("UPDATE text_edit_proposals SET status='dismissed',updated_at=? WHERE id=?", (now(), identity))
        return proposal_view(connection, identity)
    return run(database, body, 'text-edit-dismiss', identity, action)


def rebase_proposal(database, identity, body):
    def action(connection):
        prior = read_proposal(connection, identity)
        require(prior['revision'] == body.expected_revision and prior['status'] in {'pending', 'conflict'}, 'This proposal has already changed or been decided.', 409)
        require(prior['target']['ref'] == body.target.model_dump(exclude_none=True), 'Rebase the same destination; another target needs a separate request.')
        target = check_current(connection, body.target, body.expected_version)
        result = create_in(connection, target, body.selection.model_dump(), body.action, body.replacement, body.explanation,
                           origin=prior['origin'], undo_of=prior['undo_of'])
        connection.execute("UPDATE text_edit_proposals SET status='dismissed',updated_at=? WHERE id=?", (now(), identity))
        return result
    return run(database, body, 'text-edit-rebase', identity, action)


def save_text_document(database, body):
    def action(connection):
        check_current(connection, body.target, body.expected_version)
        return save_document(connection, body.target, body.text)
    return run(database, body, 'text-document-save', None, action)


def list_proposals(connection, story_id):
    one(connection, 'SELECT id FROM stories WHERE id=?', (story_id,))
    return many(connection, "SELECT p.id,p.status,p.created_at,json_extract(p.target,'$.label') AS label,"
                'r.id AS receipt_id FROM text_edit_proposals p LEFT JOIN text_edit_receipts r ON r.proposal_id=p.id '
                'WHERE p.story_id=? ORDER BY p.created_at DESC,p.id DESC LIMIT 100', (story_id,))
