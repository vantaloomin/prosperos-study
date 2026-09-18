import json
from copy import deepcopy
from uuid import uuid4

from server.database import decode, one
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_planned_events import AGREEMENT, WITHDRAWAL, accept_plan, change, fork, plan
from tests.test_profiles import make_profile


def view(client, branch):
    return client.get(f'/api/branches/{branch}/plans').json()


def save(client, branch, value=None, target=None, *, source_index=-1):
    state = view(client, branch)
    sources = client.get(f'/api/branches/{branch}/plan-sources').json()['items']
    source = sources[source_index]
    proposed = change(value, target=target, quote=source['text'])
    proposed['evidence'] = [{'source_id': source['id'], 'quote': source['text']}]
    body = {'operation_id': uuid4().hex, 'expected_revision': state['revision'],
            'expected_version_id': state['version_id'], 'change': proposed}
    result = client.post(f'/api/branches/{branch}/plans', json=body)
    assert result.status_code == 200, result.text
    assert client.post(f'/api/branches/{branch}/plans', json=body).json() == result.json()
    return result.json(), body


def test_author_edit_changes_memory_without_adding_story_and_sibling_stays_unchanged(client, story):
    branch = story['branch_id']
    head = append(client, branch, AGREEMENT, 0)
    sibling = fork(client, branch, head)
    original = client.get(f'/api/branches/{branch}').json()
    created, _ = save(client, branch)
    after = client.get(f'/api/branches/{branch}').json()
    assert after['messages'] == original['messages'] and after['head_id'] == head
    assert after['revision'] == original['revision'] + 1
    assert view(client, sibling)['entries'] == []
    before_change = fork(client, branch, head)
    append(client, branch, WITHDRAWAL, after['revision'])
    revised = plan()
    revised['participants'][0]['commitment'] = 'withdrawn'
    save(client, branch, revised, created['entry_id'])
    assert view(client, branch)['entries'][0]['plan'] == revised
    assert view(client, before_change)['entries'][0]['plan'] == plan()
    edited = fork(client, branch, head, replacement='No camping trip was discussed.')
    assert view(client, edited)['entries'] == []


def test_author_edits_round_trip_and_reject_foreign_or_changed_evidence(client, story):
    branch = story['branch_id']
    append(client, branch, AGREEMENT, 0)
    created, body = save(client, branch)
    file, document = backup(client, story)
    _, mapping = restore(client, file)
    copied = view(client, mapping[branch])
    assert copied['entries'][0]['id'] == created['entry_id']
    assert copied['entries'][0]['plan'] == plan()
    second_file, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch]})
    _, second_mapping = restore(client, second_file)
    assert view(client, second_mapping[mapping[branch]])['entries'][0]['id'] == created['entry_id']
    damage = deepcopy(document)
    damage['data']['continuity_edits'][0]['changes'] = damage['data']['continuity_edits'][0]['changes'].replace('go camping', 'go sailing')
    assert client.post('/api/archives/imports', json={'content': json.dumps(damage)}).status_code == 400
    body['operation_id'] = uuid4().hex
    body['expected_revision'] = view(client, branch)['revision']
    body['expected_version_id'] = created['id']
    body['change']['evidence'][0]['source_id'] = 'foreign-source'
    assert client.post(f'/api/branches/{branch}/plans', json=body).status_code == 400


def test_frozen_writer_inputs_keep_old_plan_after_an_author_correction(client, story):
    branch = story['branch_id']
    append(client, branch, AGREEMENT, 0)
    make_profile(client, 'Plan writer', primary=True)
    created, _ = save(client, branch)
    with client.app.state.database.connect() as connection:
        current = one(connection, 'SELECT * FROM branches WHERE id=?', (branch,))
        snapshot, _ = generation_snapshot(connection, branch, GenerateRequest(
            operation_id=uuid4().hex, expected_revision=current['revision'], use_prepared_beat=False))
    frozen = snapshot['content']
    postponed = plan('postponed')
    postponed['timing'] = 'next weekend'
    save(client, branch, postponed, created['entry_id'])
    assert decode(frozen)['continuity']['entries'][0]['plan']['timing'] == 'this weekend'
    assert snapshot['continuity_version_id'] == created['id']
    assert view(client, branch)['entries'][0]['plan']['timing'] == 'next weekend'


def test_scene_can_update_author_recorded_plan_and_preserve_earlier_author_state(client, story):
    branch = story['branch_id']
    append(client, branch, AGREEMENT, 0)
    created, _ = save(client, branch)
    earlier = fork(client, branch, client.get(f'/api/branches/{branch}').json()['head_id'])
    revised = plan()
    revised['participants'][0]['commitment'] = 'withdrawn'
    accept_plan(client, story, WITHDRAWAL, change(revised, target=created['entry_id'], quote=WITHDRAWAL))
    assert view(client, branch)['entries'][0]['plan'] == revised
    assert view(client, earlier)['entries'][0]['plan'] == plan()
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    assert view(client, mapping[branch])['entries'][0]['plan'] == revised

