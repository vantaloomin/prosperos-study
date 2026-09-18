import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.memory.knowledge import permitted_entries, prepare_knowledge
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished
from tests.test_memory import profiles, small_profile
from tests.test_memory_controls import entry, evidence, save, view
from tests.test_memory_maintenance import append
from tests.test_story_summaries import TEXT, fork, setup, writer_snapshot


def request(client, branch_id, **changes):
    return {'operation_id': uuid4().hex, 'expected_revision': client.get('/api/branches/' + branch_id).json()['revision'],
            'knowledge_subject': 'Elin', 'assess_beat': False, 'use_prepared_beat': False, **changes}


def snapshot(client, branch_id, **changes):
    with client.app.state.database.connect() as connection:
        return generation_snapshot(connection, branch_id, GenerateRequest(**request(client, branch_id, **changes)))[0]


def fixture(client):
    story, profile = setup(client)
    branch = story['branch_id']
    append(client, branch, 'SECRET: The letter is a forgery. Only Ivo witnessed its creation.')
    sources = evidence(client, branch)
    grants = [entry([sources[0]], stance='believes'), entry([sources[1]], subject='Ivo', stance='knows')]
    save(client, branch, grants)
    return story, profile, grants


def test_character_view_excludes_unassigned_history_other_people_and_story_premise(client):
    story, _, _ = fixture(client)
    result = snapshot(client, story['branch_id'])
    context = decode(result['content'])
    assert set(context) == {'story', 'knowledge_view', 'knowledge', 'direction'}
    assert TEXT in result['content'] and 'SECRET' not in result['content'] and 'PRIVATE PREMISE' not in result['content']
    assert [item['stance'] for item in context['knowledge']] == ['believes']
    assert result['knowledge_lens']['permitted_decisions'] == 1
    assert result['knowledge_lens']['source_count'] == 1
    assert 'SECRET' in writer_snapshot(client, story['branch_id'])['content']


def test_deny_overrides_grants_and_removes_the_entire_interpretation(client):
    story, _, grants = fixture(client)
    sources = evidence(client, story['branch_id'])
    mixed = entry(sources, stance='knows', text='SECRET interpretation of both passages.')
    deny = entry([sources[1]], stance='unaware')
    save(client, story['branch_id'], [*grants, mixed, deny])
    result = snapshot(client, story['branch_id'])
    assert 'SECRET' not in result['content']
    assert result['knowledge_lens']['selected_ids'] == [grants[0]['id']]
    save(client, story['branch_id'], [*grants, entry([sources[0]], stance='unaware')])
    with pytest.raises(DomainError, match='no enabled, permitted evidence'):
        snapshot(client, story['branch_id'])


@pytest.mark.parametrize('changes', [{'knowledge_subject': 'Nobody'}, {'assess_beat': True}, {'use_prepared_beat': True}])
def test_invalid_lenses_and_chance_fail_before_records_or_provider_calls(client, changes):
    story, _, _ = fixture(client)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    response = client.post('/api/branches/' + story['branch_id'] + '/generations', json=request(client, story['branch_id'], **changes))
    assert response.status_code == 409, response.text
    assert not provider.calls
    assert not client.get('/api/branches/' + story['branch_id'] + '/generations').json()


def test_comparison_and_alternate_keep_exact_lens_inputs_after_author_correction(client):
    story, profile, grants = fixture(client)
    second = small_profile(client, limit=4096)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    body = request(client, story['branch_id'], profile_ids=[profile['profile_id'], second['profile_id']])
    response = client.post('/api/branches/' + story['branch_id'] + '/generations', json=body)
    assert response.status_code == 201, response.text
    assert client.post('/api/branches/' + story['branch_id'] + '/generations', json=body).json() == response.json()
    run = finished(client, response.json()['id'])
    assert len(provider.calls) == 2 and provider.calls[0][1:] == provider.calls[1][1:]
    save(client, story['branch_id'], [{**grants[0], 'stance': 'unaware'}])
    alternate = client.post('/api/candidates/' + run['candidates'][0]['id'] + '/alternatives', json={'operation_id': uuid4().hex})
    assert alternate.status_code == 201, alternate.text
    finished(client, run['id'])
    assert provider.calls[-1][2] == run['snapshot']['content']


def test_lens_follows_branch_decisions_and_past_edit_boundaries(client):
    story, _, grants = fixture(client)
    branch = story['branch_id']
    head = client.get('/api/branches/' + branch).json()['head_id']
    copied = fork(client, branch, head)
    save(client, branch, [{**grants[0], 'enabled': False}])
    assert TEXT in snapshot(client, copied)['content']
    with pytest.raises(DomainError):
        snapshot(client, branch)
    first = client.get('/api/branches/' + copied).json()['messages'][0]['id']
    past = fork(client, copied, first)
    with pytest.raises(DomainError):
        snapshot(client, past)


def test_archive_restore_preserves_permissions_and_bytes_twice(client):
    story, _, _ = fixture(client)
    client.app.state.runner.provider = DraftProvider()
    response = client.post('/api/branches/' + story['branch_id'] + '/generations', json=request(client, story['branch_id']))
    run = finished(client, response.json()['id'])
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get('/api/generations/' + mapping[run['id']]).json()
    assert restored['snapshot']['content'] == run['snapshot']['content']
    assert 'SECRET' not in snapshot(client, mapping[story['branch_id']])['content']
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)


