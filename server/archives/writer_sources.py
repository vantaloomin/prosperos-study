"""Check exact writer evidence without selecting or reranking it again."""
import hashlib
import math
from bisect import bisect_right
from collections import defaultdict

from server.archives.remap import REFERENCES
from server.database import encode
from server.errors import require
from server.memory.chunks import compile_chunks
from server.memory.control_packet import excluded_chunks, excluded_nodes
from server.memory.neighbors import NEIGHBOR_REASON


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def same_fields(live, frozen, identities, bound):
    if set(live) != set(frozen):
        return False
    for key, value in live.items():
        if key in REFERENCES and isinstance(value, str):
            if bound and not identities.matches(value, frozen[key]):
                return False
        elif value != frozen[key]:
            return False
    return True


def node_signature(node):
    return encode({key: value for key, value in node.items() if key not in REFERENCES and key != 'metadata'} | {
        'metadata': {key: value for key, value in node['metadata'].items() if key not in REFERENCES}})


class WriterScope:
    def __init__(self, path, branch, content, identities):
        self.path, self.identities = path, identities
        history = content['history']
        require(isinstance(history, list) and bool(history) == bool(path), 'Writer history has no required current passage.')
        self.namespace = history[-1]['story_id'] if history else branch['story_id']
        self.bound = identities.matches(branch['story_id'], self.namespace)
        self.positions = {}
        if self.bound:
            self.positions = {identities.node_id(node, self.namespace): index for index, node in enumerate(path)}
        self.signatures = defaultdict(list)
        for index, node in enumerate(path):
            self.signatures[node_signature(node)].append(index)

    def whole_history(self, content):
        included, previous = [], -1
        history = content['history']
        require(len({node['id'] for node in history}) == len(history), 'Writer history duplicates a source identity.')
        for index, frozen in enumerate(history):
            position = self.whole_position(frozen, previous, index == len(history) - 1)
            live = self.path[position]
            require(same_fields({k: v for k, v in live.items() if k != 'metadata'},
                                {k: v for k, v in frozen.items() if k != 'metadata'}, self.identities, self.bound)
                    and same_fields(live['metadata'], frozen['metadata'], self.identities, self.bound),
                    'A whole writer passage differs from its archived original.')
            require(frozen['story_id'] == self.namespace and position > previous, 'Writer history crosses Stories or changes source order.')
            included.append(position)
            previous = position
        required = {i for i, node in enumerate(self.path) if node['role'] == 'ooc'}
        required.update({len(self.path) - 1} if self.path else set())
        require(required <= set(included), 'Writer history omitted required author notes or its current passage.')
        excluded = excluded_nodes(content)
        require(all(i in required or row['id'] not in excluded for i, row in zip(included, history, strict=True)),
                'Writer history includes an explicitly excluded older passage.')
        return included

    def whole_position(self, frozen, previous, last):
        if self.bound:
            position = self.positions.get(frozen['id'])
            require(position is not None, 'A writer passage is outside its archived branch.')
            return position
        # This proves only an ordered text/metadata match, not original identity.
        choices = self.signatures.get(node_signature(frozen), [])
        index = bisect_right(choices, previous)
        require(index < len(choices), 'A legacy writer passage has no matching archived source.')
        if last:
            require(len(self.path) - 1 in choices, 'A legacy writer request changed its current passage.')
            return len(self.path) - 1
        return choices[index]

    def chunk(self, item):
        number = item.get('passage_number')
        require(type(number) is int and 1 <= number <= len(self.path), 'A recalled passage has an invalid source position.')
        node = self.path[number - 1]
        source = item['source_id']
        require(node['role'] != 'ooc' and isinstance(source, str) and source.startswith('message:'), 'Recalled evidence is not accepted story prose.')
        if self.bound:
            require(source == 'message:' + self.identities.node_id(node, self.namespace), 'A recalled passage names another source.')
        chunks = compile_chunks(source, node['role'] + ' passage', node['text'])
        chunk = next((chunk for chunk in chunks if chunk.id == item['id']), None)
        require(chunk is not None, 'A recalled passage changed its source range or hash.')
        return chunk


def validate_selection(items, selected):
    require(isinstance(selected, list) and len(items) == len(selected), 'A writer receipt has missing selections.')
    by_id = {item['id']: item for item in items}
    require(len(by_id) == len(items) and len({row['id'] for row in selected}) == len(selected), 'A writer selection duplicates evidence.')
    for row in selected:
        item = by_id.get(row['id'])
        require(item is not None and row['source_id'] == item['source_id'], 'A writer selection names different evidence.')
        score, terms = row['score'], row['matched_terms']
        require(type(score) in {int, float} and math.isfinite(score) and score >= 0
                and isinstance(terms, list) and all(isinstance(term, str) and bool(term) for term in terms),
                'A writer selection has invalid ranking metadata.')
        require(isinstance(row['reason'], str) and bool(row['reason']), 'A writer selection has no reason.')
        if 'reason' in item:
            require(row['reason'] == item['reason'] and row.get('adjacent_to') == item.get('adjacent_to'),
                    'A writer selection changed its stated reason or adjacency.')


def validate_passages(scope, content, memory, included):
    items = content.get('recalled_passages', [])
    positions = []
    blocked = excluded_chunks(content)
    for item in items:
        chunk = scope.chunk(item)
        expected = {**chunk.evidence(), 'reason': item['reason'], 'passage_number': item['passage_number']}
        if 'adjacent_to' in item:
            expected['adjacent_to'] = item['adjacent_to']
        require(item == expected and item['id'] not in blocked, 'Recalled writer text differs from exact eligible source bytes.')
        require(item['passage_number'] - 1 not in included, 'Writer evidence duplicates a whole included passage.')
        positions.append((item['passage_number'], item['start'], item['end']))
    require(positions == sorted(positions) and all(a[0] != b[0] or a[2] <= b[1] for a, b in zip(positions, positions[1:])),
            'Recalled passages are reordered, duplicated or overlapping.')
    validate_selection(items, memory['selected'])
    validate_neighbors(scope, items, memory)
    return items


def validate_neighbors(scope, items, memory):
    by_id = {item['id']: item for item in items}
    for item in items:
        if 'adjacent_to' not in item:
            continue
        require(memory['algorithm'].startswith('prospero-lexical-v5'), 'A current receipt cannot claim retired neighbor selection.')
        anchor = by_id.get(item['adjacent_to'])
        require(anchor is not None and 'adjacent_to' not in anchor, 'A legacy neighbor has no independent anchor.')
        within = anchor['source_id'] == item['source_id'] and anchor['end'] == item['start']
        following = (item['passage_number'] == anchor['passage_number'] + 1 and item['start'] == 0
                     and anchor['end'] == len(scope.path[anchor['passage_number'] - 1]['text']))
        require((within or following) and item['reason'] == NEIGHBOR_REASON, 'A legacy neighbor is not adjacent to its evidence.')
