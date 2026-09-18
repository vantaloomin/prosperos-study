"""Bounded discovery and exact read ranges over one already-scoped archive."""
import hashlib
import json
import re

from server.errors import DomainError, require
from server.memory.chunks import compile_chunks
from server.memory.recall import with_aid
from server.memory.retrieval import Corpus
from server.memory.scoped_aids import aid_reference
from server.memory.side_archive import permitted_sources

PAGE_SIZE = 8


def command(output):
    kind, separator, payload = output.strip().partition(':')
    if not separator or kind not in {'SEARCH_SOURCES', 'LIST_SOURCES', 'READ_SOURCES'}:
        return None
    try:
        value = json.loads(payload)
    except ValueError as error:
        raise DomainError('The collaborator returned an unreadable archive request. No Story operation was performed.', 502) from error
    if kind == 'READ_SOURCES':
        require(isinstance(value, list) and 0 < len(value) <= 8, 'Read 1–8 archived passages per pass.', 502)
        return kind, [read_target(item) for item in value]
    require(isinstance(value, dict), 'Archive search and listing require an object.', 502)
    allowed = {'offset', 'query'} if kind == 'SEARCH_SOURCES' else {'offset'}
    require(set(value) <= allowed, 'This archive request has unsupported fields.', 502)
    offset = value.get('offset', 0)
    require(type(offset) is int and 0 <= offset <= 1000000, 'Invalid archive result offset.', 502)
    query = value.get('query', '')
    require(isinstance(query, str) and len(query) <= 1000, 'Search queries must be at most 1,000 characters.', 502)
    return kind, {'query': query, 'offset': offset}


def read_target(value):
    if isinstance(value, str):
        return {'id': value, 'offset': 0, 'length': 1600}
    require(isinstance(value, dict) and set(value) <= {'id', 'offset', 'length'}, 'Invalid archive read range.', 502)
    target = {'id': value.get('id'), 'offset': value.get('offset', 0), 'length': value.get('length', 1600)}
    require(isinstance(target['id'], str) and type(target['offset']) is int and target['offset'] >= 0
            and type(target['length']) is int and 1 <= target['length'] <= 2400, 'Invalid archive read range.', 502)
    return target


def excerpt(source, start, length):
    require(start < len(source['text']) or start == len(source['text']) == 0, 'The requested range is beyond this frozen source.', 502)
    end = min(start + length, len(source['text']))
    text = source['text'][start:end]
    return {'id': source['id'], 'title': source['title'][:240], 'authority': source.get('authority', ''),
            'text': text, 'start': start, 'end': end, 'total_chars': len(source['text']),
            'has_more': end < len(source['text']), 'sha256': hashlib.sha256(text.encode()).hexdigest(),
            **aid_reference(source)}


def discovery_excerpt(source, start, matched):
    text = source['text'][start:start + 2400]
    for term in sorted(matched, key=len, reverse=True):
        match = re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, re.IGNORECASE)
        if match:
            return excerpt(source, start + max(0, match.start() - 60), 240)
    return excerpt(source, start, 240)


class SourceArchive:
    def __init__(self, snapshot):
        self.documents = permitted_sources(snapshot)
        self.by_id = {item['id']: item for item in self.documents}
        self.corpus = None

    def search(self, query='', offset=0):
        ranked = self.rank(query) if query.strip() else [(item['id'], 0, ()) for item in self.documents]
        selected = ranked[offset:offset + PAGE_SIZE]
        results = [discovery_excerpt(self.by_id[source_id], start, matched) for source_id, start, matched in selected]
        return {'query': query, 'offset': offset, 'total': len(ranked),
                'next_offset': offset + len(results) if offset + len(results) < len(ranked) else None, 'results': results}

    def rank(self, query):
        if self.corpus is None:
            self.corpus = Corpus([with_aid(chunk, item.get('reviewed_aid')) for item in self.documents
                                  for chunk in compile_chunks(item['id'], item['title'], item['text'])])
        # Discovery exposes all lexical matches; the writer's relevance cutoff must not hide an exact rare term.
        hits = self.corpus.search(query, limit=len(self.corpus.chunks), threshold=0)
        seen, results = set(), []
        for hit in hits:
            if hit.matched and hit.chunk.source_id not in seen:
                seen.add(hit.chunk.source_id)
                results.append((hit.chunk.source_id, hit.chunk.start, hit.matched))
        return results

    def read(self, targets):
        require(all(target['id'] in self.by_id for target in targets),
                'The collaborator requested a source outside this permitted frozen archive. No operation was performed.', 502)
        return [excerpt(self.by_id[target['id']], target['offset'], target['length']) for target in targets]
