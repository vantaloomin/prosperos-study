from dataclasses import replace

from server.memory.chunks import compile_chunks
from server.memory.control_packet import excluded_chunks
from server.memory.retrieval import Corpus


def history_corpus(history, included, summary_aids=None, excluded=()):
    aids = summary_aids or {}
    chunks = [chunk for node in history if node['id'] not in included and node['role'] != 'ooc'
              for chunk in compile_chunks(f"message:{node['id']}", f"{node['role']} passage", node['text'])]
    return Corpus([with_aid(chunk, aids.get(chunk.id)) for chunk in chunks if chunk.id not in excluded])


def with_aid(chunk, aid):
    if not aid or aid['source_sha256'] != chunk.digest:
        return chunk
    return replace(chunk, aliases=(aid['summary'], *aid['topics'], *aid['aliases']))


def current_query(context):
    recent = [node['text'] for node in context['history'][-3:] if node['role'] != 'ooc']
    return context['direction'] + '\n' + '\n'.join(recent)[-6000:]


def latest_query(context):
    # A long repetitive preceding passage must not drown out the newest clue.
    latest = next((node['text'] for node in reversed(context['history']) if node['role'] != 'ooc'), '')
    return latest[-6000:]


def thread_hits(corpus, continuity):
    # Only accepted unresolved threads are cues. Suggestions never enter this collection.
    threads = [entry for entry in continuity.get('entries', [])
               if entry['kind'] in {'thread', 'plan'} and entry['status'] == 'active']
    hits = []
    for entry in threads[-4:]:
        matches = corpus.search(entry['subject'] + ' ' + entry['text'], limit=1)
        hits.extend(replace(hit, reason=f"Open thread: {entry['subject']}") for hit in matches)
    return hits


def recall_candidates(context, included, settings, summary_aids=None):
    corpus = history_corpus(context['history'], included, summary_aids, excluded_chunks(context))
    directed = corpus.search(context['direction'], limit=settings.recall_limit)
    current = corpus.search(current_query(context), limit=settings.recall_limit * 2)
    latest = [replace(hit, reason='Related to the latest accepted passage')
              for hit in corpus.search(latest_query(context), limit=1)]
    recent = unique_hits([*latest, *current])
    threads = thread_hits(corpus, context.get('continuity', {})) if settings.open_threads else []
    # Preserve immediate relevance while leaving room for an old unresolved promise.
    hits = unique_hits([*directed[:4], *recent[:2], *threads, *directed[4:], *recent[2:]])
    return hits


def unique_hits(hits):
    seen = set()
    unique = []
    for hit in hits:
        if hit.chunk.id not in seen:
            seen.add(hit.chunk.id)
            unique.append(hit)
    return unique
