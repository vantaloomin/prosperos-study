import re
from difflib import SequenceMatcher
from itertools import zip_longest


def aligned_rows(sources, left, right):
    left_ids = [sources.original(node['id']) for node in left]
    right_ids = [sources.original(node['id']) for node in right]
    result = []
    for tag, start_a, end_a, start_b, end_b in SequenceMatcher(None, left_ids, right_ids, autojunk=False).get_opcodes():
        pairs = zip(left[start_a:end_a], right[start_b:end_b], strict=True) if tag == 'equal' else zip_longest(left[start_a:end_a], right[start_b:end_b])
        for before, after in pairs:
            result.append({'index': len(result), 'status': change_kind(before, after), 'left': before, 'right': after})
    return result


def change_kind(left, right):
    if left is None:
        return 'added'
    if right is None:
        return 'removed'
    before, after = bool(left['metadata'].get('removed')), bool(right['metadata'].get('removed'))
    if before != after:
        return 'restored' if before else 'omitted'
    return 'unchanged' if left['text'] == right['text'] and left['role'] == right['role'] else 'changed'


def text_changes(left, right):
    if left == right:
        return [{'kind': 'equal', 'text': left}], [{'kind': 'equal', 'text': right}], 'words'
    if len(left) + len(right) > 24000:
        return edge_changes(left, right)
    before = re.findall(r'\s+|\w+|[^\w\s]', left)
    after = re.findall(r'\s+|\w+|[^\w\s]', right)
    first, second = [], []
    for kind, a, b, c, d in SequenceMatcher(None, before, after, autojunk=True).get_opcodes():
        if a != b:
            first.append({'kind': 'equal' if kind == 'equal' else 'removed', 'text': ''.join(before[a:b])})
        if c != d:
            second.append({'kind': 'equal' if kind == 'equal' else 'added', 'text': ''.join(after[c:d])})
    return first, second, 'words'


def edge_changes(left, right):
    prefix, suffix = 0, 0
    while prefix < min(len(left), len(right)) and left[prefix] == right[prefix]:
        prefix += 1
    while suffix < min(len(left), len(right)) - prefix and left[-suffix - 1] == right[-suffix - 1]:
        suffix += 1
    def pieces(value, kind):
        end = len(value) - suffix
        return [{'kind': 'equal', 'text': value[:prefix]}, {'kind': kind, 'text': value[prefix:end]},
                {'kind': 'equal', 'text': value[end:]}]
    return pieces(left, 'removed'), pieces(right, 'added'), 'common-edges'


def row_view(sources, row):
    left = sources.source(row['left']) if row['left'] else None
    right = sources.source(row['right']) if row['right'] else None
    first, second, mode = text_changes(left['text'] if left else '', right['text'] if right else '')
    return {'index': row['index'], 'status': row['status'],
            'left': {**left, 'changes': first} if left else None,
            'right': {**right, 'changes': second} if right else None, 'diff_mode': mode}