@pytest.mark.parametrize('kind', ['extra-layer', 'grant-text', 'foreign-source', 'count'])
def test_archive_rejects_lens_changes_even_with_recomputed_digest(client, kind):
    story, _, _ = fixture(client)
    client.app.state.runner.provider = DraftProvider()
    response = client.post('/api/branches/' + story['branch_id'] + '/generations', json=request(client, story['branch_id']))
    finished(client, response.json()['id'])
    _, document = backup(client, story)
    row = document['data']['generations'][0]
    saved = decode(row['snapshot'])
    context = decode(saved['content'])
    if kind == 'extra-layer':
        context['private_background'] = 'Not allowed'
    elif kind == 'grant-text':
        context['knowledge'][0]['text'] = 'Different instruction'
    elif kind == 'foreign-source':
        saved['source_links'][0]['node_id'] = 'foreign-node'
    else:
        saved['knowledge_lens']['permitted_decisions'] += 1
    saved['content'] = encode(context)
    saved['knowledge_lens']['content_sha256'] = hashlib.sha256(saved['content'].encode()).hexdigest()
    row['snapshot'] = encode(saved)
    with pytest.raises(DomainError):
        parse_archive(encode(document))


def test_filtering_precedes_ranking_and_budgets_use_only_permitted_material(client, monkeypatch):
    from server.memory import knowledge
    story, _, grants = fixture(client)
    # Force selection under pressure while the other character's secret stays out of the corpus.
    allowed = [{**deepcopy(grants[0]), 'id': uuid4().hex, 'subject': 'Elin', 'text': ('known context ' * 60) + str(index),
                'sources': evidence(client, story['branch_id'])[:1]} for index in range(14)]
    foreign = {**allowed[0], 'id': uuid4().hex, 'subject': 'Ivo', 'text': 'SECRET'}
    controls = {'entries': [*allowed, foreign]}
    original = knowledge.Corpus
    captured = []
    def corpus(chunks):
        captured.extend(chunks)
        return original(chunks)
    monkeypatch.setattr(knowledge, 'Corpus', corpus)
    content, report, _ = prepare_knowledge(controls, 'Elin', 'known context', 'Write.', profiles(4096, 8192))
    assert captured and all('SECRET' not in chunk.text for chunk in captured)
    assert 'SECRET' not in content and report['input_allowance'] == 3584
    assert 0 < report['selected_decisions'] < report['permitted_decisions'] == 14
    assert len(permitted_entries(controls, 'Elin')) == 14


def test_reviewed_preview_cannot_dispatch_after_permission_change(client):
    story, _, grants = fixture(client)
    body = request(client, story['branch_id'])
    preview = client.post('/api/branches/' + story['branch_id'] + '/context-preview', json={key: value for key, value in body.items() if key != 'operation_id'})
    assert preview.status_code == 200, preview.text
    assert preview.json()['knowledge_lens']['subject'] == 'Elin'
    save(client, story['branch_id'], [{**grants[0], 'stance': 'knows'}])
    response = client.post('/api/branches/' + story['branch_id'] + '/generations', json={**body, 'reviewed_fingerprint': preview.json()['fingerprint']})
    assert response.status_code == 409
    assert view(client, story['branch_id'])['entries'][0]['stance'] == 'knows'


def test_character_view_preserves_mode_and_agency_without_free_text_settings(client):
    story, _, _ = fixture(client)
    current = client.get('/api/stories/' + story['story_id']).json()
    changed = client.put('/api/stories/' + story['story_id'], json={
        'title': current['title'], 'premise': current['premise'], 'expected_revision': current['revision'],
        'settings': {**current['settings'], 'experience': 'directed', 'player_agency': 'shared',
                     'tone': 'SECRET tone instruction', 'persona': 'SECRET participation notes'}})
    assert changed.status_code == 200, changed.text
    saved = snapshot(client, story['branch_id'])
    assert decode(saved['content'])['story']['settings'] == {'experience': 'directed', 'player_agency': 'shared'}
    assert 'SECRET' not in saved['content']


def test_character_draft_fork_preserves_private_state_without_disclosing_it(client):
    from server.background.storage import state_id
    from tests.test_background import prepared, revealed
    story, _, _ = fixture(client)
    private = prepared(client, story, origin='PRIVATE ORIGIN NEVER DISCLOSE')
    client.app.state.runner.provider = DraftProvider()
    response = client.post('/api/branches/' + story['branch_id'] + '/generations', json=request(client, story['branch_id']))
    assert response.status_code == 201, response.text
    run = finished(client, response.json()['id'])
    assert run['snapshot']['background_state_id'] == private['id']
    assert 'PRIVATE ORIGIN' not in run['snapshot']['content']
    assert revealed(client, private)['result']['seed'] not in run['snapshot']['content']
    accepted = client.post('/api/candidates/' + run['candidates'][0]['id'] + '/accept',
                           json={'operation_id': uuid4().hex, 'as_new_branch': True})
    assert accepted.status_code == 200, accepted.text
    with client.app.state.database.connect() as connection:
        assert state_id(connection, accepted.json()['branch_id']) == private['id']
    file, _ = backup(client, story)
    restore(client, file)
