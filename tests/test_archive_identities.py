"""Restores retain frozen source identities without duplicating paths per request."""
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION, PLAN_TABLES, canonical
from server.archives.identities import SourceIdentities, collect_identities, records
from server.archives.validate import parse_archive
from server.branches import path_nodes
from server.database import decode, encode, many
from server.errors import DomainError
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished, generate
from tests.test_history import append
from tests.test_memory import long_story, small_profile


def mapped_story(story, mapping):
    return {key: mapping[story[key]] for key in ('story_id', 'branch_id')}


def assert_path_identity(connection, story, original_story, ids):
    branch = connection.execute('SELECT head_id FROM branches WHERE id=?', (story['branch_id'],)).fetchone()
    path = path_nodes(connection, branch['head_id'])
    identities = SourceIdentities(connection, [row['id'] for row in path] + [story['story_id']])
    assert identities.matches(story['story_id'], original_story['story_id'])
    assert [identities.node_id(row, original_story['story_id']) for row in path] == ids
    assert [identities.node_id(row, story['story_id']) for row in path] == [row['id'] for row in path]


def test_repeated_restore_keeps_original_and_intermediate_epochs_and_frozen_requests(client):
    small_profile(client)
    story, ids = long_story(client)
    client.app.state.runner.provider = DraftProvider()
    run = generate(client, story, revision=len(ids))
    saved = finished(client, run['id'])['snapshot']
    file, first = backup(client, story)
    assert first['data']['archive_identities'] == []
    _, first_map = restore(client, file)
    imported = mapped_story(story, first_map)
    file, second = backup(client, imported)
    frozen = decode(second['data']['generations'][0]['snapshot'])
    assert frozen['content'] == saved['content'] and frozen['memory'] == saved['memory']
    assert set(row['record_id'] for row in second['data']['archive_identities']) <= set(records(second['data']))
    _, second_map = restore(client, file)
    again = mapped_story(imported, second_map)
    with client.app.state.database.connect() as connection:
        assert_path_identity(connection, again, story, ids)
        assert_path_identity(connection, again, imported, [first_map[item] for item in ids])
    _, third = backup(client, again)
    assert decode(third['data']['generations'][0]['snapshot'])['content'] == saved['content']
    assert len(third['data']['archive_identities']) == 2 * len(second['data']['archive_identities'])


def test_backfill_uses_durable_maps_without_writing_or_exporting_unrelated_records(client, story):
    first_node = append(client, story['branch_id'], 'The same words.', 0)
    second_node = append(client, story['branch_id'], 'The same words.', 1)
    outside = client.post('/api/stories', json={'title': 'Outside'}).json()
    outside_node = append(client, outside['branch_id'], 'Unrelated private words.', 0)
    file, _ = backup(client)
    _, first_map = restore(client, file)
    imported = mapped_story(story, first_map)
    file, _ = backup(client, imported)
    _, second_map = restore(client, file)
    again = mapped_story(imported, second_map)
    with client.app.state.database.connect(write=True) as connection:
        connection.execute('DELETE FROM archive_identities')
    _, document = backup(client, again)
    aliases = document['data']['archive_identities']
    assert aliases and outside_node not in {row['source_id'] for row in aliases}
    for original in (first_node, second_node):
        target = second_map[first_map[original]]
        assert any(row['record_id'] == target and row['source_id'] == original
                   and row['source_story_id'] == story['story_id'] for row in aliases)
    with client.app.state.database.connect() as connection:
        assert many(connection, 'SELECT * FROM archive_identities') == []


def test_new_descendant_and_branch_are_only_in_their_own_epochs(client, story):
    old = append(client, story['branch_id'], 'Shared source.', 0)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    imported = mapped_story(story, mapping)
    child = append(client, imported['branch_id'], 'Written after restore.', 1)
    fork = client.post('/api/branches/' + imported['branch_id'] + '/forks', json={
        'operation_id': uuid4().hex, 'expected_revision': 2, 'node_id': mapping[old],
        'name': 'Different choice', 'replacement': 'Changed source.',
    })
    assert fork.status_code == 201, fork.text
    file, document = backup(client, imported)
    assert not any(row['record_id'] == child for row in document['data']['archive_identities'])
    _, next_map = restore(client, file)
    with client.app.state.database.connect() as connection:
        row = dict(connection.execute('SELECT * FROM nodes WHERE id=?', (next_map[child],)).fetchone())
        identities = SourceIdentities(connection, [row['id']])
        assert identities.node_id(row, imported['story_id']) == child
        with pytest.raises(DomainError, match='lacks the original prose identity'):
            identities.node_id(row, story['story_id'])


