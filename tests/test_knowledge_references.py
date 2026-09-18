import hashlib
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished
from tests.test_knowledge_lens import request, snapshot
from tests.test_library import adoption_request
from tests.test_memory_controls import entry, evidence, save, view
from tests.test_profiles import make_profile
from tests.test_story_summaries import fork


def asset(client, kind, name, content):
    response = client.post('/api/library', json={'kind': kind, 'name': name, 'content': content})
    assert response.status_code == 201, response.text
    return response.json()


def fixture(client):
    make_profile(client, 'Reference writer', primary=True)
    character = asset(client, 'character', 'Elin', {
        'text': 'SECRET Character background.', 'voice': 'Elin speaks in short, measured sentences.',
        'author_notes': 'SECRET author instruction.', 'private_extension': 'SECRET extra metadata.',
        'greetings': [{'id': 'start', 'label': 'Arrival', 'text': 'SECRET greeting.'}],
    })
    twin = asset(client, 'character', 'Elin', {'text': 'SECRET different Elin.'})
    book = asset(client, 'lorebook', 'The coast', {'text': '# Ferry\nThe ferry takes copper coins.\n\n# Vault\nSECRET vault mechanism.'})
    disabled = asset(client, 'lorebook', 'Hidden collection', {'text': 'DISABLED reference.'})
    story = client.post('/api/stories', json={'title': 'Reference boundaries', 'premise': 'SECRET premise.',
        'opening_text': 'Elin arrives at the shore.', 'settings': {'disabled_prompts': []}, 'attachments': [
            {'asset_id': item['asset_id'], 'version_id': item['id'], 'enabled': item != disabled}
            for item in (character, twin, book, disabled)]}).json()
    return story, character, twin, book


def sources(client, branch):
    response = client.get('/api/branches/' + branch + '/memory-control-sources?category=library')
    assert response.status_code == 200, response.text
    return response.json()['items']


def grant(client, story, character, book):
    selected = [source for source in sources(client, story['branch_id'])
                if (source['asset_id'] == book['asset_id'] and source['title'] == 'Ferry')
                or (source['asset_id'] == character['asset_id'] and source['field'] == 'voice')]
    authored = entry(selected, stance='knows', character_id=character['asset_id'], text='Elin learned the fare from the ferryman.')
    save(client, story['branch_id'], [authored])
    return authored


def publish(client, item, name=None, content=None):
    response = client.post('/api/library/' + item['asset_id'] + '/versions', json={
        'expected_version_id': item['id'], 'name': name or item['name'], 'content': content or item['content']})
    assert response.status_code == 201, response.text
    return response.json()


def adopt(client, item):
    endpoint = '/api/versions/' + item['id'] + '/adoption'
    response = client.post(endpoint, json=adoption_request(client.get(endpoint).json()))
    assert response.status_code == 200, response.text


def generated(client, story, character):
    client.app.state.runner.provider = DraftProvider()
    response = client.post('/api/branches/' + story['branch_id'] + '/generations', json=request(
        client, story['branch_id'], knowledge_subject=None, knowledge_character_id=character['asset_id']))
    assert response.status_code == 201, response.text
    return finished(client, response.json()['id'])


def test_catalogue_only_offers_whitelisted_enabled_pinned_text_and_explicit_grants(client):
    story, character, _, book = fixture(client)
    branch = story['branch_id']
    catalogue = sources(client, branch)
    assert not any(source['field'] in {'author_notes', 'greetings', 'private_extension'} for source in catalogue)
    assert all('DISABLED' not in source['text'] for source in catalogue)
    latest = publish(client, book, content={'text': 'UNADOPTED replacement.'})
    assert all(source['version_id'] != latest['id'] for source in sources(client, branch))
    authored = grant(client, story, character, book)
    result = snapshot(client, branch, knowledge_subject=None, knowledge_character_id=character['asset_id'])
    assert 'copper coins' in result['content'] and 'measured sentences' in result['content']
    assert 'SECRET' not in result['content'] and 'UNADOPTED' not in result['content']
    assert result['knowledge_lens']['algorithm'] == 'prospero-character-evidence-v2'
    assert result['knowledge_lens']['source_count'] == 2
    assert result['coverage']['messages'] == 0
    for source in decode(result['content'])['knowledge'][0]['sources']:
        original = book if source['asset_id'] == book['asset_id'] else character
        assert original['content'][source['field']][source['start']:source['end']] == source['text']
        assert hashlib.sha256(source['text'].encode()).hexdigest() == source['sha256']
    assert result['knowledge_lens']['selected_ids'] == [authored['id']]


