"""Validate proximity receipts without reranking or guessing semantic relations."""
import re

from server.errors import require
from server.memory.chunks import compile_chunks
from server.memory.control_packet import excluded_chunks
from server.memory.neighbors import NEIGHBOR_REASON, following_chunk
from server.memory.scoped_aids import chunk_key
from server.memory.source_packet import eligible

NEIGHBOR_ALGORITHMS = {'prospero-source-lexical-v3', 'prospero-source-reviewed-v4'}
ANCHOR = re.compile(r'([0-9]+)@[0-9]+:[0-9]+:[0-9a-f]{12}')


def anchor_chunk(sources, value):
    match = ANCHOR.fullmatch(value) if isinstance(value, str) else None
    require(match is not None, 'Invalid neighboring evidence anchor.')
    index = int(match[1])
    require(index < len(sources) and eligible(sources[index]), 'Neighbor anchor leaves accepted scope.')
    source = sources[index]
    found = next((chunk for chunk in compile_chunks(str(index), source['title'], source['text'], source['kind'])
                  if chunk.id == value), None)
    require(found is not None, 'Neighbor anchor differs from its exact original source.')
    return found


def contains_anchor(item, anchor):
    if item['index'] != int(anchor.source_id) or 'adjacent_to' in item:
        return False
    return 'start' not in item or (item['start'], item['end'], item['sha256']) == (anchor.start, anchor.end, anchor.digest)


def validate_neighbor(context, selection, item):
    sources = context['sources']
    anchor = anchor_chunk(sources, item['adjacent_to'])
    require(any(contains_anchor(row, anchor) for row in selection), 'Neighboring evidence omitted its anchor.')
    require('reviewed_aid' not in item and item.get('reason') == NEIGHBOR_REASON,
            'Proximity cannot claim reviewed-search provenance or a verified correction.')
    source = sources[item['index']]
    chunks = compile_chunks(str(item['index']), source['title'], source['text'], source['kind'])
    child = next((chunk for chunk in chunks if (chunk.start, chunk.end, chunk.digest)
                  == (item['start'], item['end'], item['sha256'])), None)
    require(child is not None, 'Neighbor is not an exact compiled passage.')
    order = [(str(index), len(source['text'])) for index, source in enumerate(sources)]
    require(following_chunk(anchor, (child,), order) == child,
            'Neighboring evidence crosses a gap or source boundary.')
    key = chunk_key(source['id'], child.start, child.end, child.digest)
    require(key not in excluded_chunks(context), 'Neighboring evidence was explicitly excluded.')


def validate_neighbors(context, selection, algorithm):
    neighbors = [item for item in selection if 'adjacent_to' in item]
    require(len(neighbors) <= 1, 'Too many neighboring evidence excerpts.')
    if neighbors:
        require(algorithm in NEIGHBOR_ALGORITHMS and 'start' in neighbors[0],
                'Unsupported neighboring evidence receipt.')
        validate_neighbor(context, selection, neighbors[0])
