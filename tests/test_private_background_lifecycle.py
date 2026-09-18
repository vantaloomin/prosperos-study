import asyncio
import json
from copy import deepcopy
from uuid import uuid4

from server.archives.format import ARCHIVE_VERSION
from server.background.storage import state_id
from server.database import decode
from server.providers.events import ProviderEvent
from tests.archive_legacy import remove_interpretations
from tests.test_archives import backup, restore
from tests.test_background import fork, prepared, revealed, setup_story, update
from tests.test_background_interpretations import (
    PrivateProvider,
    choose_private,
    setup_private,
    start_private,
    wait_jobs,
)
from tests.test_generations import DraftProvider, finished, generate
from tests.test_history import append
from tests.test_sidebar import ask, settle, thread


class PausedPrivateProvider:
    def __init__(self):
        self.started = asyncio.Event()

    async def generate(self, _profile, _prompt, _content):
        yield ProviderEvent(text='{"drives": [')
        self.started.set()
        await asyncio.Event().wait()


def test_stop_keeps_partial_private_output_and_retry_reuses_exact_inputs(client):
    story, receipt, _ = setup_private(client)
    provider = PausedPrivateProvider()
    client.app.state.background_runner.provider = provider
    endpoint = f"/api/branches/{story['branch_id']}/background/interpretations"
    body = {'expected_revision': 1}
    preview = client.post(endpoint + '/preview', json=body).json()
    created = client.post(endpoint, json={**body, 'operation_id': uuid4().hex, 'preview_hash': preview['preview_hash']}).json()
    client.portal.call(asyncio.wait_for, provider.started.wait(), 2)
    job_id = created['job_ids'][0]
    assert client.post(f'/api/background-jobs/{job_id}/stop').status_code == 200
    client.portal.call(wait_jobs, client)
    detail_url = f"/api/background-interpretations/{created['id']}?reveal=true"
    stopped = client.get(detail_url).json()['jobs'][0]
    assert stopped['status'] == 'cancelled' and stopped['output'] == '{"drives": ['
    assert choose_private(client, stopped).status_code == 409
    client.app.state.background_runner.provider = PrivateProvider()
    assert client.post(f'/api/background-jobs/{job_id}/retry').status_code == 200
    client.portal.call(wait_jobs, client)
    completed = client.get(detail_url).json()['jobs'][0]
    assert completed['status'] == 'done' and completed['snapshot'] == stopped['snapshot']
    attempts = client.get(f'/api/background-jobs/{job_id}/attempts/reveal').json()
    assert [item['status'] for item in attempts] == ['done', 'cancelled']
    assert attempts[1]['output'] == stopped['output']
    assert client.get(f"/api/branches/{story['branch_id']}/background").json()['current'] == receipt['id']


def test_selected_details_follow_writer_and_historical_boundaries_without_leaking_to_siblings(client):
    story, receipt, _ = setup_private(client)
    before = append(client, story['branch_id'], 'Before specific motives.', 1)
    run = start_private(client, story)
    chosen = choose_private(client, run['jobs'][0]).json()
    later = append(client, story['branch_id'], 'After private preparation.', 3)
    old_path = fork(client, story, before)
    new_path = fork(client, story, later)
    with client.app.state.database.connect() as connection:
        assert state_id(connection, old_path) == receipt['id']
        assert state_id(connection, new_path) == chosen['id']
    client.app.state.runner.provider = DraftProvider()
    target = {**story, 'branch_id': new_path}
    revision = client.get(f'/api/branches/{new_path}').json()['revision']
    draft = finished(client, generate(client, target, revision=revision)['id'])
    private = decode(draft['snapshot']['content'])['private_background']
    assert private['selected_private_interpretation']['drives'][0]['motive'].startswith('Private writer:')
    changed = update(client, target)
    assert revealed(client, changed)['interpretation'] == revealed(client, chosen)['interpretation']
    paused = finished(client, generate(client, target, revision=revision + 1)['id'])
    assert not decode(paused['snapshot']['content'])['private_background']['selected_private_interpretation']['drives']
    assert decode(draft['snapshot']['content'])['private_background'] == private
    assert 'interpretation' not in revealed(client, receipt)


def test_version_ten_restore_keeps_original_setup_without_inventing_interpretations(client):
    story, character = setup_story(client)
    receipt = prepared(client, story, character)
    before = revealed(client, receipt)
    _, document = backup(client, story)
    remove_interpretations(document)
    document['version'] = 10
    document['data'].pop('library_imports', None)
    document['data'].pop('asset_import_origins', None)
    document['data'].pop('asset_sources', None)
    document.pop('library_drafts', None)
    staged = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert staged.status_code == 201, staged.text
    assert staged.json()['summary']['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, staged.json())
    recovered = revealed(client, {'id': mapping[receipt['id']]})
    assert recovered['result']['seed'] == before['result']['seed']
    assert recovered['result']['draws'] == before['result']['draws']
    assert 'interpretation' not in recovered
    assert client.get(f"/api/branches/{mapping[story['branch_id']]}/background/interpretations").json() == []


def test_archive_rejects_altered_private_content_and_cross_story_selected_links(client):
    story, _, _ = setup_private(client)
    run = start_private(client, story)
    chosen = choose_private(client, run['jobs'][0]).json()
    other, character = setup_story(client)
    foreign = prepared(client, other, character)
    _, document = backup(client)
    altered = deepcopy(document)
    row = next(item for item in altered['data']['background_states'] if item['id'] == chosen['id'])
    snapshot = decode(row['snapshot'])
    snapshot['interpretation']['content']['drives'][0]['motive'] = 'Altered after selection'
    row['snapshot'] = json.dumps(snapshot)
    response = client.post('/api/archives/imports', json={'content': json.dumps(altered)})
    assert response.status_code == 400 and 'Private details differ' in response.text
    document['data']['background_jobs'][0]['selected_state_id'] = foreign['id']
    response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert response.status_code == 400 and 'invalid ownership' in response.text


class PrivateSourceReader:
    def __init__(self):
        self.calls = []

    async def generate(self, _profile, _prompt, content):
        context = json.loads(content)
        self.calls.append(context)
        if any(item['id'].startswith('private-interpretation:') for item in context['sources']):
            yield ProviderEvent(text='The saved private proposals are available for discussion.', done=True)
        else:
            ids = [item['id'] for item in context['source_index'] if item['id'].startswith('private-interpretation:')][:2]
            yield ProviderEvent(text='READ_SOURCES: ' + json.dumps(ids), done=True)


def test_collaborator_can_retrieve_private_model_history_without_selecting_or_advancing(client):
    story, receipt, _ = setup_private(client)
    run = start_private(client, story)
    client.app.state.side_runner.provider = PrivateSourceReader()
    conversation = thread(client, story)
    ask(client, conversation, story, revision=1, disclosure='full-disclosure')
    settle(client)
    context = client.app.state.side_runner.provider.calls[-1]
    docs = [item for item in context['sources'] if item['id'].startswith('private-interpretation:')]
    assert docs and any('missing ledger' in item['text'] for item in docs)
    assert client.get(f"/api/background-interpretations/{run['id']}").json()['jobs'][0]['selected_state_id'] is None
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert branch['revision'] == 1 and branch['messages'] == []
    assert client.get(f"/api/branches/{story['branch_id']}/background").json()['current'] == receipt['id']
