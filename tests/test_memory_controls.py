from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.generation_models import GenerateRequest
from server.generation_preparation import prepare_writer
from tests.archive_legacy import remove_controls
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished, generate
from tests.test_memory import small_profile
from tests.test_memory_maintenance import append
from tests.test_reviews import ReviewProvider, finished_review, start
from tests.test_scenes import SceneProvider, get_plan, run_stage
from tests.test_scoped_memory_aids import create_scene
from tests.test_story_summaries import TEXT, fork, setup, writer_snapshot


def view(client, branch_id):
    response = client.get('/api/branches/' + branch_id + '/memory-controls')
    assert response.status_code == 200, response.text
    return response.json()


def evidence(client, branch_id):
    return client.get('/api/branches/' + branch_id + '/summary-sources').json()['items']


def entry(sources, kind='knowledge', stance='unaware', **extra):
    return {'id': uuid4().hex, 'kind': kind, 'stance': stance, 'subject': 'Elin',
            'text': 'Elin has not tested whether the key works.', 'enabled': True,
            'source_ids': [source['id'] for source in sources], **extra}


def save(client, branch_id, entries, **extra):
    current = view(client, branch_id)
    body = {'operation_id': uuid4().hex, 'expected_revision': current['revision'],
            'expected_version_id': current['version_id'], 'entries': entries, **extra}
    response = client.put('/api/branches/' + branch_id + '/memory-controls', json=body)
    assert response.status_code == 200, response.text
    assert client.put('/api/branches/' + branch_id + '/memory-controls', json=body).json() == response.json()
    return response.json()['id']


