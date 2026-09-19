"""Scan only eligible, accepted prose on the chosen path; never call a provider."""
from typing import Literal

from pydantic import Field

from server.database import decode, one
from server.errors import require
from server.models import Input
from server.phrases.detection import ALGORITHM, detect, tokens
from server.stories import check_revision

MAX_CHARACTERS = 200_000
MAX_TOKENS = 40_000
SCOPES = {'recent': 20, 'extended': 100, 'path': None}


class PhraseCheck(Input):
    expected_revision: int = Field(ge=0)
    scope: Literal['recent', 'extended', 'path'] = 'recent'
    minimum: Literal[2, 3, 4] = 3


def accepted_prose(connection, head_id):
    rows = connection.execute(
        'WITH RECURSIVE path(id,parent_id,depth) AS (SELECT id,parent_id,0 FROM nodes WHERE id=? '
        'UNION ALL SELECT n.id,n.parent_id,p.depth+1 FROM nodes n JOIN path p ON p.parent_id=n.id) '
        'SELECT n.id,n.role,n.text,n.metadata FROM path p JOIN nodes n ON n.id=p.id ORDER BY p.depth',
        (head_id,))
    for row in rows:
        if row['role'] != 'ooc' and not decode(row['metadata']).get('removed'):
            yield dict(row)


def select_passages(connection, head_id, scope):
    selected, characters, word_count, truncated = [], 0, 0, False
    limit = SCOPES[scope]
    for node in accepted_prose(connection, head_id):
        if limit is not None and len(selected) == limit:
            break
        size = len(node['text'])
        words = len(tokens(node['id'], node['text']))
        if characters + size > MAX_CHARACTERS or word_count + words > MAX_TOKENS:
            truncated = True
            break
        selected.append(node)
        characters += size
        word_count += words
    return list(reversed(selected)), characters, word_count, truncated


def check(database, branch_id, body):
    with database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
        check_revision(branch, body.expected_revision)
        passages, characters, word_count, truncated = select_passages(connection, branch['head_id'], body.scope)
    findings, more = detect(passages, body.minimum)
    with database.connect() as connection:
        current = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
        require(current == branch, 'This path changed while checking wording. Check the current path again.', 409)
    return {'algorithm': ALGORITHM, 'branch_id': branch_id, 'revision': branch['revision'],
            'head_id': branch['head_id'], 'scope': body.scope, 'minimum': body.minimum,
            'passage_count': len(passages), 'characters': characters, 'word_count': word_count,
            'limited': truncated, 'character_limit': MAX_CHARACTERS, 'word_limit': MAX_TOKENS,
            'findings': findings, 'more_findings': more}
