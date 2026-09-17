"""Irregular topology and full-history private snapshots in a disposable DB.

Run python -m tests.branch_mature_fixture. No provider service is contacted.
"""
import json
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.database import encode, one
from server.main import create_app
from tests.branch_adversarial_fixture import shared_prefix, transition_metrics, validate_budget
from tests.branch_context_fixture import ContextSize, build_context, workspace_metrics
from tests.branch_topology_fixture import TopologySize
from tests.irregular_topology import IrregularSize, add_irregular
from tests.private_context_fixture import seed_private_history
from tests.topology_manifest import describe_fixture


class FixtureBudget:
    def __init__(self, max_bytes=512 * 1024 * 1024, max_seconds=360):
        self.max_bytes, self.max_seconds = max_bytes, max_seconds
        self.started = time.monotonic()

    def check(self, connection):
        pages = connection.execute('PRAGMA page_count').fetchone()[0]
        size = connection.execute('PRAGMA page_size').fetchone()[0]
        if pages * size > self.max_bytes or time.monotonic() - self.started > self.max_seconds:
            raise ValueError('Fixture resource ceiling exceeded; preserved for inspection, no further growth.')


def preflight(topology, context, irregular, width):
    topology.validate()
    context.validate()
    irregular.validate()
    validate_budget(topology, width)
    base = sum(topology.children ** level for level in range(topology.generations + 1))
    if base + topology.depth + topology.siblings + width + 12 + irregular.branch_ceiling() > 20000:
        raise ValueError('Combined fixture exceeds the 20,000-branch resource budget.')


def additional_transitions(paths):
    pairs = [('long_middle', 'irregular_shallow_long'), ('irregular_shallow_long', 'irregular_deeper_short'),
             ('irregular_deeper_short', 'irregular_empty'), ('long_middle', 'irregular_long_tail')]
    records = []
    for left, right in pairs:
        common = shared_prefix(paths[left]['node_ids'], paths[right]['node_ids'])
        for source, destination in ((left, right), (right, left)):
            records.append({'source': source, 'destination': destination, 'shared_messages': common,
                'source_responses': paths[source]['responses'], 'destination_responses': paths[destination]['responses'],
                'source_depth': paths[source]['depth'], 'destination_depth': paths[destination]['depth']})
    return records


def build_mature(client, topology=TopologySize(), context=ContextSize(), irregular=IrregularSize(), width=1000):
    preflight(topology, context, irregular, width)
    budget, database = FixtureBudget(), client.app.state.database
    base = build_context(client, topology, context, width)
    with database.connect() as connection:
        budget.check(connection)
        selected = {key: one(connection, 'SELECT * FROM branches WHERE id=?', (path['id'],))
                    for key, path in base['paths'].items()}
        profiles = [row[0] for row in connection.execute('SELECT p.id FROM profiles p JOIN profile_versions v ON p.latest_version_id=v.id '
                                                        "WHERE v.name LIKE 'Benchmark writer %' ORDER BY v.name")]
    extra, ragged = add_irregular(database, selected, topology.longest, irregular, budget)
    selected.update(extra)
    private = [seed_private_history(client, base['story_id'], selected[key]['id'], profiles,
                irregular.private_rounds, f'{index + 1:032x}', budget)
               for index, key in enumerate(('long_middle', 'long_remote', 'irregular_shallow_long'))]
    with database.connect(write=True) as connection:
        connection.execute('UPDATE stories SET title=? WHERE id=?',
                           ('Mature irregular benchmark · synthetic records', base['story_id']))
        budget.check(connection)
    result = describe_fixture(database, base['story_id'], selected, 'mature-irregular', asdict(topology))
    result.update(context_size=asdict(context), irregular=ragged, private_history=private,
                  historical_version_ids=base['historical_version_ids'], future_version_ids=base['future_version_ids'],
                  workflow=base['workflow'], other_stories=base['other_stories'], deep_parent_id=base['deep_parent_id'],
                  workspace=workspace_metrics(database, base['story_id']))
    result['transitions'] = transition_metrics(result['paths']) + additional_transitions(result['paths'])
    result['limitations'] = ['Synthetic results only. No provider services are contacted.',
        'Private requests freeze populated long histories. Earlier scene/review snapshots still precede the tree.',
        'Fixture counts do not prove browser responsiveness or arbitrary capacity.']
    return result


def main():
    folder = Path(__file__).resolve().parents[1] / 'test-results' / f'topology-mature-{uuid4().hex}'
    folder.mkdir(parents=True)
    path = folder / 'fixture.sqlite3'
    print(f'Building isolated fixture: {folder}', flush=True)
    with TestClient(create_app(path), headers={'x-roleplay-client': 'workspace'}) as client:
        result = build_mature(client)
    result.update(database=str(path), database_bytes=path.stat().st_size)
    (folder / 'manifest.json').write_text(encode(result), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('story_id', 'branch_count', 'max_depth', 'max_fanout',
                                                 'unique_nodes', 'database_bytes')}, indent=2))


if __name__ == '__main__':
    main()
