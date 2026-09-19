"""Optional independent semantic search with bounded foreground cache warming."""
import asyncio
import time

from server.errors import require
from server.memory.semantic_cache import (
    MAX_VECTOR_VALUES,
    cache_path,
    embedding_identity,
    read_vectors,
    write_vectors,
)
from server.memory.writer_recall import MAX_READS

LIMITS = {'max_new_sources': 64, 'batch_size': 16, 'max_sources': 4096, 'seconds': 30,
          'minimum_cosine': 0.2, 'max_vector_values': MAX_VECTOR_VALUES}


def ranking(sources, vectors, query):
    scores = [(round(sum(a * b for a, b in zip(query, vectors[source['id']]['vector'], strict=True)), 6), source)
              for source in sources]
    return [{'id': source['id'], 'sha256': source['sha256'], 'score': score}
            for score, source in sorted(scores, key=lambda row: (-row[0], row[1]['id']))
            if score >= LIMITS['minimum_cosine']][:MAX_READS]


async def request(provider, profile, texts, report, save, *, query=False):
    if profile['config'].get('embedding_input_format') == 'nomic-search-v1':
        prefix = 'search_query: ' if query else 'search_document: '
        texts = [prefix + text for text in texts]
    report['calls'] += 1
    save()
    result = await provider.embed(profile, texts)
    require(len(result['vectors']) == len(texts), 'Embedding batch did not cover its inputs.', 502)
    report['usage'].append(result.get('usage', {}))
    return result


def rank_queries(sources, vectors, queries):
    return [ranking(sources, vectors, query) for query in queries]


async def discover(provider, profile, sources, queries, report, save):
    require(len(sources) <= LIMITS['max_sources'], 'Semantic source limit reached; keyword search retained.', 409)
    path = cache_path(provider)
    identity = {**report['identity'], 'saved_profile_id': profile.get('id')}
    vectors = await asyncio.to_thread(read_vectors, path, identity, sources)
    report['cache_hits'] = len(vectors)
    missing = [source for source in sources if source['id'] not in vectors]
    pending = missing[:LIMITS['max_new_sources']]
    for offset in range(0, len(pending), LIMITS['batch_size']):
        batch = pending[offset:offset + LIMITS['batch_size']]
        result = await request(provider, profile, [source['text'] for source in batch], report, save)
        rows = {source['id']: {'vector': vector, 'model': result['model']}
                for source, vector in zip(batch, result['vectors'], strict=True)}
        vectors.update(rows)
        report['new_sources'] += len(batch)
        require(sum(len(row['vector']) for row in vectors.values()) <= MAX_VECTOR_VALUES,
                'Semantic vectors exceed the memory limit; keyword search retained.', 409)
        await asyncio.to_thread(write_vectors, path, identity, batch, rows)
    require(len(vectors) == len(sources), 'Semantic cache is still warming; keyword search retained.', 409)
    result = await request(provider, profile, queries, report, save, query=True)
    models = {row['model'] for row in vectors.values()} | {result['model']}
    dimensions = {len(row['vector']) for row in vectors.values()} | {len(vector) for vector in result['vectors']}
    require(len(models) == len(dimensions) == 1, 'Embedding model or dimensions changed; keyword search retained.', 409)
    ranked = await asyncio.to_thread(rank_queries, sources, vectors, result['vectors'])
    report.update(actual_model=result['model'], dimensions=dimensions.pop(), rankings=ranked, status='completed')


async def semantic_search(provider, profile, snapshot, queries, receipt, save):
    settings = snapshot['writer_recall'].get('semantic', {})
    if not settings.get('enabled') or not queries:
        return None
    report = {'version': 1, 'status': 'preparing', 'identity': embedding_identity(profile), 'calls': 0,
              'cache_hits': 0, 'new_sources': 0, 'total_sources': len(snapshot['writer_recall']['sources']),
              'rankings': [], 'usage': []}
    receipt['semantic'] = report
    started = time.monotonic()
    try:
        require(profile['config']['provider'] in {'local', 'compatible', 'openai'} and bool(report['identity']['model'].strip()),
                'No supported embedding model is configured; keyword search retained.', 409)
        async with asyncio.timeout(min(LIMITS['seconds'], profile['config']['timeout_seconds'])):
            await discover(provider, profile, snapshot['writer_recall']['sources'], queries, report, save)
    except asyncio.CancelledError:
        report['status'] = 'cancelled'
        raise
    except Exception as error:
        report.update(status='fallback', rankings=[], reason=getattr(error, 'message',
                      'Semantic search was unavailable or exceeded its limits; keyword search retained.'))
    finally:
        report['seconds'] = time.monotonic() - started
        save()
    return report