def test_decisions_are_versioned_without_story_changes_or_same_head_sibling_leak(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    before = client.get('/api/branches/' + branch_id).json()
    sibling = fork(client, branch_id, before['head_id'])
    authored = entry(evidence(client, branch_id))
    first = save(client, branch_id, [authored])
    assert client.get('/api/branches/' + branch_id).json() == before
    assert view(client, sibling)['entries'] == []
    inherited = fork(client, branch_id, before['head_id'])
    assert view(client, inherited)['version_id'] == first
    second = save(client, branch_id, [{**authored, 'stance': 'uncertain'}])
    assert view(client, inherited)['entries'][0]['stance'] == 'unaware'
    assert view(client, branch_id)['version_id'] == second
    history = client.get('/api/branches/' + branch_id + '/memory-control-history').json()
    assert [row['id'] for row in history] == [second, first]
    assert client.get('/api/branches/' + sibling + '/memory-control-history/' + first).status_code == 404


def test_fork_before_decision_and_past_edit_follow_the_correct_control_lineage(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    opening = client.get('/api/branches/' + branch_id).json()['head_id']
    first_entry = entry(evidence(client, branch_id))
    first = save(client, branch_id, [first_entry])
    later = append(client, branch_id, 'Elin tests the key and learns it opens the gate.')
    sources = evidence(client, branch_id)
    save(client, branch_id, [entry([sources[-1]], stance='knows')])
    past = fork(client, branch_id, opening)
    edited = fork(client, branch_id, later, 'Elin never tries the key.')
    assert view(client, past)['version_id'] == view(client, edited)['version_id'] == first
    replaced = fork(client, branch_id, opening, 'A different opening with no key.')
    assert view(client, replaced)['entries'] == []


def test_stale_controls_and_unrelated_evidence_fail_before_publication(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    authored = entry(evidence(client, branch_id))
    save(client, branch_id, [authored])
    stale = {'operation_id': uuid4().hex, 'expected_revision': 1, 'expected_version_id': None, 'entries': []}
    assert client.put('/api/branches/' + branch_id + '/memory-controls', json=stale).status_code == 409
    current = view(client, branch_id)
    invalid = {**stale, 'operation_id': uuid4().hex, 'expected_version_id': current['version_id'],
               'entries': [{**authored, 'source_ids': ['message:outside@0:2:000000000000']}]}
    assert client.put('/api/branches/' + branch_id + '/memory-controls', json=invalid).status_code == 409
    invalid['entries'] = [{**authored, 'kind': 'conflict', 'stance': 'intentional'}]
    assert client.put('/api/branches/' + branch_id + '/memory-controls', json=invalid).status_code == 422
    assert len(client.get('/api/branches/' + branch_id + '/memory-control-history').json()) == 1


def test_pins_keep_exact_evidence_exclusions_apply_even_when_long_history_fits(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    first = evidence(client, branch_id)[0]
    append(client, branch_id, 'The market closes.')
    save(client, branch_id, [entry([first], 'emphasis', 'exclude')])
    snapshot = writer_snapshot(client, branch_id)
    content = decode(snapshot['content'])
    assert TEXT not in snapshot['content'] and content['history'][-1]['text'] == 'The market closes.'
    assert not snapshot['coverage']['complete_path']
    save(client, branch_id, [entry([first], 'emphasis', 'pin')])
    pinned = decode(writer_snapshot(client, branch_id)['content'])
    assert pinned['author_memory']['entries'][0]['sources'][0]['text'] == TEXT
    head = evidence(client, branch_id)[-1]
    save(client, branch_id, [entry([head], 'emphasis', 'exclude')])
    required = decode(writer_snapshot(client, branch_id)['content'])
    assert required['history'][-1]['text'] == 'The market closes.'


def test_full_history_retains_originals_and_disabled_decisions_leave_future_inputs(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    authored = entry(evidence(client, branch_id), 'emphasis', 'exclude')
    append(client, branch_id, 'A later moment.')
    save(client, branch_id, [authored])
    current = client.get('/api/stories/' + story['story_id']).json()
    client.put('/api/stories/' + story['story_id'], json={'title': current['title'], 'premise': current['premise'],
        'expected_revision': current['revision'], 'settings': {**current['settings'], 'memory': {'mode': 'full'}}})
    assert TEXT in writer_snapshot(client, branch_id)['content']
    save(client, branch_id, [{**authored, 'enabled': False}])
    assert 'author_memory' not in decode(writer_snapshot(client, branch_id)['content'])


def test_knowledge_conflict_and_author_emphasis_remain_distinct_required_instructions(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    append(client, branch_id, 'Ivo says the key has never opened that gate.')
    sources = evidence(client, branch_id)
    entries = [entry([sources[0]], stance='believes'), entry(sources, 'conflict', 'intentional', subject='Two accounts'),
               entry([sources[1]], 'emphasis', 'motif', subject='Uncertainty')]
    save(client, branch_id, entries)
    packet = decode(writer_snapshot(client, branch_id)['content'])['author_memory']
    assert [item['stance'] for item in packet['entries']] == ['believes', 'intentional', 'motif']
    assert 'separate from accepted continuity and Canon' in packet['authority']
    assert len(packet['entries'][1]['sources']) == 2
    small_profile(client, limit=2048)
    huge = [{**entry(sources, subject=f'Control {index}'), 'text': 'Evidence must remain visible. ' * 35} for index in range(15)]
    save(client, branch_id, huge)
    with pytest.raises(DomainError, match='Required story context'):
        writer_snapshot(client, branch_id)


def test_new_decision_invalidates_prepared_writer_without_advancing_the_branch(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    branch = client.get('/api/branches/' + branch_id).json()
    body = GenerateRequest(operation_id=uuid4().hex, expected_revision=branch['revision'])
    with client.app.state.database.connect() as connection:
        prepared = prepare_writer(connection, branch_id, body)
    save(client, branch_id, [entry(evidence(client, branch_id))])
    with client.app.state.database.connect(write=True) as connection:
        with pytest.raises(DomainError, match='while context was being assembled'):
            prepared.validate(connection, body)
    assert client.get('/api/branches/' + branch_id).json() == branch


def test_frozen_scene_and_accepted_draft_fork_keep_their_original_decisions(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    authored = entry(evidence(client, branch_id))
    version = save(client, branch_id, [authored])
    scene_id = create_scene(client, story)
    client.app.state.runner.provider = DraftProvider()
    generation = finished(client, generate(client, story, revision=1)['id'])
    save(client, branch_id, [{**authored, 'stance': 'knows'}])
    client.app.state.scene_runner.provider = SceneProvider()
    stage = run_stage(client, scene_id, 'scene-beats')[0]
    assert decode(stage['snapshot']['content'])['author_memory']['entries'][0]['stance'] == 'unaware'
    response = client.post('/api/candidates/' + generation['candidates'][0]['id'] + '/accept', json={
        'operation_id': uuid4().hex, 'as_new_branch': True})
    assert response.status_code == 200, response.text
    accepted = view(client, response.json()['branch_id'])
    assert accepted['version_id'] == version and accepted['entries'][0]['stance'] == 'unaware'
    assert get_plan(client, scene_id)['snapshot']['memory_controls_version_id'] == version


def test_historical_and_blind_review_boundaries_exclude_author_decisions(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    initial = client.get('/api/branches/' + branch_id).json()['head_id']
    append(client, branch_id, 'A later revelation.')
    save(client, branch_id, [entry(evidence(client, branch_id))])
    client.app.state.review_runner.provider = ReviewProvider()
    body = {'expected_revision': 2, 'from_node_id': initial, 'through_node_id': initial,
            'steps': [{'key': 'review-continuity'}, {'key': 'review-pacing'}]}
    response, _ = start(client, story, body)
    jobs = finished_review(client, response['id'])['jobs']
    assert all('author_memory' not in decode(job['snapshot']['content']) for job in jobs)
    current = client.get('/api/branches/' + branch_id).json()['head_id']
    body.update(from_node_id=current, through_node_id=current)
    response, _ = start(client, story, body)
    jobs = finished_review(client, response['id'])['jobs']
    assert 'author_memory' in decode(next(job for job in jobs if job['step'] == 'review-continuity')['snapshot']['content'])
    assert 'author_memory' not in decode(next(job for job in jobs if job['step'] == 'review-pacing')['snapshot']['content'])


def test_archives_preserve_decisions_live_links_and_exact_saved_provider_bytes_twice(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    version = save(client, branch_id, [entry(evidence(client, branch_id))])
    client.app.state.runner.provider = DraftProvider()
    generation = finished(client, generate(client, story, revision=1)['id'])
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied = view(client, mapping[branch_id])
    assert copied['version_id'] == mapping[version]
    assert copied['entries'][0]['sources'][0]['node_id'] == mapping[client.get('/api/branches/' + branch_id).json()['head_id']]
    assert client.get('/api/generations/' + mapping[generation['id']]).json()['snapshot']['content'] == generation['snapshot']['content']
    snapshot = writer_snapshot(client, mapping[branch_id])
    assert decode(snapshot['content'])['author_memory']['entries'][0]['sources'][0]['text'] == TEXT
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch_id]})
    restore(client, second)


@pytest.mark.parametrize('kind', ['source', 'cycle', 'foreign-boundary'])
def test_archive_decision_tampering_is_rejected(client, kind):
    story, _ = setup(client)
    version = save(client, story['branch_id'], [entry(evidence(client, story['branch_id']))])
    _, document = backup(client, story)
    row = document['data']['memory_control_versions'][0]
    if kind == 'source':
        payload = decode(row['payload'])
        payload['entries'][0]['sources'][0]['text'] = 'Invented source'
        row['payload'] = encode(payload)
    elif kind == 'cycle':
        row['parent_id'] = version
    else:
        row['node_id'] = 'outside-story'
    with pytest.raises(DomainError):
        parse_archive(encode(document))


def test_old_archive_upgrade_has_no_implicit_author_decisions(client):
    story, _ = setup(client)
    _, document = backup(client, story)
    remove_controls(document)
    document['version'] = 22
    original = deepcopy(document)
    upgraded = parse_archive(encode(document))
    assert upgraded['version'] == ARCHIVE_VERSION and not upgraded['data']['memory_control_versions']
    assert original == document


def test_assessed_chance_and_reroll_preserve_frozen_controls_through_restore(client, story):
    from tests.test_assessments import settled, setup_assessment
    from tests.test_assessments import start as assess
    setup_assessment(client, story)
    branch_id = story['branch_id']
    authored = entry(evidence(client, branch_id))
    version = save(client, branch_id, [authored])
    run = settled(client, assess(client, story)['assessment_id'])
    finished(client, run['generation_id'])
    save(client, branch_id, [{**authored, 'stance': 'knows'}])
    rolled = client.post('/api/branches/' + branch_id + '/opportunities', json={
        'operation_id': uuid4().hex, 'expected_revision': 1,
        'reroll_of': run['opportunity_id'], 'beat': run['jobs'][0]['result']['beat']})
    assert rolled.status_code == 201, rolled.text
    assert view(client, rolled.json()['branch_id'])['version_id'] == version
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    assert view(client, mapping[rolled.json()['branch_id']])['version_id'] == mapping[version]
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch_id]})
    restore(client, second)


def test_complete_scene_decisions_survive_fork_acceptance_and_repeated_archives(client):
    from tests.test_scene_continuity import acceptance_body, ready_continuity
    story, _ = setup(client)
    branch_id = story['branch_id']
    authored = entry(evidence(client, branch_id))
    version = save(client, branch_id, [authored])
    run_id, _ = ready_continuity(client, story)
    save(client, branch_id, [{**authored, 'stance': 'knows'}])
    response = client.post('/api/scenes/' + run_id + '/accept',
                           json=acceptance_body(client, run_id, as_new_branch=True))
    assert response.status_code == 200, response.text
    branch = response.json()['state']['accepted']['branch_id']
    assert view(client, branch)['version_id'] == version
    original = get_plan(client, run_id)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = get_plan(client, mapping[run_id])
    assert [job['snapshot']['content'] for job in restored['jobs']] == [job['snapshot']['content'] for job in original['jobs']]
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch_id]})
    restore(client, second)
