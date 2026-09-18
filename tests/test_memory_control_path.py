"""Author-decision ancestry must stay exact without loading narrative payloads."""
from unittest.mock import patch

from server.branches import path_nodes
from server.database import one
from server.memory.control_state import control_view, eligible_version, path_node_ids
from tests.test_memory_controls import entry, evidence, save
from tests.test_story_summaries import fork, setup


def legacy_eligible_version(connection, version_id, head_id):
    path = {node['id'] for node in path_nodes(connection, head_id)}
    while version_id:
        row = one(connection, 'SELECT * FROM memory_control_versions WHERE id=?', (version_id,))
        if row['node_id'] in path:
            return row, path
        version_id = row['parent_id']
    return None, path


def test_branch_without_author_decisions_never_reads_ancestry(client):
    story, _ = setup(client)
    with client.app.state.database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],))
        statements = []
        connection.set_trace_callback(statements.append)
        assert control_view(connection, branch) == {'version_id': None, 'applied_version_id': None, 'entries': []}
        assert eligible_version(connection, None, branch['head_id']) == (None, set())
        assert not any('nodes' in sql.casefold() for sql in statements)


def test_projected_ids_exclude_siblings_other_stories_and_empty_heads(client):
    story, _ = setup(client)
    another, _ = setup(client)
    branch = client.get('/api/branches/' + story['branch_id']).json()
    edited = fork(client, story['branch_id'], branch['head_id'], 'Different past.')
    with client.app.state.database.connect() as connection:
        rows = path_nodes(connection, branch['head_id'])
        statements = []
        connection.set_trace_callback(statements.append)
        result = path_node_ids(connection, branch['head_id'])
        assert result == {row['id'] for row in rows}
        assert path_node_ids(connection, None) == set()
        assert not any('text' in sql.casefold() or 'metadata' in sql.casefold() or 'select *' in sql.casefold()
                       for sql in statements)
        connection.set_trace_callback(None)
        for branch_id in (edited, another['branch_id']):
            head = one(connection, 'SELECT head_id FROM branches WHERE id=?', (branch_id,))['head_id']
            assert not result & path_node_ids(connection, head)


def test_applied_decisions_and_historical_forks_match_full_path_oracle(client):
    from tests.test_memory_maintenance import append
    story, _ = setup(client)
    branch_id = story['branch_id']
    head = client.get('/api/branches/' + branch_id).json()['head_id']
    first = save(client, branch_id, [entry(evidence(client, branch_id))])
    later = append(client, branch_id, 'Elin learns something new.')
    save(client, branch_id, [entry(evidence(client, branch_id), stance='knows')])
    earlier = fork(client, branch_id, head)
    revised = fork(client, branch_id, later, 'The lesson never happens.')
    with client.app.state.database.connect() as connection:
        for identity in (branch_id, earlier, revised):
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (identity,))
            actual = control_view(connection, branch)
            with patch('server.memory.control_state.eligible_version', legacy_eligible_version):
                assert control_view(connection, branch) == actual
            if identity != branch_id:
                assert actual['applied_version_id'] == first
