import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

from server.assessment.decision import apply_opportunity
from server.assessment.writing import WritingRequests
from server.database import decode, encode
from server.errors import DomainError
from server.generation_models import GenerateRequest
from server.mechanics.models import TablePublish
from server.mechanics.tables import Tables
from server.memory.budget import token_estimate
from server.operations import remember
from tests.prompt_fixtures import saved_prompt
from tests.test_agent_switches import toggle
from tests.test_archives import backup, restore
from tests.test_assessments import setup_assessment
from tests.test_context_inspector import database_dump, preview
from tests.test_generations import DraftProvider, finished
from tests.test_history import append
from tests.test_library import create_book, publish, with_book
from tests.test_memory import long_story, small_profile
from tests.test_profiles import make_profile


def revise_prompt(client, key='writer'):
    prompt = saved_prompt(client, key)
    response = client.put(f'/api/prompts/{key}', json={'expected_version_id': prompt['id'],
                          'template': '!' + prompt['template'][1:]})
    assert response.status_code == 200, response.text


def guarded_body(report, body):
    return {**body, 'operation_id': uuid4().hex, 'reviewed_fingerprint': report['fingerprint']}


def test_guarded_long_comparison_matches_preview_and_preserves_receipt_through_replay_archive(client):
    first = small_profile(client)
    second = small_profile(client, 'Second', limit=8192)
    story, nodes = long_story(client)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    report, body = preview(client, story, expected_revision=len(nodes),
                           profile_ids=[first['profile_id'], second['profile_id']], direction='The observatory key.')
    request = guarded_body(report, body)
    endpoint = f"/api/branches/{story['branch_id']}/generations"
    response = client.post(endpoint, json=request)
    assert response.status_code == 201, response.text
    run = finished(client, response.json()['id'])
    snapshot = run['snapshot']
    assert snapshot['reviewed_context'] == {'fingerprint': report['fingerprint'], 'stage': 'writer'}
    assert snapshot['memory'] == report['memory']
    assert len(provider.calls) == 2 and provider.calls[0][1:] == provider.calls[1][1:]
    assert provider.calls[0][2] == snapshot['content']
    revise_prompt(client)
    assert client.post(endpoint, json=request).json() == response.json()
    assert len(provider.calls) == 2
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()['snapshot']
    assert restored['reviewed_context'] == snapshot['reviewed_context']
    assert restored['content'] == snapshot['content']


@pytest.mark.parametrize('change', ['prompt', 'profile', 'direction', 'memory', 'branch'])
def test_changed_inputs_block_guarded_dispatch_before_any_records_or_provider_call(client, story, change):
    profile = make_profile(client, 'Writer', primary=True)
    report, body = preview(client, story)
    request = guarded_body(report, body)
    if change == 'prompt':
        revise_prompt(client)
    if change == 'profile':
        updated = client.put(f"/api/profiles/{profile['profile_id']}", json={
            'expected_version_id': profile['id'], 'name': 'Writer',
            'config': {**profile['config'], 'temperature': 0.6}})
        assert updated.status_code == 200, updated.text
    if change == 'direction':
        request['direction'] = 'A different request.'
    if change == 'memory':
        current = client.get(f"/api/stories/{story['story_id']}").json()
        updated = client.put(f"/api/stories/{story['story_id']}", json={
            'expected_revision': current['revision'], 'title': current['title'], 'premise': current['premise'],
            'settings': {**current['settings'], 'memory': {'mode': 'long'}}})
        assert updated.status_code == 200, updated.text
    if change == 'branch':
        append(client, story['branch_id'], 'New accepted prose.', 0)
    before = database_dump(client)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=request)
    assert response.status_code == 409, response.text
    assert database_dump(client) == before and provider.calls == []
    if change != 'branch':
        assert 'reviewed preview' in response.json()['detail']


def test_new_unadopted_canon_version_does_not_invalidate_reviewed_pins(client):
    make_profile(client, 'Writer', primary=True)
    book = create_book(client)
    story = with_book(client, book, 'Pinned city')
    report, body = preview(client, story)
    publish(client, book)
    client.app.state.runner.provider = DraftProvider()
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=guarded_body(report, body))
    assert response.status_code == 201, response.text
    content = finished(client, response.json()['id'])['snapshot']['content']
    assert 'Rain every day.' in content and 'A dry season.' not in content


@pytest.mark.parametrize('change', ['prompt', 'table', 'disabled'])
def test_assessment_contract_detects_same_size_prompt_table_and_activation_changes(client, story, change, monkeypatch):
    setup_assessment(client, story)
    if change == 'table':
        # Legacy/unpinned settings follow the current table catalog. Normally
        # configuring randomness pins versions, which remain stable on publication.
        with client.app.state.database.connect(write=True) as connection:
            row = connection.execute('SELECT settings FROM stories WHERE id=?', (story['story_id'],)).fetchone()
            settings = decode(row['settings'])
            settings['randomness']['table_versions'] = {}
            connection.execute('UPDATE stories SET settings=? WHERE id=?', (encode(settings), story['story_id']))
    report, body = preview(client, story, expected_revision=1)
    if change == 'prompt':
        revise_prompt(client, 'beat-assessment')
    if change == 'table':
        service = Tables(client.app.state.database)
        table = next(item for item in service.list() if item['table_id'] == 'momentum')
        definition = deepcopy(table['definition'])
        definition['note'] += ' Revised author guidance.'
        service.publish('momentum', TablePublish(operation_id=uuid4().hex,
                        expected_version_id=table['id'], definition=definition))
    if change == 'disabled':
        toggle(client, 'beat-assessment')
    refreshed, _ = preview(client, story, expected_revision=1)
    assert refreshed['fingerprint'] == report['fingerprint']
    assert refreshed['assessment']['status'] == 'none'
    assert refreshed['assessment']['budgets'] == []
    monkeypatch.setattr('server.assessment.context.secrets.token_hex', lambda *_: pytest.fail('Writing drew seed'))
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=guarded_body(report, body))
    assert response.status_code == 201, response.text
    assert finished(client, response.json()['id'])['candidates'][0]['status'] == 'done'
    assert client.app.state.assessment_runner.provider.calls == []


