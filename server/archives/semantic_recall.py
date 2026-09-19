"""Validate recorded semantic rankings as derived hints, never accepted facts."""
import math

from server.errors import require
from server.memory.semantic_cache import embedding_identity
from server.memory.semantic_recall import LIMITS
from server.memory.writer_recall import MAX_READS


def validate_rankings(report, queries, sources):
    rankings = report.get('rankings')
    require(isinstance(rankings, list), 'Invalid semantic rankings.')
    if report['status'] != 'completed':
        require(not rankings, 'Incomplete semantic search cannot supply rankings.')
        return
    require(len(rankings) == len(queries), 'Semantic rankings differ from their queries.')
    require(type(report.get('dimensions')) is int and 1 <= report['dimensions'] <= 8192
            and isinstance(report.get('actual_model'), str) and 0 < len(report['actual_model']) <= 300,
            'Invalid semantic model result.')
    for ranking in rankings:
        require(isinstance(ranking, list) and len(ranking) <= MAX_READS, 'Semantic ranking exceeds its limit.')
        for row in ranking:
            require(isinstance(row, dict) and set(row) == {'id', 'sha256', 'score'}, 'Invalid semantic result.')
            require(row['id'] in sources and row['sha256'] == sources[row['id']]['sha256'],
                    'Semantic result is outside the frozen permitted sources.')
            require(type(row['score']) in {int, float} and math.isfinite(row['score'])
                    and LIMITS['minimum_cosine'] <= row['score'] <= 1.000001, 'Invalid semantic score.')
        require(len({row['id'] for row in ranking}) == len(ranking)
                and ranking == sorted(ranking, key=lambda row: (-row['score'], row['id'])), 'Invalid semantic rank order.')


def validate_semantic(snapshot, profile, report, queries):
    if report is None:
        return
    archive = snapshot['writer_recall']
    require(archive.get('semantic', {}).get('enabled') is True and report.get('version') == 1
            and report.get('identity') == embedding_identity(profile), 'Semantic receipt differs from its frozen policy or model.')
    require(report.get('status') in {'preparing', 'cancelled', 'fallback', 'completed'}, 'Invalid semantic status.')
    sources = {source['id']: source for source in archive['sources']}
    require(report.get('total_sources') == len(sources), 'Semantic source count changed.')
    for key, ceiling in [('calls', 5), ('cache_hits', len(sources)), ('new_sources', LIMITS['max_new_sources'])]:
        require(type(report.get(key)) is int and 0 <= report[key] <= ceiling, 'Invalid semantic preparation accounting.')
    require(report['cache_hits'] + report['new_sources'] <= len(sources), 'Semantic cache accounting exceeds the source scope.')
    if report['status'] == 'completed':
        require(report['calls'] >= 1 and report['cache_hits'] + report['new_sources'] == len(sources),
                'Completed semantic search did not cover every permitted source.')
    validate_rankings(report, queries, sources)
