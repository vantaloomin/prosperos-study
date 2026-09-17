import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.authoring.context import parse_authoring
from server.authoring.models import AuthoringPreview, AuthoringStart
from server.authoring.service import Authoring
from server.database import decode, many
from server.errors import DomainError
from server.providers.events import ProviderEvent
from tests.archive_legacy import remove_authoring
from tests.test_archives import backup, restore
from tests.test_library import create_book, with_book
from tests.test_profiles import make_profile


class AuthoringProvider:
    """Protocol fixture only: never presented as a successful live model call."""
    def __init__(self, invalid=False):
        self.calls, self.invalid = [], invalid

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        target = json.loads(content)['target']['text']
        result = {'summary': 'QA fixture: a focused prose suggestion.',
            'proposal': None if 'Keep proposal null.' in prompt else f"{profile['name']}: rain settles over the harbor.\n\nThe lamps stay lit.\n",
            'findings': [{'quote': target[:30], 'explanation': 'QA fixture observation.', 'suggestion': 'Review the rhythm.'}] if target else []}
        yield ProviderEvent(text='invalid fixture output' if self.invalid else json.dumps(result), done=True)


def request(book=None, **values):
    return {'source_version_id': book['id'] if book else None, 'draft_id': 'qa-draft', 'kind': 'lorebook',
        'name': book['name'] if book else 'Unsaved book', 'target_key': 'text', 'target_label': 'Book overview',
        'text': '  Rain every day.\n', 'context': {'entry:harbor': 'Quiet lamps.\n'}, 'direction': 'Retain the genre.',
        'step': 'authoring-tighten', **values}


async def settle(client):
    await asyncio.gather(*list(client.app.state.authoring_runner.tasks.values()))


def start(client, body):
    preview = client.post('/api/authoring/preview', json=body)
    assert preview.status_code == 200, preview.text
    payload = {**body, 'preview_hash': preview.json()['preview_hash'], 'operation_id': uuid4().hex}
    created = client.post('/api/authoring', json=payload)
    assert created.status_code == 201, created.text
    assert client.post('/api/authoring', json=payload).json() == created.json()
    client.portal.call(settle, client)
    return client.get(f"/api/authoring/{created.json()['id']}").json()


def setup(client):
    profile = make_profile(client, 'Fixture writer', primary=True)
    book = create_book(client)
    client.app.state.authoring_runner.provider = AuthoringProvider()
    return book, profile


def test_comparison_preserves_exact_context_and_cannot_publish_or_progress(client):
    book, first = setup(client)
    second = make_profile(client, 'Fixture alternative')
    story = with_book(client, book, 'Unchanged path')
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    body = request(book, profile_ids=[first['profile_id'], second['profile_id']])
    assert client.post('/api/authoring/preview', json=body).json()['request_count'] == 2
    assert client.app.state.authoring_runner.provider.calls == []
    run = start(client, body)
    assert [job['status'] for job in run['jobs']] == ['done', 'done']
    calls = client.app.state.authoring_runner.provider.calls
    assert len(calls) == 2 and calls[0][1:] == calls[1][1:]
    assert json.loads(calls[0][2])['target']['text'] == body['text']
    assert all('credential_ref' not in job['snapshot']['profile'] for job in run['jobs'])
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert len(client.get(f"/api/library/{book['asset_id']}/versions").json()) == 1
    assert client.post(f"/api/authoring-jobs/{run['jobs'][0]['id']}/apply", json={}).status_code == 405
    assert client.get('/api/authoring', params={'asset_id': book['asset_id']}).json()[0]['id'] == run['id']


def test_defaults_prompt_versions_and_stale_preview(client, story):
    book, primary = setup(client)
    second = make_profile(client, 'Editor specialist')
    body = request(book)
    preview = client.post('/api/authoring/preview', json=body).json()
    assert preview['jobs'][0]['profile_name'] == primary['name']
    assert client.put('/api/authoring/defaults', json={'step': body['step'], 'profile_id': second['profile_id']}).status_code == 200
    stale = {**body, 'operation_id': uuid4().hex, 'preview_hash': preview['preview_hash']}
    assert client.post('/api/authoring', json=stale).status_code == 409
    run = start(client, body)
    assert run['jobs'][0]['snapshot']['profile']['profile_id'] == second['profile_id']
    preview = client.post('/api/authoring/preview', json=body).json()
    prompt = next(item for item in client.get('/api/prompts').json() if item['key'] == body['step'])
    assert client.put(f"/api/prompts/{body['step']}", json={'expected_version_id': prompt['id'], 'template': prompt['template'] + '\nBe concise.'}).status_code == 200
    assert client.post('/api/authoring', json={**stale, 'preview_hash': preview['preview_hash']}).status_code == 409
    assert run['jobs'][0]['snapshot']['prompt']['id'] == prompt['id']
    assert not any(item['key'].startswith('authoring-') for item in client.get(f"/api/prompts?story_id={story['story_id']}").json())
    assert client.put('/api/authoring/defaults', json={'step': body['step'], 'profile_id': None}).json() == {}


@pytest.mark.parametrize('step', ['authoring-draft', 'authoring-critique', 'authoring-tighten'])
def test_output_contract_and_exact_quote_validation(client, step):
    book, _ = setup(client)
    run = start(client, request(book, step=step))
    job = run['jobs'][0]
    assert job['status'] == 'done'
    assert (job['result']['proposal'] is None) == (step == 'authoring-critique')
    invalid = deepcopy(job['result'])
    invalid['findings'][0]['quote'] = 'NOT IN THE REVIEWED PROSE'
    with pytest.raises(DomainError):
        parse_authoring(json.dumps(invalid), job['snapshot'])
    invalid = {**job['result'], 'publish': True}
    with pytest.raises(DomainError):
        parse_authoring(json.dumps(invalid), job['snapshot'])


