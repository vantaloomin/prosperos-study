"""Canonical original prose evidence, shared without workflow dependencies."""
from server.branches import path_nodes
from server.memory.chunks import compile_chunks
from server.memory.index import connection_index


def source_chunks(connection, head_id):
    with connection_index(connection, True):
        return [(node, chunk) for node in path_nodes(connection, head_id) if node['role'] != 'ooc'
                for chunk in compile_chunks('message:' + node['id'], node['role'] + ' passage', node['text'])]


def source_evidence(node, chunk):
    return {**chunk.evidence(), 'node_id': node['id'], 'role': node['role']}
