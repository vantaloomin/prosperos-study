"""Validate cleanup receipts independently of current path state or opt-in settings."""
from server.archives.links import snapshot_links
from server.cleanup.models import CleanupChoices
from server.cleanup.protocol import PROMPT, apply_output, content_for
from server.database import decode, encode, one
from server.errors import require
from server.phrases.detection import digest


def validate_cleanups(connection, data):
    for row in data['candidate_cleanups']:
        validate_cleanup(connection, row)


def validate_cleanup(connection, row):
    snapshot = decode(row['snapshot'])
    candidate = one(connection, 'SELECT * FROM candidates WHERE id=?', (row['candidate_id'],))
    generation = one(connection, 'SELECT * FROM generations WHERE id=?', (candidate['generation_id'],))
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (row['branch_id'],))
    require(row['branch_id'] == generation['branch_id'] == snapshot['branch']['id'], 'Cleanup belongs to a different path.')
    snapshot_links(connection, snapshot, branch['story_id'])
    require(snapshot['protocol'] == 1 and snapshot['attempt'] == row['attempt'], 'Unsupported cleanup receipt.')
    require(snapshot['original_sha256'] == digest(snapshot['original']), 'Cleanup original text was changed.')
    validate_original(connection, candidate, snapshot)
    if snapshot['settings']['choices'] is not None:
        CleanupChoices.model_validate(snapshot['settings']['choices'])
    for item in snapshot['evidence']:
        require(0 <= item['start'] < item['end'] <= len(snapshot['original'])
                and item['quote'] == snapshot['original'][item['start']:item['end']]
                and item['sha256'] == snapshot['original_sha256'], 'Cleanup evidence does not match its original draft.')
    require(snapshot['instruction'] == PROMPT and decode(snapshot['content']) == content_for(snapshot['original'], snapshot['evidence'], snapshot.get('guidance')),
            'Cleanup inputs do not match their saved evidence.')
    validate_result(row, snapshot)


def validate_original(connection, candidate, snapshot):
    original = candidate['output'] if candidate['attempt'] == snapshot['attempt'] else one(
        connection, 'SELECT output FROM generation_attempts WHERE candidate_id=? AND attempt=?',
        (candidate['id'], snapshot['attempt']))['output']
    require(original == snapshot['original'], 'Cleanup original does not belong to this writer attempt.')


def validate_result(row, snapshot):
    require(row['selected'] != 'cleaned' or row['status'] == 'done', 'An unfinished cleanup cannot be selected.')
    if row['status'] == 'done':
        cleaned, edits = apply_output(row['output'], snapshot['original'], snapshot['evidence'])
        require(cleaned == row['cleaned'] and edits == decode(row['edits']), 'Cleanup result differs from its allowed replacements.')


def restore_cleanup(table, row, updated):
    if table == 'candidates' and decode(row['usage']).get('cleanup_pending'):
        updated = {**updated, 'usage': encode({**decode(row['usage']), 'cleanup_pending': False})}
    if table == 'branch_cleanup_settings':
        return {**updated, 'enabled': 0, 'version': row['version'] + 1}
    if table == 'candidate_cleanups' and row['status'] == 'running':
        return {**updated, 'status': 'interrupted', 'selected': 'original',
                'error': 'Restored cleanup was interrupted. The original is available; cleanup was not resent.'}
    if table == 'candidates' and row['status'] == 'cleaning':
        return {**updated, 'status': 'done', 'error': ''}
    return updated
