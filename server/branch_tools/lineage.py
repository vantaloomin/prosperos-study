"""Browse source editions without granting them to a writing role."""
from collections import defaultdict

from server.database import decode, many
from server.errors import require


class StorySources:
    def __init__(self, connection, story_id):
        self.nodes = {row['id']: {**row, 'metadata': decode(row['metadata'])}
                      for row in many(connection, 'SELECT * FROM nodes WHERE story_id=? ORDER BY created_at,id', (story_id,))}
        self.roots = {}

    def original(self, identity):
        visited, seen = [], set()
        current = identity
        while current not in self.roots:
            require(current in self.nodes and current not in seen, 'A passage has unavailable or cyclic source lineage.')
            seen.add(current)
            visited.append(current)
            metadata = self.nodes[current]['metadata']
            parent = metadata.get('original_node_id') or metadata.get('replaces')
            if not parent:
                self.roots[current] = current
                break
            current = parent
        root = self.roots[current]
        self.roots.update({node: root for node in visited})
        return root

    def path(self, head):
        result, seen = [], set()
        while head:
            require(head in self.nodes and head not in seen, 'This telling has unavailable or cyclic ancestry.')
            seen.add(head)
            result.append(self.nodes[head])
            head = self.nodes[head]['parent_id']
        return list(reversed(result))

    def source(self, node):
        metadata = node['metadata']
        removed = bool(metadata.get('removed'))
        prior_id = metadata.get('original_node_id') if removed else None
        prior = self.nodes.get(prior_id)
        return {'node_id': node['id'], 'original_node_id': self.original(node['id']),
                'role': node['role'], 'text': node['text'], 'removed': removed,
                'omitted_text': prior['text'] if prior else None, 'created_at': node['created_at']}

    def intervals(self):
        children = defaultdict(list)
        for row in self.nodes.values():
            children[row['parent_id']].append(row['id'])
        starts, ends, stack = {}, {}, [(identity, False) for identity in reversed(children[None])]
        while stack:
            identity, closing = stack.pop()
            if closing:
                ends[identity] = len(starts)
                continue
            require(identity not in starts, 'The Story contains cyclic passage ancestry.')
            starts[identity] = len(starts)
            stack.append((identity, True))
            stack.extend((child, False) for child in reversed(children[identity]))
        require(len(starts) == len(self.nodes), 'The Story contains disconnected passage ancestry.')
        return starts, ends
