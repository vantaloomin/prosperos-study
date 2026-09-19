"""Rank fusion of independent lexical and semantic candidate lists."""
from server.memory.chunks import Chunk
from server.memory.retrieval import Corpus, Hit
from server.memory.writer_recall import MAX_READS

RANK_OFFSET = 60


def hybrid_hits(sources, queries, semantic):
    chunks = {row['id']: Chunk(row['id'], row['source_id'], row['title'], row['text'], row['start'], row['end'],
                              row['sha256'], row['kind']) for row in sources}
    corpus = Corpus(list(chunks.values()))
    lexical = [corpus.search(query, limit=MAX_READS) for query in queries]
    ranks = [[hit.chunk.id for hit in hits] for hits in lexical] + [
        [row['id'] for row in ranking] for ranking in semantic['rankings']]
    totals, matched = {}, {}
    for ranking in ranks:
        for rank, identity in enumerate(ranking, 1):
            totals[identity] = totals.get(identity, 0) + 1 / (RANK_OFFSET + rank)
    for hits in lexical:
        for hit in hits:
            matched.setdefault(hit.chunk.id, set()).update(hit.matched)
    ordered = sorted(totals, key=lambda identity: (-totals[identity], identity))[:MAX_READS]
    return [Hit(chunks[identity], totals[identity], tuple(sorted(matched.get(identity, set()))),
                'Combined keyword and semantic search') for identity in ordered]