def test_saved_bounded_writer_and_alternate_acceptance_keep_frozen_plans(client):
    from server.archives.format import canonical
    from server.archives.writer_sources import digest
    from server.database import encode
    from server.memory.budget import token_estimate
    from tests.test_generations import DraftProvider, finished
    from tests.test_memory import small_profile

    story = client.post('/api/stories', json={'title': 'Plan context receipt',
        'settings': {'memory': {'mode': 'long'}}}).json()
    branch = story['branch_id']
    append(client, branch, AGREEMENT, 0)
    created, _ = save(client, branch)
    for index in range(12):
        append(client, branch, 'They tidied the house and discussed the weather. ' * 30, index + 2)
    small_profile(client)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    run = client.post(f'/api/branches/{branch}/generations', json={
        'operation_id': uuid4().hex, 'expected_revision': view(client, branch)['revision'],
        'direction': 'I cannot go this weekend.', 'use_prepared_beat': False, 'assess_beat': False}).json()
    detail = finished(client, run['id'])
    assert detail['candidates'][0]['status'] == 'done'
    original_input = detail['snapshot']['content']
    assert decode(original_input)['plan_memory']['entries'][0]['plan'] == plan()
    postponed = plan('postponed')
    postponed['timing'] = 'next weekend'
    save(client, branch, postponed, created['entry_id'], source_index=0)
    accepted = client.post('/api/candidates/' + detail['candidates'][0]['id'] + '/accept',
        json={'operation_id': uuid4().hex, 'as_new_branch': True, 'branch_name': 'Original intention'})
    assert accepted.status_code == 200, accepted.text
    assert view(client, accepted.json()['branch_id'])['entries'][0]['plan'] == plan()
    assert view(client, branch)['entries'][0]['plan'] == postponed
    file, document = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get('/api/generations/' + mapping[run['id']]).json()
    assert restored['snapshot']['content'] == original_input
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch]})
    changed = deepcopy(document)
    row = changed['data']['generations'][0]
    snapshot = decode(row['snapshot'])
    content = decode(snapshot['content'])
    content['plan_memory']['entries'][0]['plan']['status'] = 'completed'
    snapshot['content'] = encode(content)
    snapshot['memory']['content_sha256'] = digest(snapshot['content'])
    snapshot['estimated_input_tokens'] = token_estimate(snapshot['prompt']['template'], content)
    row['snapshot'] = encode(snapshot)
    response = client.post('/api/archives/imports', json={'content': canonical(changed)})
    assert response.status_code == 400 and 'recorded source' in response.text


def test_character_lens_keeps_branch_plans_without_disclosing_private_intentions(client, story):
    from tests.test_generations import DraftProvider, finished
    from tests.test_memory_controls import entry, evidence
    from tests.test_memory_controls import save as save_controls

    branch = story['branch_id']
    append(client, branch, AGREEMENT, 0)
    created, _ = save(client, branch)
    append(client, branch, 'Elin saw the bakery open its doors at sunrise.', 2)
    public = [source for source in evidence(client, branch) if 'bakery' in source['text']]
    assert len(public) == 1
    save_controls(client, branch, [entry(public, stance='knows', text='Elin knows the bakery is open.')])
    make_profile(client, 'Limited viewpoint', primary=True)
    client.app.state.runner.provider = DraftProvider()
    response = client.post(f'/api/branches/{branch}/generations', json={
        'operation_id': uuid4().hex, 'expected_revision': view(client, branch)['revision'],
        'knowledge_subject': 'Elin', 'direction': 'Visit the bakery.',
        'use_prepared_beat': False, 'assess_beat': False})
    assert response.status_code == 201, response.text
    detail = finished(client, response.json()['id'])
    assert detail['candidates'][0]['status'] == 'done'
    snapshot = detail['snapshot']
    assert snapshot['continuity_version_id'] == created['id']
    assert 'bakery' in snapshot['content']
    assert not any(word in snapshot['content'].lower() for word in ['camping', 'jules', 'plan_memory'])
    result = client.post('/api/candidates/' + detail['candidates'][0]['id'] + '/accept', json={
        'operation_id': uuid4().hex, 'as_new_branch': True, 'branch_name': 'Elin at the bakery'})
    assert result.status_code == 200, result.text
    assert view(client, result.json()['branch_id'])['entries'][0]['plan'] == plan()
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    assert view(client, mapping[result.json()['branch_id']])['entries'][0]['plan'] == plan()
