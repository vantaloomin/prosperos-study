import pytest

from tests.branch_context_fixture import ContextSize, build_context
from tests.branch_topology_fixture import TopologySize
from tests.test_branch_topology import assert_path


def test_combined_context_preserves_early_canon_versions_and_workspace_isolation(client):
    size = ContextSize(lorebooks=3, characters=2, lore_characters=1200, continuity_entries=6,
                       assessments=2, sidebar_turns=1, other_stories=2, other_responses=12)
    topology = TopologySize(generations=2, children=2, depth=8, siblings=5, longest=25, payload_characters=2000)
    fixture = build_context(client, topology, size, deep_width=5)
    long_path = fixture['paths']['long_middle']
    branch = assert_path(client, long_path)
    assert set(item['version_id'] for item in branch['attachments']) == set(fixture['historical_version_ids'])
    assert all(item['update_available'] for item in branch['attachments'])
    canon = client.get(f"/api/branches/{branch['id']}/continuity").json()
    assert len(canon['entries']) == 6
    assert {item['kind'] for item in canon['entries']} == {'fact', 'knowledge', 'thread'}
    assert [commit['id'] for commit in canon['commits']] == [fixture['workflow']['early_receipt']['commit_id']]
    empty = client.get(f"/api/branches/{fixture['paths']['deep_empty']['id']}/continuity").json()
    assert empty == {'entries': [], 'commits': []}
    later = client.get(f"/api/branches/{fixture['paths']['root']['id']}/continuity").json()
    assert len(later['entries']) == 8 and len(later['commits']) == 2
    workspace = fixture['workspace']
    assert workspace['counts']['candidates'] == 4 and workspace['counts']['side_turns'] == 1
    assert workspace['frozen_snapshots']['assessment_runs']['records'] == 2
    assert workspace['frozen_snapshots']['scene_runs']['records'] == 2
    assert workspace['counts']['review_jobs'] > 0 and workspace['counts']['mechanic_opportunities'] > 0
    assert workspace['unrelated_messages'] == 48
    assert not any('UNRELATED STORY' in node['text'] for node in branch['messages'])
    other = client.get(f"/api/branches/{fixture['other_stories'][0]['branch_id']}").json()
    assert set(item['version_id'] for item in other['attachments']) == set(fixture['future_version_ids'])


@pytest.mark.parametrize('values', [{'lorebooks': 0}, {'assessments': 13}, {'other_stories': 25}, {'sidebar_turns': 3}])
def test_context_fixture_rejects_out_of_budget_workloads(values):
    with pytest.raises(ValueError, match='resource budget'):
        ContextSize(**values).validate()


def test_invalid_topology_does_not_create_context_or_workflow_records(client):
    database = client.app.state.database
    with database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM stories').fetchone()[0] == 0
    with pytest.raises(ValueError, match='20,000'):
        build_context(client, TopologySize(generations=12))
    with database.connect() as connection:
        assert all(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
                   for table in ('stories', 'profiles', 'assets', 'scene_runs', 'assessment_runs'))
