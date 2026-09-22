from server.errors import require
from server.text_edits.models import TextTarget
from server.text_edits.targets import check_current, save_document


def autosave_document(database, body):
    # Typing updates one working copy. CAS prevents stale writes; after a lost
    # acknowledgement clients read the current version before deciding to save.
    # Unlike an applied edit, a typing pause does not retain another full receipt.
    with database.connect(write=True) as connection:
        check_current(connection, body.target, body.expected_version)
        return save_document(connection, body.target, body.text)


def consume_document(connection, branch, purpose, expected_version, text):
    """Use a reviewed unsent draft once, in the accepting operation's transaction.

    Existing callers without a draft version retain their original contract.
    Input models trim surrounding whitespace; bound drafts preserve their exact
    saved text after comparing against that normalized request value.
    """
    if expected_version is None:
        return text
    ref = TextTarget(kind='document', story_id=branch['story_id'], branch_id=branch['id'], purpose=purpose)
    source = check_current(connection, ref, expected_version)
    require(source['text'].strip() == text, 'The submitted wording does not match the selected unsent draft.', 409)
    save_document(connection, ref, '')
    return source['text']
