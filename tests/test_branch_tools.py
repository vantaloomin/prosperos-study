import json
from copy import deepcopy
from uuid import uuid4

from server.archives.format import V39_TABLES
from server.branch_tools.differences import text_changes
from server.branch_tools.lineage import StorySources
from server.database import decode
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_passage_revisions import passages, revise
from tests.test_profiles import make_profile
from tests.test_v07_manuscript import book_fixture


def branch(client, identity):
    return client.get(f'/api/branches/{identity}').json()


def fork(client, identity, node_id, replacement=None, name='Alternate telling'):
    response = client.post(f'/api/branches/{identity}/forks', json={
        'operation_id': uuid4().hex, 'expected_revision': branch(client, identity)['revision'],
        'node_id': node_id, 'replacement': replacement, 'name': name})
    assert response.status_code == 201, response.text
    return response.json()['branch_id']


def comparison(client, story, left, right):
    body = {'operation_id': uuid4().hex, 'left_branch_id': left, 'right_branch_id': right,
            'left_revision': branch(client, left)['revision'], 'right_revision': branch(client, right)['revision']}
    endpoint = f"/api/stories/{story['story_id']}/branch-comparisons"
    response = client.post(endpoint, json=body)
    assert response.status_code == 201, response.text
    assert client.post(endpoint, json=body).json() == response.json()
    return client.get(f"/api/branch-comparisons/{response.json()['id']}").json()


def search(client, story, query, **options):
    response = client.post(f"/api/stories/{story['story_id']}/branch-search", json={'query': query, **options})
    assert response.status_code == 200, response.text
    return response.json()


def curate(client, identity, favorite=False, archived=False):
    body = {'operation_id': uuid4().hex, 'expected_revision': branch(client, identity)['curation']['revision'],
            'favorite': favorite, 'archived': archived}
    response = client.put(f'/api/branches/{identity}/curation', json=body)
    assert response.status_code == 200, response.text
    assert client.put(f'/api/branches/{identity}/curation', json=body).json() == response.json()
    return response.json()


def test_curation_is_reversible_idempotent_and_independent_of_narrative_revision(client, story):
    identity = story['branch_id']
    original = branch(client, identity)
    current = curate(client, identity, favorite=True, archived=True)
    assert current == {'favorite': True, 'archived': True, 'revision': 1}
    after = branch(client, identity)
    assert {key: value for key, value in after.items() if key != 'curation'} == {
        key: value for key, value in original.items() if key != 'curation'}
    assert client.get(f"/api/stories/{story['story_id']}").json()['branches'][0]['curation'] == current
    response = client.put(f'/api/branches/{identity}/curation', json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'favorite': False, 'archived': False})
    assert response.status_code == 409
    assert curate(client, identity, favorite=True)['archived'] is False


def test_comparison_tracks_edited_lineage_and_preserves_exact_text_differences(client, story):
    identity = story['branch_id']
    nodes = passages(client, identity)
    other = fork(client, identity, nodes[1], 'Unique passage number one, revised.')
    result = comparison(client, story, identity, other)
    assert result['shared_prefix_count'] == 1 and result['shared_prefix_node_id'] == nodes[0]
    assert result['shared_source_count'] == 2
    assert result['counts'] == {'unchanged': 1, 'changed': 1, 'removed': 1}
    assert result['difference_indices'] == [1, 2]
    row = result['rows'][1]
    assert row['left']['original_node_id'] == row['right']['original_node_id'] == nodes[1]
    for side in ('left', 'right'):
        assert ''.join(part['text'] for part in row[side]['changes']) == row[side]['text']
    assert any(part['kind'] == 'added' and 'one' in part['text'] for part in row['right']['changes'])
    filtered = client.get(f"/api/branch-comparisons/{result['id']}?differences_only=true&limit=1").json()
    assert filtered['rows'][0]['index'] == 1 and filtered['next_offset'] == 2


def test_omissions_and_restored_suffixes_keep_their_source_identity(client, story):
    identity = story['branch_id']
    nodes = passages(client, identity)
    omitted = revise(client, identity, nodes[1])
    result = comparison(client, story, identity, omitted['branch_id'])
    assert result['counts'] == {'unchanged': 2, 'omitted': 1}
    row = result['rows'][1]['right']
    assert row['removed'] and row['text'] == '' and row['omitted_text'] == 'Unique passage number 1.'
    assert result['rows'][2]['left']['node_id'] != result['rows'][2]['right']['node_id']
    restored = revise(client, omitted['branch_id'], omitted['node_id'], 'restore')
    assert comparison(client, story, omitted['branch_id'], restored['branch_id'])['counts'] == {'unchanged': 2, 'restored': 1}
    assert comparison(client, story, identity, restored['branch_id'])['difference_indices'] == []