def test_identical_names_and_name_only_viewpoints_never_merge_permissions(client):
    story, character, twin, book = fixture(client)
    authored = grant(client, story, character, book)
    legacy = entry(evidence(client, story['branch_id']), stance='knows', text='LEGACY viewpoint.')
    twin_grant = entry([source for source in sources(client, story['branch_id']) if source['asset_id'] == twin['asset_id']],
                       stance='knows', character_id=twin['asset_id'], text='TWIN interpretation.')
    save(client, story['branch_id'], [authored, legacy, twin_grant])
    bound = snapshot(client, story['branch_id'], knowledge_character_id=character['asset_id'])['content']
    assert 'TWIN' not in bound and 'LEGACY' not in bound and 'SECRET' not in bound
    name_only = snapshot(client, story['branch_id'])['content']
    assert 'LEGACY' in name_only and 'copper coins' not in name_only and 'TWIN' not in name_only


def test_rename_keeps_prose_grants_but_profile_grants_require_new_edition_review(client):
    story, character, _, book = fixture(client)
    references = grant(client, story, character, book)
    prose = entry(evidence(client, story['branch_id']), stance='knows', character_id=character['asset_id'])
    save(client, story['branch_id'], [references, prose])
    renamed = publish(client, character, name='Elin of the Coast')
    adopt(client, renamed)
    current = view(client, story['branch_id'])
    assert [item['id'] for item in current['entries']] == [prose['id']]
    assert [item['id'] for item in current['unavailable_entries']] == [references['id']]
    result = snapshot(client, story['branch_id'], knowledge_subject=None, knowledge_character_id=character['asset_id'])
    assert result['knowledge_lens']['subject'] == 'Elin of the Coast'
    assert 'copper coins' not in result['content']  # Suppress the whole mixed interpretation.
    file, _ = backup(client, story)
    restore(client, file)


def test_does_not_know_blocks_reference_grants_for_only_the_bound_identity(client):
    story, character, _, book = fixture(client)
    authored = grant(client, story, character, book)
    denial = {**authored, 'id': uuid4().hex, 'stance': 'unaware', 'source_ids': authored['source_ids'][:1]}
    save(client, story['branch_id'], [authored, denial])
    with pytest.raises(DomainError, match='no enabled, permitted evidence'):
        snapshot(client, story['branch_id'], knowledge_character_id=character['asset_id'])
    save(client, story['branch_id'], [authored, {**denial, 'enabled': False}])
    assert 'copper coins' in snapshot(client, story['branch_id'], knowledge_character_id=character['asset_id'])['content']


def test_adoption_invalidates_preview_and_future_grants_but_preserves_saved_alternatives(client):
    story, character, _, book = fixture(client)
    authored = grant(client, story, character, book)
    run = generated(client, story, character)
    body = request(client, story['branch_id'], knowledge_character_id=character['asset_id'])
    preview = client.post('/api/branches/' + story['branch_id'] + '/context-preview', json={key: value for key, value in body.items() if key != 'operation_id'})
    assert preview.status_code == 200, preview.text
    changed = publish(client, book, content={'text': '# Ferry\nThe ferry demands a secret password.'})
    adopt(client, changed)
    rejected = client.post('/api/branches/' + story['branch_id'] + '/generations', json={**body, 'reviewed_fingerprint': preview.json()['fingerprint']})
    assert rejected.status_code == 409
    assert not view(client, story['branch_id'])['entries']
    before = len(client.get('/api/branches/' + story['branch_id'] + '/memory-control-history').json())
    current = view(client, story['branch_id'])
    saved = client.put('/api/branches/' + story['branch_id'] + '/memory-controls', json={
        'operation_id': uuid4().hex, 'expected_revision': current['revision'], 'expected_version_id': current['version_id'], 'entries': [authored]})
    assert saved.status_code == 409
    assert len(client.get('/api/branches/' + story['branch_id'] + '/memory-control-history').json()) == before
    alternate = client.post('/api/candidates/' + run['candidates'][0]['id'] + '/alternatives', json={'operation_id': uuid4().hex})
    assert alternate.status_code == 201, alternate.text
    finished(client, run['id'])
    assert client.app.state.runner.provider.calls[-1][2] == run['snapshot']['content']
    assert 'secret password' not in run['snapshot']['content']


