"""Reconstruct revision requests without widening the original candidate scope."""
from server.continuity_revision import RevisionRequest, freeze
from server.database import decode
from server.errors import require


def validate_continuity_revisions(data):
    candidates = {row['id']: row for row in data['candidates']}
    snapshots = {row['id']: decode(row['snapshot']) for row in data['generations']}
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
        expected = freeze(snapshots[source['generation_id']], decode(source['profile']), original_usage, source, revision['concern'], version=revision.get('version'))
        require(revision == expected, 'A continuity revision differs from its original draft, evidence or bounded request.')
        parents[candidate['id']] = source['id']
    for start in parents:
        trail, current = set(), start
        while current in parents:
            require(current not in trail, 'Continuity revision ancestry is cyclic.')
            trail.add(current)
            current = parents[current]


def remap_revision_usage(usage, mapping):
    if 'continuity_revision' not in usage:
        return usage
    revision = usage['continuity_revision']
    return {**usage, 'continuity_revision': {**revision, 'candidate_id': mapping[revision['candidate_id']]}}
