"""Validated, non-executable interchange for the disposable chunk index."""

def dump_chunks(chunks):
    return [{**chunk.evidence(), 'digest': chunk.digest, 'aliases': chunk.aliases} for chunk in chunks]


def load_chunks(rows):
    from server.memory.chunks import Chunk
    if not isinstance(rows, list) or len(rows) > 50000:
        raise ValueError('Invalid cached chunks')
    result = []
    for row in rows:
        aliases = row['aliases']
        if not isinstance(aliases, list) or any(not isinstance(item, str) for item in aliases):
            raise ValueError('Invalid aliases')
        chunk = Chunk(**{**{key: value for key, value in row.items() if key != 'sha256'}, 'aliases': tuple(aliases)})
        if not valid_chunk(chunk):
            raise ValueError('Invalid cached span')
        result.append(chunk)
    return tuple(result)


def valid_chunk(chunk):
    import hashlib
    strings = (chunk.id, chunk.source_id, chunk.title, chunk.text, chunk.digest, chunk.kind)
    return (all(isinstance(value, str) for value in strings)
            and isinstance(chunk.start, int) and isinstance(chunk.end, int)
            and 0 <= chunk.start < chunk.end and len(chunk.text) == chunk.end - chunk.start
            and hashlib.sha256(chunk.text.encode('utf-8')).hexdigest() == chunk.digest)


def load_counts(rows):
    if not isinstance(rows, list):
        raise ValueError('Invalid term counts')
    result = []
    for term, count in rows:
        if not isinstance(term, str) or type(count) is not int or not 1 <= count <= 1000000:
            raise ValueError('Invalid term count')
        result.append((term, count))
    return tuple(result)
