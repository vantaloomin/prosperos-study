"""Reproduce retired v5/v3 request construction only for compatibility tests.

The real production selectors no longer insert neighboring passages. Keep this
explicit fixture policy so archive/replay checks exercise historical requests.
The pre-withdrawal literal receipts are also retained independently as JSON.
"""
from server.memory import packet, recall, source_packet
from server.memory.chunks import compile_chunks
from server.memory.control_packet import excluded_chunks
from server.memory.neighbors import with_following_context
from server.memory.retrieval import Corpus
from server.memory.scoped_aids import chunk_key


def writer_neighbors(original, context, included, settings, aids=None):
    hits = original(context, included, settings, aids)
    corpus = recall.history_corpus(context['history'], included, aids, excluded_chunks(context))
    order = [(f"message:{node['id']}", len(node['text'])) for node in context['history']]
    return with_following_context(hits, corpus, order)


def specialist_neighbors(original, context, included, settings, aids):
    hits = original(context, included, settings, aids)
    blocked = excluded_chunks(context)
    chunks = [chunk for index, source in enumerate(context['sources'])
              if source_packet.eligible(source) and index not in included
              for chunk in compile_chunks(str(index), source['title'], source['text'], source['kind'])
              if chunk_key(source['id'], chunk.start, chunk.end, chunk.digest) not in blocked]
    order = [(str(index), len(source['text'])) for index, source in enumerate(context['sources'])]
    return with_following_context(hits, Corpus(chunks), order)


def retired_receipt(original, *args):
    result = original(*args)
    result['algorithm'] = 'prospero-source-reviewed-v4' if result['receipt_version'] == 2 else 'prospero-source-lexical-v3'
    return result


def enable_retired_policy(monkeypatch):
    original_writer, original_sources, original_receipt = recall.recall_candidates, source_packet.candidates, source_packet.receipt
    monkeypatch.setattr(packet, 'ALGORITHM', 'prospero-lexical-v5')
    monkeypatch.setattr(packet, 'recall_candidates', lambda *args: writer_neighbors(original_writer, *args))
    monkeypatch.setattr(source_packet, 'candidates', lambda *args: specialist_neighbors(original_sources, *args))
    monkeypatch.setattr(source_packet, 'receipt', lambda *args: retired_receipt(original_receipt, *args))