def test_saved_comparison_does_not_move_with_a_continued_branch(client, story):
    identity = story['branch_id']
    nodes = passages(client, identity)
    other = fork(client, identity, nodes[0])
    result = comparison(client, story, identity, other)
    append(client, other, 'Later writing excluded from saved comparison.', 0)
    after = client.get(f"/api/branch-comparisons/{result['id']}").json()
    assert after == result
    assert client.get(f"/api/stories/{story['story_id']}/branch-comparisons").json()[0]['id'] == result['id']


def test_search_groups_shared_sources_and_keeps_editions_and_omissions_distinct(client, story):
    identity = story['branch_id']
    nodes = passages(client, identity)
    omitted = revise(client, identity, nodes[1])
    other = fork(client, identity, nodes[1], 'Unique passage number 1 changed.')
    common = search(client, story, 'number 0')['results']
    assert len(common) == 1 and len(common[0]['occurrences']) == 3
    suffix = search(client, story, 'number 2')['results']
    assert len(suffix) == 1 and {item['branch_id'] for item in suffix[0]['occurrences']} == {identity, omitted['branch_id']}
    changed = search(client, story, 'number 1', include_removed=True)['results']
    assert len(changed) == 3 and sum(item['removed'] for item in changed) == 1
    assert {item['branch_id'] for row in changed for item in row['occurrences']} == {identity, omitted['branch_id'], other}
    assert len(search(client, story, 'number 1')['results']) == 2


def test_search_filters_archived_branches_and_does_not_merge_unrelated_identical_prose(client, story):
    identity = story['branch_id']
    other = fork(client, identity, None)
    append(client, identity, 'Identical wording, independent source.', 0)
    append(client, other, 'Identical wording, independent source.', 0)
    assert search(client, story, 'Identical')['total'] == 2
    curate(client, other, favorite=True, archived=True)
    assert search(client, story, 'Identical')['total'] == 1
    result = search(client, story, 'Identical', include_archived=True, branch_ids=[other])
    assert result['total'] == 1 and result['results'][0]['occurrences'][0]['archived']
    assert branch(client, other)['messages'][0]['text'].startswith('Identical')
    assert search(client, story, 'Identical', branch_ids=[other])['total'] == 0


def test_browsing_sibling_text_does_not_widen_writer_context(client, story):
    identity = story['branch_id']
    nodes = passages(client, identity)
    other = fork(client, identity, nodes[0])
    append(client, other, 'PRIVATE SIBLING secret answer.', 0)
    make_profile(client, 'Writer', primary=True)
    def context():
        with client.app.state.database.connect() as connection:
            return generation_snapshot(connection, identity, GenerateRequest(operation_id=uuid4().hex,
                expected_revision=3))[0]['content']
    before = context()
    assert search(client, story, 'PRIVATE SIBLING')['total'] == 1
    comparison(client, story, identity, other)
    curate(client, other, archived=True)
    assert context() == before and 'PRIVATE SIBLING' not in before


def test_comparison_and_search_reject_foreign_branches_and_stale_revisions(client, story):
    other = client.post('/api/stories', json={'title': 'Unrelated Story'}).json()
    body = {'operation_id': uuid4().hex, 'left_branch_id': story['branch_id'],
            'right_branch_id': other['branch_id'], 'left_revision': 0, 'right_revision': 0}
    endpoint = f"/api/stories/{story['story_id']}/branch-comparisons"
    assert client.post(endpoint, json=body).status_code == 400
    assert client.post(f"/api/stories/{story['story_id']}/branch-search", json={
        'query': 'anything', 'branch_ids': [other['branch_id']]}).status_code == 400
    local = fork(client, story['branch_id'], None)
    assert client.post(endpoint, json={**body, 'right_branch_id': local, 'right_revision': 99}).status_code == 409
    assert client.get(endpoint).json() == []


