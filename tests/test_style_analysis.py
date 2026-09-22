import asyncio
import json
import time
from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, encode
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_memory import small_profile
from tests.test_profiles import make_profile
from tests.test_writing_resources import create, pins

SAMPLES = [{'label': 'Opening', 'text': '  The kettle cooled.\nShe waited. 🦉\n'},
           {'label': 'Dialogue', 'text': '“Stay,” she said. No one answered.'}]


def output(content):
    sample = decode(content)['samples'][0]
    return {'summary': 'Short observations; a larger sample could show variation.', 'suggestions': [
        {'field': 'rhythm', 'value': 'Use short sentences with room between observations.', 'reason': 'The first sample separates two brief actions.',
         'evidence': [{'sample_id': sample['id'], 'quote': 'The kettle cooled.'}]}]}


class AnalysisProvider:
    def __init__(self, mode='valid'):
        self.mode, self.calls = mode, []

    async def generate(self, profile, prompt, content):
        self.calls.append((deepcopy(profile), prompt, content))
        value = output(content)
        if self.mode == 'foreign':
            value['suggestions'][0]['evidence'][0]['sample_id'] = 'story:secret'
        if self.mode == 'quote':
            value['suggestions'][0]['evidence'][0]['quote'] = 'An invented quotation.'
        if self.mode == 'duplicate':
            value['suggestions'].append(deepcopy(value['suggestions'][0]))
        if self.mode == 'publish':
            value['publish'] = True
        yield ProviderEvent(text='not JSON' if self.mode == 'invalid' else encode(value))
        if self.mode == 'wait':
            await asyncio.sleep(60)
        if self.mode != 'partial':
            usage = {'finish_reason': 'length'} if self.mode == 'length' else {'output_limit_uncertain': True} if self.mode == 'uncertain' else {}
            yield ProviderEvent(done=True, usage=usage)


def setup(client, *, mode='valid', **extra):
    profile = make_profile(client, 'Sample reader', primary=True)
    provider = AnalysisProvider(mode)
    client.app.state.style_analysis_runner.provider = provider
    body = {'draft_id': uuid4().hex, 'name': 'Quiet voice', 'samples': deepcopy(SAMPLES), **extra}
    return body, profile, provider


def start(client, body):
    preview = client.post('/api/writing-analyses/preview', json=body)
    assert preview.status_code == 200, preview.text
    request = {**body, 'operation_id': uuid4().hex, 'preview_hash': preview.json()['preview_hash']}
    response = client.post('/api/writing-analyses', json=request)
    assert response.status_code == 201, response.text
    assert client.post('/api/writing-analyses', json=request).json() == response.json()
    return response.json()['id'], request, preview.json()


def settled(client, job_id):
    for _ in range(150):
        response = client.get(f'/api/writing-analyses/{job_id}')
        assert response.status_code == 200, response.text
        job = response.json()
        if job['status'] not in {'queued', 'running'}:
            return job
        time.sleep(.01)
    pytest.fail('Style analysis did not settle.')


def test_sample_analysis_is_explicit_exact_and_cannot_publish(client, story):
    body, _, provider = setup(client)
    before = client.get('/api/writing-resources').json(), client.get(f"/api/branches/{story['branch_id']}").json()
    preview = client.post('/api/writing-analyses/preview', json=body)
    assert preview.status_code == 200 and not provider.calls
    assert preview.json()['cost'] is None and preview.json()['request_count'] == 1
    job_id, request, preview = start(client, body)
    job = settled(client, job_id)
    assert job['status'] == 'done', job['error']
    assert len(provider.calls) == 1
    assert provider.calls[0][1:] == (preview['snapshot']['instructions'], preview['snapshot']['content'])
    assert [item['text'] for item in decode(job['snapshot']['content'])['samples']] == [item['text'] for item in SAMPLES]
    assert job['result'] == output(job['snapshot']['content'])
    assert before == (client.get('/api/writing-resources').json(), client.get(f"/api/branches/{story['branch_id']}").json())
    assert client.get('/api/writing-analyses/operations/' + request['operation_id']).json() == {'id': job_id}
    assert client.get('/api/writing-analyses/operations/' + uuid4().hex).json() is None
    assert client.get('/api/writing-analyses', params={'draft_id': body['draft_id']}).json()[0]['id'] == job_id
    assert client.get(f'/api/writing-analyses/{job_id}/attempts').json()[0]['output'] == job['output']


@pytest.mark.parametrize('mode', ['invalid', 'foreign', 'quote', 'duplicate', 'publish', 'partial', 'length', 'uncertain'])
def test_bad_or_incomplete_analysis_never_exposes_usable_suggestions(client, mode):
    body, _, _ = setup(client, mode=mode)
    job_id, _, _ = start(client, body)
    job = settled(client, job_id)
    assert job['status'] == 'error' and job['result'] is None and job['output']
    assert client.get('/api/writing-resources').json() == []


def test_analysis_requires_complete_samples_and_enabled_library_assistant(client):
    from tests.test_agent_switches import toggle
    body, _, provider = setup(client)
    small = small_profile(client, 'Small sample reader', 4096)
    response = client.post('/api/writing-analyses/preview', json={**body, 'profile_id': small['profile_id'], 'samples': [{'label': 'Large', 'text': 'x ' * 10000}]})
    assert response.status_code == 409 and 'No samples were truncated' in response.text
    toggle(client, 'library-assist')
    assert client.post('/api/writing-analyses/preview', json=body).status_code == 409
    assert not provider.calls