def test_guard_is_transport_metadata_and_pending_assessment_does_not_block_writing(client, story):
    from tests.legacy_assessment import legacy_create
    setup_assessment(client, story)
    report, body = preview(client, story, expected_revision=1)
    pending = legacy_create(client.app.state.database, story['branch_id'], GenerateRequest(**body, operation_id=uuid4().hex))
    assert pending['assessment_id']
    refreshed, _ = preview(client, story, expected_revision=1)
    assert refreshed['assessment']['status'] == 'none'
    service = WritingRequests(client.app.state.database)
    request = GenerateRequest(**guarded_body(refreshed, body))
    result = service.create(story['branch_id'], request)
    assert result['id'] and 'assessment_id' not in result
    assert service.create(story['branch_id'], request) == result


def test_guarded_assessment_saves_final_memory_digest_and_archive_provenance(client, story):
    setup_assessment(client, story)
    with client.app.state.database.connect(write=True) as connection:
        row = connection.execute('SELECT settings FROM stories WHERE id=?', (story['story_id'],)).fetchone()
        settings = {**decode(row['settings']), 'memory': {'mode': 'long'}}
        connection.execute('UPDATE stories SET settings=?,revision=revision+1 WHERE id=?',
                           (encode(settings), story['story_id']))
    from server.assessment.preparation import prepare_accepted
    from server.assessment.service import Assessments
    from tests.test_post_acceptance import complete
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    preparation = prepare_accepted(client.app.state.database, story['branch_id'], branch['head_id'])
    assessment = complete(client, Assessments(client.app.state.database).detail(preparation['assessment_id']))
    assert assessment['opportunity_id'] and not assessment['generation_id']
    report, body = preview(client, story, expected_revision=1)
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=guarded_body(report, body))
    assert response.status_code == 201, response.text
    run = finished(client, response.json()['id'])
    snapshot = run['snapshot']
    assert snapshot['reviewed_context']['stage'] == 'writer'
    assert snapshot['reviewed_context']['fingerprint'] == report['fingerprint']
    assert snapshot['memory']['content_sha256'] == hashlib.sha256(snapshot['content'].encode()).hexdigest()
    assert snapshot['memory']['content_sha256'] == report['memory']['content_sha256']
    assert decode(snapshot['content'])['direction'] == body.get('direction', '')
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()['snapshot']
    assert restored['memory'] == snapshot['memory']
    assert restored['reviewed_context'] == snapshot['reviewed_context']


def test_assessed_beat_cannot_consume_long_memory_overhead_margin():
    content = {'history': [], 'direction': ''}
    opportunity = {'writer': {'text': 'A prepared beat.'}}
    after = {**content, 'prepared_beat': opportunity['writer']}
    writer = {'content': encode(content), 'prompt': {'template': 'Write.'}, 'memory': {'overhead_margin': 128, 'receipt_version': 2}}
    profile = {'name': 'Tiny', 'config': {'context_tokens': token_estimate('Write.', after) + 512,
                                       'max_output_tokens': 512}}
    with pytest.raises(DomainError, match='context allowance'):
        apply_opportunity(writer, [profile], 'opportunity', opportunity)


def test_legacy_unreviewed_operation_replays_without_new_null_field(client, story):
    body = GenerateRequest(operation_id=uuid4().hex, expected_revision=0)
    payload = {'branch_id': story['branch_id'], **body.model_dump(exclude={'reviewed_fingerprint', 'knowledge_subject', 'knowledge_character_id'})}
    recorded = {'id': 'historical-result', 'candidate_ids': []}
    with client.app.state.database.connect(write=True) as connection:
        remember(connection, body.operation_id, 'generate', payload, recorded)
    assert WritingRequests(client.app.state.database).create(story['branch_id'], body) == recorded


def test_pinned_random_tables_remain_stable_after_unadopted_publication(client, story):
    setup_assessment(client, story)
    report, body = preview(client, story, expected_revision=1)
    service = Tables(client.app.state.database)
    table = next(item for item in service.list() if item['table_id'] == 'momentum')
    definition = deepcopy(table['definition'])
    definition['note'] += ' A future version.'
    service.publish('momentum', TablePublish(operation_id=uuid4().hex,
                    expected_version_id=table['id'], definition=definition))
    refreshed, _ = preview(client, story, expected_revision=1)
    assert refreshed['fingerprint'] == report['fingerprint']
    response = WritingRequests(client.app.state.database).create(story['branch_id'], GenerateRequest(**guarded_body(report, body)))
    assert response['id']


def test_earlier_saved_assessment_receipts_keep_their_original_serialization():
    content = {'history': [], 'direction': 'Preserve this ordering.'}
    original_memory = {'overhead_margin': 128, 'content_sha256': 'original-receipt'}
    writer = {'content': encode(content), 'prompt': {'template': 'Write.'}, 'memory': deepcopy(original_memory)}
    opportunity = {'writer': {'text': 'A recorded beat.'}}
    after = {**content, 'prepared_beat': opportunity['writer']}
    profiles = [{'name': 'Earlier profile', 'config': {'context_tokens': 4096, 'max_output_tokens': 512}}]
    apply_opportunity(writer, profiles, 'old-opportunity', opportunity)
    assert writer['content'] == encode(after)
    assert writer['memory'] == original_memory