@pytest.mark.parametrize('mutation', ['missing', 'kind', 'empty', 'wrong-type', 'extra', 'story', 'ambiguous', 'two-targets', 'current', 'global'])
def test_invalid_or_ambiguous_aliases_are_rejected(client, story, mutation):
    append(client, story['branch_id'], 'First.', 0)
    append(client, story['branch_id'], 'Second.', 1)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    _, document = backup(client, mapped_story(story, mapping))
    aliases = document['data']['archive_identities']
    item = next(row for row in aliases if row['record_kind'] == 'nodes')
    if mutation == 'missing':
        item['record_id'] = 'missing'
    elif mutation == 'kind':
        item['record_kind'] = 'stories'
    elif mutation == 'empty':
        item['source_id'] = ''
    elif mutation == 'wrong-type':
        item['source_id'] = []
    elif mutation == 'extra':
        item['invented'] = 'field'
    elif mutation == 'story':
        item['source_story_id'] = 'another-story'
    elif mutation == 'ambiguous':
        aliases.append({**item, 'source_id': 'second-identity'})
    elif mutation == 'two-targets':
        other = next(row for row in aliases if row['record_kind'] == 'nodes' and row['record_id'] != item['record_id'])
        other['source_id'] = item['source_id']
    elif mutation == 'current':
        item['source_story_id'] = mapping[story['story_id']]
    else:
        next(row for row in aliases if row['record_kind'] == 'stories')['source_story_id'] = 'not-global'
    with pytest.raises(DomainError):
        parse_archive(canonical(document))


def test_multiple_copies_can_share_original_ids_without_merging_stories(client, story):
    source = append(client, story['branch_id'], 'A source with two independent restored copies.', 0)
    file, _ = backup(client, story)
    _, a = restore(client, file)
    _, b = restore(client, file)
    _, workspace = backup(client)
    aliases = workspace['data']['archive_identities']
    assert {row['record_id'] for row in aliases if row['source_id'] == source} == {a[source], b[source]}
    with client.app.state.database.connect() as connection:
        assert_path_identity(connection, mapped_story(story, a), story, [source])
        assert_path_identity(connection, mapped_story(story, b), story, [source])


def test_original_v27_archive_upgrades_without_inventing_lost_identities(client, story):
    append(client, story['branch_id'], 'Original source.', 0)
    _, document = backup(client, story)
    document['version'] = 27
    from tests.archive_legacy import remove_v061_records
    remove_v061_records(document)
    del document['data']['archive_identities']
    for table in PLAN_TABLES:
        assert document['data'].pop(table) == []
    upgraded = parse_archive(canonical(document))
    assert upgraded['version'] == ARCHIVE_VERSION and upgraded['data']['archive_identities'] == []
    assert all(upgraded['data'][table] == [] for table in PLAN_TABLES)
    forged = deepcopy(document)
    forged['data']['archive_identities'] = []
    with pytest.raises(DomainError, match='Version 27'):
        parse_archive(canonical(forged))


def test_backfill_rejects_a_corrupt_cyclic_restore_map(client, story):
    node = append(client, story['branch_id'], 'Source.', 0)
    file, document = backup(client, story)
    with client.app.state.database.connect(write=True) as connection:
        connection.execute('INSERT INTO archive_restores VALUES (?,?,?,?)', ('cycle', file['id'], encode({node: node}), 'now'))
        with pytest.raises(DomainError, match='cyclic'):
            collect_identities(connection, document['data'])


def test_configuration_aliases_only_follow_actual_source_metadata(client, story):
    small_profile(client)
    client.app.state.runner.provider = DraftProvider()
    run = generate(client, story)
    detail = finished(client, run['id'])
    candidate = detail['candidates'][0]['id']
    response = client.post('/api/candidates/' + candidate + '/accept', json={'operation_id': uuid4().hex})
    assert response.status_code == 200, response.text
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    _, document = backup(client, mapped_story(story, mapping))
    aliases = document['data']['archive_identities']
    prompt = detail['snapshot']['prompt']['id']
    assert [row['source_id'] for row in aliases if row['record_kind'] == 'prompt_versions'] == [prompt]
    assert not any(row['record_kind'] in {'profiles', 'profile_versions', 'roll_table_versions'} for row in aliases)
    with client.app.state.database.connect() as connection:
        assert SourceIdentities(connection, [mapping[prompt]]).matches(mapping[prompt], prompt)