def test_retry_preserves_attempt_and_frozen_input(client):
    book, _ = setup(client)
    client.app.state.authoring_runner.provider = AuthoringProvider(invalid=True)
    run = start(client, request(book))
    job = run['jobs'][0]
    assert job['status'] == 'error' and job['output'] == 'invalid fixture output'
    client.app.state.authoring_runner.provider = AuthoringProvider()
    assert client.post(f"/api/authoring-jobs/{job['id']}/retry").status_code == 200
    client.portal.call(settle, client)
    retried = client.get(f"/api/authoring/{run['id']}").json()['jobs'][0]
    assert retried['status'] == 'done' and retried['snapshot'] == job['snapshot']
    assert retried['attempt'] == 2
    attempts = client.get(f"/api/authoring-jobs/{job['id']}/attempts").json()
    assert [item['status'] for item in attempts] == ['done', 'error']
    assert client.post(f"/api/authoring-jobs/{job['id']}/retry").status_code == 409


def test_cancel_and_restart_leave_explicit_retry(client):
    book, _ = setup(client)
    service = Authoring(client.app.state.database)
    body = request(book)
    created = service.create(AuthoringStart(**body, preview_hash=service.preview(AuthoringPreview(**body))['preview_hash'], operation_id=uuid4().hex))
    job_id = created['job_ids'][0]
    assert client.post(f'/api/authoring-jobs/{job_id}/stop').json()['stopped']
    assert service.detail(created['id'])['jobs'][0]['status'] == 'cancelled'
    with client.app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE authoring_jobs SET status='running',output='partial',attempt=1 WHERE id=?", (job_id,))
    client.app.state.authoring_runner.recover()
    job = service.detail(created['id'])['jobs'][0]
    assert job['status'] == 'interrupted' and job['output'] == 'partial'
    assert client.app.state.authoring_runner.provider.calls == []


def test_archive_recovers_unsaved_runs_sources_outputs_and_rejects_tampering(client):
    book, profile = setup(client)
    story = with_book(client, book, 'Linked book')
    saved = start(client, request(book))
    unsaved = start(client, request())
    client.put('/api/authoring/defaults', json={'step': 'authoring-tighten', 'profile_id': profile['profile_id']})
    file, document = backup(client)
    assert document['version'] == 19 and len(document['data']['authoring_runs']) == 2
    assert document['authoring_profiles'] == {'authoring-tighten': profile['profile_id']}
    _, mapping = restore(client, file)
    restored = client.get(f"/api/authoring/{mapping[saved['id']]}").json()
    assert restored['source_version_id'] == mapping[book['id']]
    assert restored['snapshot']['content'] == saved['snapshot']['content']
    assert restored['jobs'][0]['result'] == saved['jobs'][0]['result']
    assert client.get(f"/api/authoring/{mapping[unsaved['id']]}").json()['asset_id'] is None
    backup(client)
    _, scoped = backup(client, story)
    assert len(scoped['data']['authoring_runs']) == 1
    corrupted = deepcopy(document)
    corrupted['data']['authoring_jobs'][0]['result'] = '{}'
    with pytest.raises(DomainError):
        parse_archive(json.dumps(corrupted))
    corrupted = deepcopy(document)
    snapshot = json.loads(corrupted['data']['authoring_jobs'][0]['snapshot'])
    snapshot['prompt']['template'] += '\nUnrecorded change'
    corrupted['data']['authoring_jobs'][0]['snapshot'] = json.dumps(snapshot)
    with pytest.raises(DomainError):
        parse_archive(json.dumps(corrupted))


def test_legacy_upgrade_empty_history_and_source_kind_and_capacity_checks(client):
    book, profile = setup(client)
    _, document = backup(client)
    remove_authoring(document)
    document['version'] = 15
    upgraded = parse_archive(json.dumps(document))
    assert upgraded['version'] == 19 and upgraded['data']['authoring_runs'] == []
    assert client.post('/api/authoring/preview', json=request(book, kind='character')).status_code == 400
    assert client.post('/api/authoring/preview', json=request(book, profile_ids=[profile['profile_id']]*2)).status_code == 400
    assert client.post('/api/authoring/preview', json=request(book, text='x'*100000)).status_code == 409
    assert client.post('/api/authoring/preview', json=request(book, context={str(i): 'x'*100000 for i in range(20)})).status_code == 422
    with client.app.state.database.connect() as connection:
        assert many(connection, 'SELECT * FROM authoring_runs') == []
        assert decode(connection.execute('SELECT content FROM asset_versions WHERE id=?', (book['id'],)).fetchone()['content'])['text'] == book['content']['text']


def test_paged_history_and_archive_interrupt_pending_requests_without_model_calls(client):
    book, _ = setup(client)
    service = Authoring(client.app.state.database)
    body = request(book)
    preview = service.preview(AuthoringPreview(**body))
    created = [service.create(AuthoringStart(**body, preview_hash=preview['preview_hash'], operation_id=uuid4().hex)) for _ in range(3)]
    history = client.get('/api/authoring', params={'asset_id': book['asset_id'], 'offset': 1}).json()
    assert all(row['target_label'] == 'Book overview' for row in history)
    assert [row['id'] for row in history] == [row['id'] for row in reversed(created[:2])]
    assert client.get('/api/authoring?offset=-1').status_code == 422
    file, _ = backup(client)
    _, mapping = restore(client, file)
    restored = service.detail(mapping[created[0]['id']])
    assert restored['jobs'][0]['status'] == 'interrupted'
    assert client.app.state.authoring_runner.provider.calls == []