def test_archive_remaps_comparison_sources_and_preserves_curation_twice(client, story):
    nodes = passages(client, story['branch_id'])
    other = revise(client, story['branch_id'], nodes[1])['branch_id']
    result = comparison(client, story, story['branch_id'], other)
    curate(client, other, favorite=True, archived=True)
    file, document = backup(client, story)
    assert len(document['data']['branch_curation']) == len(document['data']['branch_comparisons']) == 1
    _, mapping = restore(client, file)
    compared = client.get(f"/api/branch-comparisons/{mapping[result['id']]}").json()
    assert compared['counts'] == result['counts']
    assert compared['right']['branch_id'] == mapping[other]
    assert compared['right']['head_id'] == mapping[result['right']['head_id']]
    assert compared['right']['curation'] == {'favorite': True, 'archived': True, 'revision': 1}
    assert compared['rows'][1]['left']['node_id'] == mapping[nodes[1]]
    restored = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    second, _ = backup(client, restored)
    _, second_map = restore(client, second)
    assert client.get(f"/api/branch-comparisons/{second_map[mapping[result['id']]]}").json()['counts'] == result['counts']


def test_archive_rejects_a_comparison_head_from_another_path(client, story):
    nodes = passages(client, story['branch_id'])
    other = fork(client, story['branch_id'], nodes[0])
    comparison(client, story, story['branch_id'], other)
    _, document = backup(client, story)
    document['data']['branch_comparisons'][0]['right_head_id'] = nodes[2]
    rejected = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert rejected.status_code == 400 and 'outside its source telling' in rejected.text


def test_v39_archive_upgrade_requires_original_record_groups(client, story):
    _, document = backup(client, story)
    old = deepcopy(document)
    old['version'] = 39
    old['data'] = {key: old['data'][key] for key in V39_TABLES}
    assert client.post('/api/archives/imports', json={'content': json.dumps(old)}).status_code == 201
    old['data']['branch_curation'] = []
    assert client.post('/api/archives/imports', json={'content': json.dumps(old)}).status_code == 400


def test_deep_source_intervals_and_large_unicode_differences_are_bounded():
    sources = object.__new__(StorySources)
    sources.nodes = {str(index): {'id': str(index), 'parent_id': str(index - 1) if index else None,
                                 'metadata': {}} for index in range(10001)}
    sources.roots = {}
    starts, ends = sources.intervals()
    assert starts['10000'] == 10000 and ends['0'] == ends['10000'] == 10001
    assert len(sources.path('10000')) == 10001
    left = 'A beginning. ' + '🕯 rain ' * 5000 + ' Last sentence.'
    right = 'A beginning. A different middle. Last sentence.'
    before, after, mode = text_changes(left, right)
    assert mode == 'common-edges'
    assert ''.join(item['text'] for item in before) == left
    assert ''.join(item['text'] for item in after) == right


def test_search_is_read_only_and_treats_query_characters_literally(client, story):
    append(client, story['branch_id'], 'A literal [plan] costs 10% — not a regex.', 0)
    with client.app.state.database.connect() as connection:
        before = '\n'.join(connection.iterdump())
    assert search(client, story, '[plan]')['results'][0]['match'] == '[plan]'
    assert search(client, story, '10%')['total'] == 1
    with client.app.state.database.connect() as connection:
        assert '\n'.join(connection.iterdump()) == before
        assert decode(connection.execute('SELECT metadata FROM nodes').fetchone()[0])['source'] == 'manual'


def test_archived_sources_preserve_book_selections_and_export_prose_after_restore(client, story):
    document, head = book_fixture(client, story)
    endpoint = f"/api/stories/{story['story_id']}/manuscript"
    before = client.get(endpoint + '/preview').json()
    export = client.post(endpoint + '/exports', json={'expected_revision': 1}).json()
    original_bytes = client.get(export['docx_url']).content
    other = fork(client, story['branch_id'], head, 'An entirely different ending.')
    comparison(client, story, story['branch_id'], other)
    curate(client, story['branch_id'], favorite=True, archived=True)
    assert client.get(endpoint).json()['document'] == document
    assert client.get(endpoint + '/preview').json() == before
    assert client.get(export['docx_url']).content == original_bytes
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/stories/{mapping[story['story_id']]}/manuscript/preview").json()
    def prose(preview):
        return [passage['text'] for chapter in preview['chapters'] for scene in chapter['scenes'] for passage in scene['passages']]
    assert prose(restored) == prose(before)
    assert branch(client, mapping[story['branch_id']])['curation']['archived']


def test_archive_rejects_non_object_comparison_labels(client, story):
    other = fork(client, story['branch_id'], None)
    comparison(client, story, story['branch_id'], other)
    _, document = backup(client, story)
    document['data']['branch_comparisons'][0]['labels'] = json.dumps(['left', 'right'])
    response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert response.status_code == 400 and 'Comparison labels are invalid' in response.text
