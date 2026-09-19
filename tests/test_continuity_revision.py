import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.continuity_revision import PROMPT, freeze
from server.database import decode, encode
from server.errors import DomainError
from server.memory.writer_recall import digest
from server.prompt_sections import system_prompt
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished, generate
from tests.test_history import append
from tests.test_profiles import make_profile


class RevisionProvider(DraftProvider):
    async def generate(self, profile, prompt, content):
        self.calls.append((deepcopy(profile), prompt, content))
        yield ProviderEvent(text='The recipient confirmed the receipt.' if prompt == PROMPT else 'The recipient was still waiting.', done=True)


def original(client, story):
    provider = RevisionProvider()
    client.app.state.runner.provider = provider
    make_profile(client, 'Writer', primary=True)
    run = generate(client, story)
    candidate = finished(client, run['id'])['candidates'][0]
    return run, candidate, provider


def revision_body(candidate, **overrides):
    return {'operation_id': uuid4().hex, 'expected_attempt': candidate['attempt'],
            'original_sha256': digest(candidate['output']), 'concern': 'Check the established receipt.', **overrides}


def revise(client, candidate, body=None):
    return client.post(f"/api/candidates/{candidate['id']}/continuity-revision", json=body or revision_body(candidate))


def test_proposal_is_one_explicit_call_original_retained_and_keep_required(client, story):
    run, source, provider = original(client, story)
    before = client.get(f"/api/generations/{run['id']}").json()['snapshot']
    body = revision_body(source)
    result = revise(client, source, body)
    assert result.status_code == 201, result.text
    assert revise(client, source, body).json() == result.json()
    detail = finished(client, run['id'])
    assert len(provider.calls) == 2
    proposal = next(row for row in detail['candidates'] if row['id'] == result.json()['candidate_id'])
    receipt = proposal['usage']['continuity_revision']
    assert receipt['version'] == 2
    assert decode(receipt['content'])['writer_instructions'] == system_prompt(before)
    assert provider.calls[-1][1:] == (receipt['prompt'], receipt['content'])
    assert decode(receipt['content'])['context'] == decode(before['content'])
    assert detail['snapshot'] == before and detail['candidates'][0]['output'] == source['output']
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []
    assert proposal['cleanup'] is None
    accepted = client.post(f"/api/candidates/{proposal['id']}/accept", json={'operation_id': uuid4().hex})
    assert accepted.status_code == 200
    messages = client.get(f"/api/branches/{story['branch_id']}").json()['messages']
    assert messages[0]['text'] == proposal['output']
    assert detail['candidates'][0]['accepted_node_id'] is None


@pytest.mark.parametrize('override', [{'expected_attempt': 99}, {'original_sha256': '0' * 64}, {'concern': '  '}])
def test_invalid_or_obsolete_requests_create_no_alternative(client, story, override):
    run, source, provider = original(client, story)
    assert revise(client, source, revision_body(source, **override)).status_code in {400, 409, 422}
    assert len(client.get(f"/api/generations/{run['id']}").json()['candidates']) == 1
    assert len(provider.calls) == 1


def test_budget_overflow_refuses_without_dropping_sources_or_calling_provider():
    snapshot = {'prompt': {'template': 'Write.'}, 'content': encode({'history': [{'text': 'x' * 10000}]})}
    candidate = {'id': 'a', 'attempt': 1, 'output': 'A draft.'}
    with pytest.raises(DomainError, match='do not fit'):
        freeze(snapshot, {'config': {'context_tokens': 4096, 'max_output_tokens': 1024}}, {}, candidate, 'Check history.')
    assert len(decode(snapshot['content'])['history'][0]['text']) == 10000


def test_revision_preserves_v1_replay_and_new_requests_respect_profile_safety():
    from server.continuity_revision import prepare
    snapshot = {'prompt': {'template': 'Write.'}, 'content': encode({'history': []})}
    candidate = {'id': 'original', 'attempt': 1, 'output': 'A draft.'}
    config = {'context_tokens': 8192, 'max_output_tokens': 512}
    old = freeze(snapshot, {'config': config}, {}, candidate, 'Check history.', version=1)
    config['context_safety_tokens'] = 7680 - old['estimated_input_tokens'] + 1
    assert freeze(snapshot, {'config': config}, {}, candidate, 'Check history.', version=1) == old
    with pytest.raises(DomainError, match='do not fit'):
        freeze(snapshot, {'config': config}, {}, candidate, 'Check history.')
    state = {'usage': {}}
    replay = prepare({'usage': encode({'continuity_revision': old})}, snapshot, state)
    assert (system_prompt(replay), replay['content']) == (old['prompt'], old['content'])


