from collections import Counter

import pytest

from server.background.storage import state_id
from server.database import Database, one
from tests.branch_adversarial_fixture import build_adversarial
from tests.branch_context_fixture import ContextSize
from tests.branch_mature_fixture import FixtureBudget, build_mature
from tests.branch_topology_fixture import TopologySize
from tests.irregular_topology import IrregularSize, add_irregular
from tests.test_background import fork
from tests.test_branch_topology import assert_path
from tests.topology_manifest import describe_fixture


def sizes():
    return (TopologySize(generations=2, children=2, depth=8, siblings=5, longest=24, payload_characters=1000),
            ContextSize(lorebooks=2, characters=2, lore_characters=500, continuity_entries=6,
                        assessments=1, sidebar_turns=1, other_stories=2, other_responses=12),
            IrregularSize(generations=4, parents_per_level=6, max_continuation=6, private_rounds=2))


def test_irregular_context_has_unequal_internal_paths_and_full_history_private_snapshots(client):
    topology, context, irregular = sizes()
    fixture = build_mature(client, topology, context, irregular, width=5)
    records = fixture['irregular']['branches']
    counts = Counter(item['parent_name'] for item in records)
    internal = [item for item in records if counts[item['name']]]
    assert {item['level'] for item in internal} == {1, 2, 3}
    assert len({item['continuation_messages'] for item in internal}) >= 3
    assert {1, 4} <= set(counts.values())
    for level in range(1, irregular.generations + 1):
        assert {item['fork_point'] for item in records if item['level'] == level} == {'empty', 'early', 'middle', 'latest'}
    paths = fixture['paths']
    for key in ('long_middle', 'long_remote', 'irregular_shallow_long', 'irregular_deeper_short', 'irregular_long_tail', 'irregular_empty'):
        assert_path(client, paths[key])
    assert paths['irregular_deeper_short']['depth'] > paths['irregular_shallow_long']['depth']
    assert paths['irregular_deeper_short']['responses'] == 1
    assert paths['irregular_shallow_long']['responses'] == 24
    assert paths['irregular_long_tail']['responses'] == 26
    assert paths['irregular_empty']['messages'] == 0
    for private in fixture['private_history']:
        assert [item['input_messages'] for item in private['rounds']] == [48, 49]
        assert private['rounds'][1]['input_utf8_bytes'] > private['rounds'][0]['input_utf8_bytes']
    assert fixture['workspace']['counts']['background_jobs'] == 12
    assert fixture['workspace']['counts']['node_background'] == 6
    assert not any(fixture['workspace']['pending_jobs'].values())
    chosen = fixture['private_history'][0]
    story = {'story_id': fixture['story_id'], 'branch_id': chosen['branch_id']}
    early_fork = fork(client, story, paths['long_middle']['node_ids'][1])
    later_fork = fork(client, story, chosen['rounds'][0]['node_id'])
    with client.app.state.database.connect() as connection:
        assert state_id(connection, early_fork) is None
        assert state_id(connection, later_fork) == chosen['rounds'][0]['updated_state']


def test_irregular_topology_is_reproducible_with_new_storage_ids(tmp_path):
    topology, _, irregular = sizes()
    results = []
    for label in ('first', 'second'):
        database = Database(tmp_path / f'{label}.sqlite3')
        baseline = build_adversarial(database, topology, 5)
        with database.connect() as connection:
            selected = {key: one(connection, 'SELECT * FROM branches WHERE id=?', (value['id'],))
                        for key, value in baseline['paths'].items()}
        extra, manifest = add_irregular(database, selected, topology.longest, irregular, FixtureBudget())
        final = describe_fixture(database, baseline['story_id'], extra, 'test-irregular', {})
        results.append((final, [{key: value for key, value in row.items() if key != 'id'} for row in manifest['branches']]))
    assert results[0][0]['story_id'] != results[1][0]['story_id']
    assert results[0][0]['content_sha256'] == results[1][0]['content_sha256']
    assert results[0][1] == results[1][1]


@pytest.mark.parametrize('changes', [{'generations': 2}, {'max_children': 2}, {'parents_per_level': 65}, {'private_rounds': 6}])
def test_invalid_irregular_budget_creates_no_story_or_provider_history(client, changes):
    topology, context, _ = sizes()
    with pytest.raises(ValueError, match='fixture'):
        build_mature(client, topology, context, IrregularSize(**changes), width=5)
    assert client.get('/api/stories').json() == []
    assert client.get('/api/profiles').json()['profiles'] == []


def test_runtime_budget_stops_growth_without_deleting_prior_data(client, story):
    database = client.app.state.database
    with database.connect() as connection:
        with pytest.raises(ValueError, match='preserved for inspection'):
            FixtureBudget(max_bytes=1).check(connection)
    assert client.get(f"/api/branches/{story['branch_id']}").status_code == 200