def test_historical_fork_reuses_its_exact_edition_without_granting_new_text(client):
    story, character, _, book = fixture(client)
    grant(client, story, character, book)
    opening = client.get('/api/branches/' + story['branch_id']).json()['head_id']
    adopt(client, publish(client, book, content={'text': 'NEW edition.'}))
    historical = fork(client, story['branch_id'], opening)
    result = snapshot(client, historical, knowledge_character_id=character['asset_id'])
    assert 'copper coins' in result['content'] and 'NEW edition' not in result['content']


def test_reference_archive_restores_live_identities_and_exact_frozen_inputs_twice_after_adoption(client):
    story, character, _, book = fixture(client)
    grant(client, story, character, book)
    run = generated(client, story, character)
    adopt(client, publish(client, book, content={'text': 'NEW edition.'}))
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    saved = client.get('/api/generations/' + mapping[run['id']]).json()['snapshot']
    assert saved['content'] == run['snapshot']['content']
    assert saved['knowledge_character_id'] == mapping[character['asset_id']]
    assert saved['knowledge_lens']['character_id'] == character['asset_id']
    assert saved['source_links'][0]['version_id'] != run['snapshot']['source_links'][0]['version_id']
    assert saved['source_links'][0]['frozen_version_id'] == run['snapshot']['source_links'][0]['version_id']
    restored_story = {key: mapping[value] for key, value in story.items()}
    second, _ = backup(client, restored_story)
    restore(client, second)


@pytest.mark.parametrize('mutation', ['field', 'identity', 'extra-context', 'manifest'])
def test_archive_rejects_altered_reference_receipts_and_permissions(client, mutation):
    story, character, twin, book = fixture(client)
    grant(client, story, character, book)
    generated(client, story, character)
    _, document = backup(client, story)
    row = document['data']['generations'][0]
    saved = decode(row['snapshot'])
    if mutation == 'field':
        saved['source_links'][0]['field'] = 'author_notes'
    elif mutation == 'identity':
        saved['knowledge_character_id'] = twin['asset_id']
    elif mutation == 'manifest':
        control = document['data']['memory_control_versions'][0]
        payload = decode(control['payload'])
        payload['manifest_id'] = 'foreign-manifest'
        control['payload'] = encode(payload)
    else:
        context = decode(saved['content'])
        context['knowledge'][0]['sources'][0]['text'] += ' SECRET extra source.'
        saved['content'] = encode(context)
        saved['knowledge_lens']['content_sha256'] = hashlib.sha256(saved['content'].encode()).hexdigest()
    row['snapshot'] = encode(saved)
    with pytest.raises(DomainError):
        parse_archive(encode(document))


def test_concurrent_adoption_during_decision_preparation_cannot_publish_stale_grants(client, monkeypatch):
    from server.memory import control_service
    story, character, _, book = fixture(client)
    authored = grant(client, story, character, book)
    current = view(client, story['branch_id'])
    changed = publish(client, book, content={'text': 'NEW edition.'})
    original = control_service.prepare_controls
    def prepare(connection, branch, body):
        result = original(connection, branch, body)
        adopt(client, changed)
        return result
    monkeypatch.setattr(control_service, 'prepare_controls', prepare)
    response = client.put('/api/branches/' + story['branch_id'] + '/memory-controls', json={
        'operation_id': uuid4().hex, 'expected_revision': current['revision'], 'expected_version_id': current['version_id'], 'entries': [authored]})
    assert response.status_code == 409, response.text
    assert view(client, story['branch_id'])['version_id'] == current['version_id']


def test_unattached_identity_and_reference_based_emphasis_are_rejected(client):
    story, character, _, book = fixture(client)
    authored = grant(client, story, character, book)
    current = view(client, story['branch_id'])
    foreign = asset(client, 'character', 'Outside', {'text': 'Outside profile.'})
    base = {'expected_revision': current['revision'], 'expected_version_id': current['version_id']}
    for invalid in ({**authored, 'character_id': foreign['asset_id']},
                    {**authored, 'character_id': None, 'kind': 'emphasis', 'stance': 'exclude'}):
        response = client.put('/api/branches/' + story['branch_id'] + '/memory-controls', json={
            **base, 'operation_id': uuid4().hex, 'entries': [invalid]})
        assert response.status_code == 409, response.text
