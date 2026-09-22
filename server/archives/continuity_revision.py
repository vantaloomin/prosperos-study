"""Reconstruct revision requests without widening the original candidate scope."""
from server.continuity_revision import RevisionRequest, freeze
from server.database import decode
from server.errors import require


def validate_continuity_revisions(data):
    candidates = {row['id']: row for row in data['candidates']}
    snapshots = {row['id']: decode(row['snapshot']) for row in data['generations']}
    edits = {row['id']: row for row in data['text_edit_receipts']}
    parents = {}
    for row in [*data['candidates'], *data['generation_attempts']]:
        candidate = candidates[row['candidate_id']] if 'candidate_id' in row else row
        usage = decode(row['usage'])
        revision = usage.get('continuity_revision')
        if revision is None:
            continue
        source = candidates.get(revision.get('candidate_id'))
        require(source and source['id'] != candidate['id'] and source['generation_id'] == candidate['generation_id']
                and source['status'] == 'done' and source['profile'] == candidate['profile'],
                'A continuity revision must reference a completed draft with the same saved evidence and profile.')
        RevisionRequest.model_validate({'operation_id': 'archive-validation', 'expected_attempt': revision['attempt'],
                                        'original_sha256': revision['original_sha256'], 'concern': revision['concern']})
        original_usage = decode(source['usage'])
        require(usage.get('writer_recall') == original_usage.get('writer_recall'),
                'A continuity revision changed its source draft’s recall evidence.')
        original = revision_source(source, revision, edits)
        expected = freeze(snapshots[source['generation_id']], decode(source['profile']), original_usage, original, revision['concern'],
                          version=revision.get('version'), source_edit_receipt_id=revision.get('source_edit_receipt_id'))
        require(revision == expected, 'A continuity revision differs from its original draft, evidence or bounded request.')
        parents[candidate['id']] = source['id']
    for start in parents:
        trail, current = set(), start
        while current in parents:
            require(current not in trail, 'Continuity revision ancestry is cyclic.')
            trail.add(current)
            current = parents[current]


def revision_source(source, revision, edits):
    if revision.get('version') != 3:
        return source
    edit = edits.get(revision.get('source_edit_receipt_id'))
    require(edit is not None, 'A continuity revision lost its selected author text receipt.')
    target = decode(edit['after_target'])
    require(target['ref']['kind'] == 'candidate' and target['ref']['candidate_id'] == source['id'] and target['basis']['attempt'] == revision['attempt'],
            'A continuity revision points outside its selected author draft.')
    return {**source, 'output': target['text']}


def remap_revision_usage(usage, mapping):
    if 'continuity_revision' not in usage:
        return usage
    revision = usage['continuity_revision']
    updated = {**revision, 'candidate_id': mapping[revision['candidate_id']]}
    if revision.get('source_edit_receipt_id'):
        updated['source_edit_receipt_id'] = mapping[revision['source_edit_receipt_id']]
    return {**usage, 'continuity_revision': updated}
