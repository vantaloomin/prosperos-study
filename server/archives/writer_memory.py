"""Validate ordinary Long-story writer receipts at archive boundaries."""
from server.archives.identities import SourceIdentities, records
from server.archives.writer_canon import validate_writer_canon
from server.archives.writer_sources import WriterScope, digest, validate_passages
from server.branches import path_nodes
from server.database import decode, encode
from server.errors import require
from server.memory.budget import token_estimate

CURRENT = {'prospero-lexical-v5': 2, 'prospero-lexical-v6': 2,
           'prospero-lexical-v5-reviewed-aids': 3, 'prospero-lexical-v6-reviewed-aids': 3,
           'prospero-lexical-v7-summary-context': 4}
LEGACY = {f'prospero-lexical-v{i}{suffix}' for i in range(1, 5) for suffix in ('', '-reviewed-aids')}
IDENTITY_LIMIT = 'Some original source IDs are missing from an older restored archive. Text was checked against available sources; original identity and the complete path fingerprint could not be fully verified.'
ALGORITHM_LIMIT = 'Some writer inputs use an older receipt algorithm whose complete source selection is not verified by this version.'


def validate_writer_memory(connection, data):
    identities = SourceIdentities(connection, records(data))
    snapshots = [decode(row['snapshot']) for row in data['generations']]
    snapshots.extend(decode(row['snapshot'])['writer_snapshot'] for row in data['assessment_runs'])
    results = [validate_snapshot(connection, snapshot, identities) for snapshot in snapshots]
    checked = [result for result in results if result is not None]
    return {'checked': len(checked), 'complete': checked.count('complete'),
            'limited': sum(result != 'complete' for result in checked),
            'limitations': sorted({result for result in checked if result != 'complete'})}


def validate_snapshot(connection, snapshot, identities):
    if 'knowledge_lens' in snapshot:
        return None  # This separate source boundary is checked by archives.knowledge.
    content = decode(snapshot['content'])
    memory = snapshot.get('memory')
    policy = content.get('story', {}).get('settings', {}).get('memory', {})
    if memory is None:
        require(policy.get('mode') != 'long' and not any(key in content for key in ('recalled_passages', 'recalled_canon', 'memory_guidance')),
                'Selective writer context has no memory receipt.')
        return None
    require(isinstance(memory, dict), 'Invalid writer memory receipt.')
    require(policy.get('mode') == 'long' and memory.get('mode') == 'long', 'Writer memory disagrees with its frozen mode.')
    algorithm = memory.get('algorithm')
    require(algorithm in CURRENT or algorithm in LEGACY, 'Unsupported writer memory receipt algorithm.')
    if algorithm in LEGACY:
        return ALGORITHM_LIMIT
    require(memory.get('receipt_version') == CURRENT[algorithm], 'Writer memory receipt version disagrees with its algorithm.')
    require(memory['content_sha256'] == digest(snapshot['content']), 'Writer input differs from its memory receipt hash.')
    scope = WriterScope(path_nodes(connection, snapshot['branch']['head_id']), snapshot['branch'], content, identities)
    included = scope.whole_history(content)
    passages = validate_passages(scope, content, memory, included)
    validate_coverage(snapshot, content, scope, included, passages)
    canon_bound = validate_writer_canon(connection, snapshot, content, identities, allow_legacy=not scope.bound or not scope.path)
    from server.archives.writer_summary_aids import validate_writer_aids
    aids_bound = validate_writer_aids(connection, scope, memory, passages)
    return 'complete' if scope.bound and canon_bound and aids_bound else IDENTITY_LIMIT


def validate_coverage(snapshot, content, scope, included, passages):
    memory = snapshot['memory']
    count = len(scope.path)
    expected = {'messages': count, 'included_messages': len(included), 'recalled_passages': len(passages),
                'complete_path': len(included) == count, 'mode': 'long'}
    coverage = memory['coverage']
    if 'summarized_messages' in coverage or content.get('reviewed_summaries'):
        expected['summarized_messages'] = len({row['source_id'] for row in content.get('reviewed_summaries', [])})
    require(all(type(coverage.get(key)) is type(value) for key, value in expected.items())
            and coverage == expected and snapshot['coverage'] == coverage, 'Writer coverage disagrees with the supplied source evidence.')
    if scope.bound:
        source = [{'id': scope.identities.node_id(node, scope.namespace), 'hash': digest(node['text'])} for node in scope.path]
        require(memory['source_fingerprint'] == digest(encode(source)), 'Writer memory belongs to another source path.')
    require(type(memory['input_allowance']) is int and type(memory['overhead_margin']) is int
            and memory['input_allowance'] > 0 and memory['overhead_margin'] >= 0,
            'Writer memory has invalid context accounting.')
    estimate = token_estimate(snapshot['prompt']['template'], content)
    require(estimate == snapshot['estimated_input_tokens'] and estimate + memory['overhead_margin'] <= memory['input_allowance'],
            'Writer context accounting differs from its frozen inputs.')