def test_stale_proposal_can_only_be_kept_on_frozen_fork(client, story):
    run, source, _ = original(client, story)
    response = revise(client, source)
    proposal = finished(client, run['id'])['candidates'][-1]
    assert response.status_code == 201
    append(client, story['branch_id'], 'Later history.', 0)
    endpoint = f"/api/candidates/{proposal['id']}/accept"
    assert client.post(endpoint, json={'operation_id': uuid4().hex}).status_code == 409
    accepted = client.post(endpoint, json={'operation_id': uuid4().hex, 'as_new_branch': True})
    assert accepted.status_code == 200
    messages = client.get(f"/api/branches/{accepted.json()['branch_id']}").json()['messages']
    assert [row['text'] for row in messages] == [proposal['output']]
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][0]['text'] == 'Later history.'


def test_retry_restore_and_alternative_preserve_revision_bytes(client, story):
    run, source, _ = original(client, story)

    class Waiting(RevisionProvider):
        async def generate(self, profile, prompt, content):
            self.calls.append((profile, prompt, content))
            yield ProviderEvent(text='Partial proposal.')
            await asyncio.sleep(60)

    waiting = Waiting()
    client.app.state.runner.provider = waiting
    response = revise(client, source)
    candidate_id = response.json()['candidate_id']
    client.post(f'/api/candidates/{candidate_id}/cancel')
    detail = finished(client, run['id'])
    receipt = detail['candidates'][-1]['usage']['continuity_revision']
    assert detail['candidates'][-1]['status'] == 'cancelled'
    assert detail['candidates'][-1]['output'] == 'Partial proposal.'
    file, document = backup(client, story)
    parse_archive(encode(document))
    _, mapping = restore(client, file)
    candidate_id = mapping[candidate_id]
    provider = RevisionProvider()
    client.app.state.runner.provider = provider
    assert client.post(f'/api/candidates/{candidate_id}/retry').status_code == 200
    result = finished(client, mapping[run['id']])['candidates'][-1]
    assert provider.calls[-1][1:] == (receipt['prompt'], receipt['content'])
    assert result['usage']['continuity_revision']['candidate_id'] == mapping[source['id']]
    second = client.post(f'/api/candidates/{candidate_id}/alternatives', json={'operation_id': uuid4().hex})
    assert second.status_code == 201
    finished(client, mapping[run['id']])
    assert provider.calls[-1][1:] == provider.calls[-2][1:]
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    corrupted = deepcopy(document)
    target = next(row for row in corrupted['data']['candidates'] if row['id'] == response.json()['candidate_id'])
    usage = decode(target['usage'])
    usage['continuity_revision']['content'] += ' forged context'
    target['usage'] = encode(usage)
    with pytest.raises(DomainError, match='differs'):
        parse_archive(encode(corrupted))


def test_character_revision_reuses_only_permitted_inputs(client):
    from tests.test_knowledge_lens import fixture, request
    story, _, _ = fixture(client)
    client.app.state.runner.provider = RevisionProvider()
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=request(client, story['branch_id']))
    source = finished(client, response.json()['id'])['candidates'][0]
    proposed = revise(client, source)
    assert proposed.status_code == 201, proposed.text
    candidate = finished(client, response.json()['id'])['candidates'][-1]
    context = decode(candidate['usage']['continuity_revision']['content'])['context']
    assert 'knowledge_view' in context and 'history' not in context
    assert 'SECRET' not in encode(context) and 'PRIVATE PREMISE' not in encode(context)
    backup(client, story)


def test_recall_revision_reuses_completed_packet_without_another_search(client):
    from tests.test_writer_recall import RecallProvider, setup_story, start
    story, nodes = setup_story(client)
    # Leave explicit headroom for the extra draft and feedback, without changing
    # profile settings after either request has been saved.
    profile = client.get('/api/profiles').json()['profiles'][0]
    config = {**profile['config'], 'context_tokens': 32768}
    updated = client.put(f"/api/profiles/{profile['profile_id']}", json={
        'expected_version_id': profile['id'], 'name': profile['name'], 'config': config})
    assert updated.status_code == 200, updated.text
    provider = RecallProvider()
    client.app.state.runner.provider = provider
    run = start(client, story, len(nodes))
    source = finished(client, run['id'])['candidates'][0]
    initial = len(provider.calls)
    response = revise(client, source)
    assert response.status_code == 201, response.text
    target = finished(client, run['id'])['candidates'][-1]
    assert len(provider.calls) == initial + 1
    assert decode(target['usage']['continuity_revision']['content'])['context'] == decode(source['usage']['writer_recall']['final_input']['content'])
    backup(client, story)
