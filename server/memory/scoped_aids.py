"""Frozen retrieval aids bound to exact accepted source spans."""
import hashlib

from server.errors import require
from server.memory.chunks import compile_chunks
from server.memory.summary_models import SummaryItem


def chunk_key(source_id, start, end, digest):
    return f'{source_id}@{start}:{end}:{digest[:12]}'


def source_aid(source, chunk, aids):
    key = chunk_key(source['id'], chunk.start, chunk.end, chunk.digest)
    aid = (aids or {}).get(key)
    return aid if aid and aid.get('source_sha256') == chunk.digest else None


def validate_aid(aid, text):
    require(isinstance(aid, dict), 'Invalid reviewed memory aid.')
    require(set(aid) == set(SummaryItem.model_fields) | {'version_id', 'source_sha256'}, 'Invalid reviewed memory fields.')
    item = SummaryItem.model_validate({key: aid[key] for key in SummaryItem.model_fields})
    require(isinstance(aid['version_id'], str) and bool(aid['version_id'])
            and aid['source_sha256'] == hashlib.sha256(text.encode()).hexdigest(), 'Reviewed memory refers to different source bytes.')
    require(all(quote in text for quote in item.quotes), 'Reviewed memory quotations leave their source.')


def annotated_documents(source_id, title, text, aids):
    """Align aided documents to canonical spans, retaining whitespace between chunks."""
    chunks = compile_chunks(source_id, title, text)
    if not any(chunk.id in aids for chunk in chunks):
        return None
    documents, cursor = [], 0
    for chunk in chunks:
        if cursor < chunk.start:
            documents.append({'text': text[cursor:chunk.start]})
        document = {'text': chunk.text}
        aid = aids.get(chunk.id)
        if aid and aid['source_sha256'] == chunk.digest:
            document.update(reviewed_aid=aid, memory_source={key: value for key, value in chunk.evidence().items()
                                                           if key in {'id', 'source_id', 'start', 'end', 'sha256'}})
        documents.append(document)
        cursor = chunk.end
    if cursor < len(text):
        documents.append({'text': text[cursor:]})
    return documents


def aid_reference(document):
    if not document.get('reviewed_aid'):
        return {}
    return {'recall_aid': {'version_id': document['reviewed_aid']['version_id'],
                           'chunk_id': document['memory_source']['id'],
                           'source_sha256': document['reviewed_aid']['source_sha256']}}


def validate_document_aid(document):
    if 'reviewed_aid' not in document:
        require('memory_source' not in document, 'A memory source has no reviewed aid.')
        return
    validate_aid(document['reviewed_aid'], document['text'])
    source = document.get('memory_source', {})
    start, end, digest = source.get('start'), source.get('end'), source.get('sha256')
    require(type(start) is int and type(end) is int and 0 <= start < end
            and end - start == len(document['text']), 'Invalid reviewed memory source range.')
    source_id = source.get('source_id', '')
    require(source_id.startswith('message:') and ':' + source_id + ':' in document['id']
            and digest == document['reviewed_aid']['source_sha256']
            and source.get('id') == chunk_key(source_id, start, end, digest), 'Reviewed memory changed source identity.')


def validate_frozen_aids(sources, aids):
    require(isinstance(aids, dict), 'Invalid frozen reviewed memory.')
    chunks = {chunk.id: chunk for source in sources
              if source['kind'] in {'accepted', 'previous'} and source['title'] != 'ooc contribution'
              for chunk in compile_chunks(source['id'], source['title'], source['text'])}
    require(set(aids) <= chunks.keys(), 'Frozen reviewed memory leaves its accepted sources.')
    for key, aid in aids.items():
        validate_aid(aid, chunks[key].text)
