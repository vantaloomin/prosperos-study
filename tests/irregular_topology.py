"""Seeded, uneven continuations at every generation; sizes are fixture budgets."""
import random
from dataclasses import asdict, dataclass

from server.background.storage import bind, state_id
from server.branches import path_nodes
from tests.branch_stress_fixture import fork_at
from tests.performance_fixture import add_pairs


@dataclass(frozen=True)
class IrregularSize:
    seed: int = 9162026
    generations: int = 8
    parents_per_level: int = 48
    max_children: int = 4
    max_continuation: int = 24
    private_rounds: int = 3

    def validate(self):
        ceilings = {'generations': 10, 'parents_per_level': 64, 'max_children': 6,
                    'max_continuation': 50, 'private_rounds': 5}
        if any(not 1 <= getattr(self, key) <= limit for key, limit in ceilings.items()):
            raise ValueError('Irregular fixture exceeds its resource budget.')
        if self.generations < 3 or self.parents_per_level < 2 or self.max_children < 3:
            raise ValueError('Irregular fixture needs three generations and differing child counts.')

    def branch_ceiling(self):
        return self.generations * self.parents_per_level * self.max_children + 8


def child_at(connection, source, nodes, shared, extra, name):
    head = nodes[shared - 1]['id'] if shared else None
    child = fork_at(connection, source, head, name)
    bind(connection, child['id'], state_id(connection, head, node=True))
    add_pairs(connection, child, 0, extra, name)
    return child


def split_size(nodes, choice):
    return {'empty': 0, 'early': min(2, len(nodes)), 'middle': len(nodes) // 2,
            'latest': len(nodes)}[choice]


def next_parents(frontier, size, rng):
    remaining = frontier[2:]
    return frontier[:2] + rng.sample(remaining, min(len(remaining), size.parents_per_level - 2))


def grow_level(connection, parents, level, size, rng, records):
    following = []
    for ordinal, source in enumerate(parents):
        count = (1, size.max_children)[ordinal] if ordinal < 2 else rng.randrange(size.max_children + 1)
        nodes = path_nodes(connection, source['head_id'])
        for child_index in range(count):
            name = f'Irregular {level:02d}.{len(records) + 1:04d}'
            point = ('empty', 'early', 'middle', 'latest')[(level + child_index) % 4]
            extra = (0, 1, min(3, size.max_continuation), size.max_continuation)[rng.randrange(4)]
            shared = split_size(nodes, point)
            child = child_at(connection, source, nodes, shared, extra, name)
            records.append({'id': child['id'], 'name': name, 'parent_name': source['name'],
                'level': level, 'fork_point': point, 'shared_messages': shared,
                'continuation_messages': extra * 2, 'messages': shared + extra * 2,
                'responses': sum(item['role'] == 'assistant' for item in nodes[:shared]) + extra})
            following.append(child)
    return following


def pinned_extremes(connection, selected, longest):
    root, deep, long = (selected[key] for key in ('root', 'deepest', 'long_middle'))
    early = path_nodes(connection, root['head_id'])[:2]
    short = child_at(connection, deep, early, 2, 1, 'Irregular deep short')
    shorter = child_at(connection, short, path_nodes(connection, short['head_id']), 2, 0, 'Irregular deeper short')
    shallow = child_at(connection, root, early, 2, longest - 1, 'Irregular shallow long')
    tail = child_at(connection, long, path_nodes(connection, long['head_id']), longest * 2, 2, 'Irregular long shared prefix')
    middle = child_at(connection, shallow, path_nodes(connection, shallow['head_id']), longest, 12, 'Irregular middle continuation')
    empty = child_at(connection, middle, [], 0, 0, 'Irregular empty grandchild')
    return {'irregular_deep_short': short, 'irregular_deeper_short': shorter,
            'irregular_shallow_long': shallow, 'irregular_long_tail': tail,
            'irregular_middle': middle, 'irregular_empty': empty}


def add_irregular(database, selected, longest, size, budget):
    size.validate()
    rng, records = random.Random(size.seed), []
    frontier = [selected['left_parent'], selected['deepest']]
    with database.connect(write=True) as connection:
        for level in range(1, size.generations + 1):
            frontier = grow_level(connection, next_parents(frontier, size, rng), level, size, rng, records)
            budget.check(connection)
        pinned = pinned_extremes(connection, selected, longest)
    pinned['irregular_leaf'] = frontier[-1]
    return pinned, {'algorithm': 'python-random-v1', 'size': asdict(size), 'branches': records,
                    'additional_branches': len(records) + len(pinned) - 1}