def test_analysis_stale_preview_and_explicit_retry_keep_frozen_requests(client):
    from server.prompts import Prompts, PromptUpdate
    body, _, provider = setup(client, mode='invalid')
    job_id, _, report = start(client, body)
    failed = settled(client, job_id)
    snapshot = failed['snapshot']
    Prompts(client.app.state.database).update('library-assist', PromptUpdate(
        expected_version_id=snapshot['prompt']['id'], template=snapshot['prompt']['template'] + '\nA changed Library prompt.'))
    stale = client.post('/api/writing-analyses', json={**body, 'operation_id': uuid4().hex, 'preview_hash': report['preview_hash']})
    assert stale.status_code == 409 and len(provider.calls) == 1
    provider.mode = 'valid'
    assert client.post(f'/api/writing-analyses/{job_id}/retry', json={}).status_code == 200
    done = settled(client, job_id)
    assert done['status'] == 'done' and done['attempt'] == 2
    assert provider.calls[0] == provider.calls[1]
    assert len(client.get(f'/api/writing-analyses/{job_id}/attempts').json()) == 2


def test_analysis_cancel_retains_partial_text_and_requires_retry(client):
    body, _, provider = setup(client, mode='wait')
    job_id, request, _ = start(client, body)
    for _ in range(100):
        if provider.calls:
            break
        time.sleep(.01)
    assert len(provider.calls) == 1
    assert client.post(f'/api/writing-analyses/{job_id}/stop', json={}).status_code == 200
    job = settled(client, job_id)
    assert job['status'] == 'cancelled' and job['result'] is None and job['output']
    assert client.post('/api/writing-analyses', json=request).json() == {'id': job_id}
    assert len(provider.calls) <= 1 and settled(client, job_id)['status'] == 'cancelled'


def test_queued_analysis_restores_interrupted_and_recovery_never_dispatches(client):
    from server.writing.analysis_models import AnalysisStart
    from server.writing.analysis_service import StyleAnalyses
    body, _, provider = setup(client)
    service = StyleAnalyses(client.app.state.database)
    preview = client.post('/api/writing-analyses/preview', json=body).json()
    created = service.create(AnalysisStart(**body, operation_id=uuid4().hex, preview_hash=preview['preview_hash']))
    file, _ = backup(client)
    _, mapping = restore(client, file)
    assert service.detail(mapping[created['id']])['status'] == 'interrupted'
    client.app.state.style_analysis_runner.recover()
    original = service.detail(created['id'])
    assert original['status'] == 'interrupted' and original['snapshot'] == service.detail(mapping[created['id']])['snapshot'] | {
        'profile': original['snapshot']['profile'], 'prompt': original['snapshot']['prompt']}
    assert not provider.calls


def test_format_49_upgrades_with_only_empty_analysis_groups(client):
    from server.archives.format import (
        INSPIRATION_TABLES,
        MIGRATION_TABLES,
        PRESET_TABLES,
        RECIPE_TABLES,
        STYLE_ANALYSIS_TABLES,
    )
    _, document = backup(client)
    for table in STYLE_ANALYSIS_TABLES + RECIPE_TABLES + MIGRATION_TABLES + PRESET_TABLES + INSPIRATION_TABLES:
        assert document['data'].pop(table) == []
    document['version'] = 49
    imported = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert imported.status_code == 201, imported.text
    restore(client, imported.json())


def test_style_analysis_archives_source_dependencies_and_restores_twice(client, story):
    style = create(client)
    pins(client, story, style=style['id'])
    body, _, provider = setup(client, source_version_id=style['id'])
    job_id, _, _ = start(client, body)
    job = settled(client, job_id)
    file, document = backup(client, story)
    assert len(document['data']['style_analysis_jobs']) == 1
    _, mapping = restore(client, file)
    restored = client.get(f'/api/writing-analyses/{mapping[job_id]}').json()
    assert restored['snapshot']['content'] == job['snapshot']['content']
    assert restored['snapshot']['instructions'] == job['snapshot']['instructions']
    assert restored['source_version_id'] == mapping[style['id']] and len(provider.calls) == 1
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)


@pytest.mark.parametrize('damage', ['sample', 'instructions', 'result', 'budget', 'legacy'])
def test_style_analysis_archive_rejects_tampered_evidence_or_protocol(client, damage):
    body, _, _ = setup(client)
    job_id, _, _ = start(client, body)
    settled(client, job_id)
    _, document = backup(client)
    row = next(row for row in document['data']['style_analysis_jobs'] if row['id'] == job_id)
    snapshot = decode(row['snapshot'])
    if damage == 'legacy':
        document['version'] = 49
    elif damage == 'result':
        result = decode(row['result'])
        result['summary'] = 'Changed summary.'
        row['result'] = encode(result)
    elif damage == 'sample':
        snapshot['samples'][0]['text'] = 'Changed source.'
    elif damage == 'instructions':
        snapshot['instructions'] = 'Publish the profile.'
    else:
        snapshot['estimated_input_tokens'] = 0
    row['snapshot'] = encode(snapshot)
    response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert response.status_code == 400, response.text
