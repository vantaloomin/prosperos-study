"""Validate frozen search scope and exact per-candidate writer inputs on import."""
from server.archives.identities import SourceIdentities, records
from server.archives.recall_groups import group_context
from server.archives.relationships import validate_annotation_aids
from server.archives.semantic_recall import validate_semantic
from server.archives.summary_context import validate_summary_context
from server.archives.writer_memory import validate_snapshot
from server.archives.writer_sources import WriterScope
from server.branches import path_nodes
from server.database import decode, encode
from server.errors import require
from server.memory.writer_recall import (
    MAX_OUTPUT_CHARS,
    digest,
    freeze_sources,
    preparation_profile,
)
from server.memory.writer_recall_packet import final_snapshot, pack_recall
from server.memory.writer_recall_runner import parse_queries


def validate_recall_archive(connection, snapshot, identities):
    archive = snapshot.get('writer_recall')
    if archive is None:
        return
    require(archive.get('version') in {1, 2, 3, 4, 5, 6}, 'Unsupported prewriting archive version.')
    content = decode(snapshot['content'])
    policy = content.get('story', {}).get('settings', {}).get('memory', {})
    require('knowledge_lens' not in snapshot and policy.get('mode') == 'long' and policy.get('writer_recall') is True,
            'Prewriting recall is outside the frozen writer scope.')
    scope = WriterScope(path_nodes(connection, snapshot['branch']['head_id']), snapshot['branch'], content, identities)
    require(scope.bound, 'Prewriting recall requires verifiable original source identities.')
    history = [{**node, 'id': identities.node_id(node, scope.namespace)} for node in scope.path]
    if archive['version'] >= 2:
        content = group_context(connection, snapshot, scope, content, archive)
    annotations = validate_annotation_aids(connection, snapshot, scope, identities) if archive['version'] >= 4 else None
    require(archive == freeze_sources({**content, 'history': history}, version=archive['version'],
                                     summary_aids=archive.get('summary_aids'), annotation_aids=annotations),
            'Prewriting recall archive differs from its permitted exact sources or frozen limits.')


def validate_recall_receipt(connection, snapshot, profile, receipt, identities):
    require('writer_recall' in snapshot, 'A prewriting receipt has no frozen source archive.')
    require(receipt.get('version') == snapshot['writer_recall']['version'] and receipt.get('base_sha256') == digest(snapshot['content'])
            and receipt.get('sources_sha256') == snapshot['writer_recall']['sources_sha256']
            and receipt.get('config') == preparation_profile(profile)['config'],
            'A prewriting receipt differs from its frozen inputs or profile.')
    if receipt['version'] >= 2:
        require(receipt.get('archive_sha256') == digest(encode(snapshot['writer_recall'])),
                'A prewriting receipt changed its frozen groups or search descriptions.')
    require(isinstance(receipt.get('output'), str) and len(receipt['output']) <= MAX_OUTPUT_CHARS
            and type(receipt.get('calls')) is int and receipt['calls'] in {0, 1}, 'Invalid prewriting call accounting.')
    status = receipt.get('status')
    require(status in {'preparing', 'cancelled', 'completed', 'fallback'}, 'Invalid prewriting receipt status.')
    semantic = receipt.get('semantic')
    if semantic is not None:
        validate_semantic(snapshot, profile, semantic, parse_queries(receipt['output']))
    if status in {'preparing', 'cancelled'}:
        require('final_input' not in receipt, 'Incomplete prewriting cannot claim a final writer input.')
        return
    queries = parse_queries(receipt['output']) if status == 'completed' else []
    expected = pack_recall(snapshot, queries, semantic if status == 'completed' else None)
    require(all(receipt.get(key) == value for key, value in expected.items()),
            'Prewriting selection or final input differs from its bounded source search.')
    final = final_snapshot(snapshot, receipt['final_input'])
    validate_snapshot(connection, final, identities)
    policy = decode(final['content'])['story']['settings']['memory']
    validate_summary_context(connection, final, final['branch'], policy)


def validate_writer_recall(connection, data):
    identities = SourceIdentities(connection, records(data))
    snapshots = {row['id']: decode(row['snapshot']) for row in data['generations']}
    for snapshot in snapshots.values():
        validate_recall_archive(connection, snapshot, identities)
    for row in data['assessment_runs']:
        validate_recall_archive(connection, decode(row['snapshot'])['writer_snapshot'], identities)
    candidates = {row['id']: row for row in data['candidates']}
    for row in [*data['candidates'], *data['generation_attempts']]:
        candidate = candidates[row['candidate_id']] if 'candidate_id' in row else row
        receipt = decode(row['usage']).get('writer_recall')
        if receipt is not None:
            validate_recall_receipt(connection, snapshots[candidate['generation_id']],
                                    decode(candidate['profile']), receipt, identities)
