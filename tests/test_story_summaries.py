import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.memory.summary_context import parse_summary
from server.providers.events import ProviderEvent
from tests.archive_legacy import remove_summaries
from tests.prompt_fixtures import saved_prompt
from tests.test_archives import backup, restore
from tests.test_profiles import make_profile

TEXT = '雨 🔑 Elin says the key may open the Moon Gate. She has never tried it.'


class SummaryProvider:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.wait = False

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        if self.wait:
            yield ProviderEvent(text='{"items":[')
            await asyncio.sleep(30)
        if self.fail:
            yield ProviderEvent(text='Malformed but preserved', done=True)
            return
        sources = decode(content)['sources']
        items = [{'source_id': source['id'], 'summary': 'Elin makes an untested claim.',
                  'quotes': [source['text'][:100]], 'topics': ['testimony'], 'aliases': ['lunar doorway']}
                 for source in sources]
        yield ProviderEvent(text=encode({'items': items}), usage={'output_tokens': 45}, done=True)


def setup(client):
    profile = make_profile(client, 'Memory primary', primary=True)
    story = client.post('/api/stories', json={'title': 'The uncertain gate', 'opening_text': TEXT,
        'settings': {'memory': {'mode': 'long'}}, 'premise': 'PRIVATE PREMISE must not reach summaries.'}).json()
    client.app.state.summary_runner.provider = SummaryProvider()
    return story, profile


def prepared(client, branch_id, **extra):
    sources = client.get('/api/branches/' + branch_id + '/summary-sources').json()
    body = {'expected_revision': sources['revision'], 'source_ids': [item['id'] for item in sources['items']], **extra}
    preview = client.post('/api/branches/' + branch_id + '/summary-preview', json=body)
    assert preview.status_code == 200, preview.text
    return {**body, 'preview_hash': preview.json()['preview_hash'], 'operation_id': uuid4().hex}, preview.json()


async def settle(client):
    for _ in range(100):
        tasks = list(client.app.state.summary_runner.tasks.values())
        if not tasks:
            return
        await asyncio.sleep(0.01)
    assert not client.app.state.summary_runner.tasks


def started(client, branch_id, body=None):
    body = body or prepared(client, branch_id)[0]
    response = client.post('/api/branches/' + branch_id + '/summaries', json=body)
    assert response.status_code == 201, response.text
    assert client.post('/api/branches/' + branch_id + '/summaries', json=body).json() == response.json()
    client.portal.call(settle, client)
    return detail(client, response.json()['id'], branch_id)


def detail(client, run_id, branch_id):
    response = client.get('/api/summaries/' + run_id, params={'branch_id': branch_id})
    assert response.status_code == 200, response.text
    return response.json()


def publication(client, run, branch_id, **extra):
    branch = client.get('/api/branches/' + branch_id).json()
    job = run['jobs'][0]
    return {'operation_id': uuid4().hex, 'branch_id': branch_id, 'expected_revision': branch['revision'],
            'job_id': job['id'], 'result': job['result'], **extra}


def test_comparison_review_versions_exclusion_and_double_archive_replay(client):
    story, primary = setup(client)
    branch_id = story['branch_id']
    alternate = make_profile(client, 'Memory alternate')
    body, preview = prepared(client, branch_id, profile_ids=[primary['profile_id'], alternate['profile_id']])
    assert preview['request_count'] == 2 and not client.app.state.summary_runner.provider.calls
    before = client.get('/api/branches/' + branch_id).json()
    run = started(client, branch_id, body)
    assert all(job['status'] == 'done' for job in run['jobs']), run
    calls = client.app.state.summary_runner.provider.calls
    assert len(calls) == 2 and calls[0][1:] == calls[1][1:]
    assert 'PRIVATE PREMISE' not in calls[0][2]
    assert len(decode(calls[0][2])['sources']) == 1
    assert run['current_version'] is None
    publish = publication(client, run, branch_id)
    publish['result']['items'][0]['summary'] = 'AUTHOR: a claim, not proof.'
    saved = client.post('/api/summaries/' + run['id'] + '/versions', json=publish)
    assert saved.status_code == 201, saved.text
    assert client.post('/api/summaries/' + run['id'] + '/versions', json=publish).json() == saved.json()
    stale = {**publish, 'operation_id': uuid4().hex}
    assert client.post('/api/summaries/' + run['id'] + '/versions', json=stale).status_code == 409
    exclusion = {**stale, 'expected_version_id': saved.json()['id'], 'enabled': False}
    excluded = client.post('/api/summaries/' + run['id'] + '/versions', json=exclusion)
    assert excluded.status_code == 201, excluded.text
    latest = detail(client, run['id'], branch_id)
    assert latest['current_version']['enabled'] == 0 and len(latest['versions']) == 2
    assert client.get('/api/branches/' + branch_id).json() == before
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied = detail(client, mapping[run['id']], mapping[branch_id])
    assert copied['jobs'][0]['snapshot']['content'] == run['jobs'][0]['snapshot']['content']
    assert copied['jobs'][0]['output'] == run['jobs'][0]['output']
    assert copied['current_version']['result'] == latest['current_version']['result']
    assert copied['snapshot']['source_links'][0]['node_id'] == mapping[run['snapshot']['source_links'][0]['node_id']]
    second_file, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch_id]})
    restore(client, second_file)


def fork(client, branch_id, node_id, replacement=None):
    branch = client.get('/api/branches/' + branch_id).json()
    response = client.post('/api/branches/' + branch_id + '/forks', json={'operation_id': uuid4().hex,
        'expected_revision': branch['revision'], 'node_id': node_id, 'name': 'Another path', 'replacement': replacement})
    assert response.status_code == 201, response.text
    return response.json()['branch_id']


def test_late_publication_and_forks_never_inherit_replaced_or_future_sources(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    run = started(client, branch_id)
    branch = client.get('/api/branches/' + branch_id).json()
    first_node = branch['head_id']
    sibling = fork(client, branch_id, first_node)
    changed = fork(client, branch_id, first_node, 'Elin says nothing about the gate.')
    body = publication(client, run, changed)
    assert client.post('/api/summaries/' + run['id'] + '/versions', json=body).status_code == 409
    later = client.post('/api/branches/' + branch_id + '/messages', json={'operation_id': uuid4().hex,
        'expected_revision': branch['revision'], 'text': 'They reach the gate.', 'role': 'narrator'})
    assert later.status_code == 201, later.text
    saved = client.post('/api/summaries/' + run['id'] + '/versions', json=publication(client, run, branch_id))
    assert saved.status_code == 201, saved.text
    assert detail(client, run['id'], sibling)['current_version'] is None
    assert detail(client, run['id'], changed)['current_version'] is None
    extended = fork(client, branch_id, client.get('/api/branches/' + branch_id).json()['head_id'])
    assert detail(client, run['id'], extended)['current_version']['id'] == saved.json()['id']
    other = client.post('/api/stories', json={'title': 'Unrelated', 'opening_text': TEXT}).json()
    assert client.post('/api/summaries/' + run['id'] + '/versions', json=publication(client, run, other['branch_id'])).status_code == 409


def test_sources_are_bounded_distinct_and_never_ooc(client):
    story, _ = setup(client)
    branch_id = story['branch_id']
    branch = client.get('/api/branches/' + branch_id).json()
    client.post('/api/branches/' + branch_id + '/messages', json={'operation_id': uuid4().hex,
        'expected_revision': branch['revision'], 'text': 'PRIVATE OOC guidance', 'role': 'ooc'})
    body, preview = prepared(client, branch_id)
    assert 'PRIVATE OOC' not in preview['jobs'][0]['content']
    duplicate = {key: value for key, value in body.items() if key not in {'operation_id', 'preview_hash'}}
    duplicate['source_ids'] *= 2
    assert client.post('/api/branches/' + branch_id + '/summary-preview', json=duplicate).status_code == 400
    duplicate['source_ids'] = ['missing source']
    assert client.post('/api/branches/' + branch_id + '/summary-preview', json=duplicate).status_code == 409


@pytest.mark.parametrize('kind', ['foreign', 'quote', 'duplicate', 'unknown-field'])
def test_summary_rejects_invented_sources_and_quotes(client, kind):
    story, _ = setup(client)
    job = started(client, story['branch_id'])['jobs'][0]
    output = decode(job['output'])
    item = output['items'][0]
    if kind == 'foreign':
        item['source_id'] = 'not-in-this-path'
    elif kind == 'quote':
        item['quotes'] = ['She knows that the gate will open.']
    elif kind == 'duplicate':
        output['items'].append(item)
    else:
        output['advance_story'] = True
    with pytest.raises(DomainError):
        parse_summary(encode(output), job['snapshot'])


def test_failed_retry_keeps_original_inputs_after_prompt_change_and_no_automatic_publish(client):
    story, _ = setup(client)
    provider = client.app.state.summary_runner.provider
    provider.fail = True
    run = started(client, story['branch_id'])
    job = run['jobs'][0]
    assert job['status'] == 'error' and job['output'] == 'Malformed but preserved'
    prompt = saved_prompt(client, 'memory-summary')
    changed = client.put('/api/prompts/memory-summary', json={'expected_version_id': prompt['id'], 'template': 'NEW instructions'})
    assert changed.status_code == 200, changed.text
    provider.fail = False
    assert client.post('/api/summary-jobs/' + job['id'] + '/retry').status_code == 200
    client.portal.call(settle, client)
    assert provider.calls[0] == provider.calls[1]
    finished = detail(client, run['id'], story['branch_id'])
    assert finished['jobs'][0]['status'] == 'done' and finished['current_version'] is None
    attempts = client.get('/api/summary-jobs/' + job['id'] + '/attempts').json()
    assert len(attempts) == 2 and attempts[-1]['output'] == 'Malformed but preserved'


@pytest.mark.parametrize('kind', ['content', 'node', 'result', 'version-quote', 'parent-cycle'])
def test_archive_rejects_summary_tampering(client, kind):
    story, _ = setup(client)
    run = started(client, story['branch_id'])
    assert client.post('/api/summaries/' + run['id'] + '/versions', json=publication(client, run, story['branch_id'])).status_code == 201
    _, document = backup(client, story)
    data = document['data']
    if kind in {'content', 'node'}:
        snapshot = decode(data['summary_runs'][0]['snapshot'])
        if kind == 'content':
            content = decode(snapshot['content'])
            content['sources'][0]['text'] = 'A different account.'
            snapshot['content'] = encode(content)
        else:
            snapshot['source_links'][0]['node_id'] = 'not-in-this-story'
        data['summary_runs'][0]['snapshot'] = encode(snapshot)
    elif kind == 'result':
        data['summary_jobs'][0]['result'] = '{"items":[]}'
    elif kind == 'version-quote':
        result = decode(data['summary_versions'][0]['result'])
        result['items'][0]['quotes'] = ['Invented quote']
        data['summary_versions'][0]['result'] = encode(result)
    else:
        data['summary_versions'][0]['parent_id'] = data['summary_versions'][0]['id']
    with pytest.raises(DomainError):
        parse_archive(encode(document))


def test_old_archive_upgrade_is_opt_in_and_does_not_modify_original(client):
    setup(client)
    _, legacy = backup(client)
    remove_summaries(legacy)
    legacy['version'] = 20
    original = deepcopy(legacy)
    upgraded = parse_archive(encode(legacy))
    assert upgraded['version'] == ARCHIVE_VERSION and 'memory-summary' in upgraded['prompt_heads']
    assert upgraded['data']['summary_runs'] == [] and legacy == original


def update_memory(client, story_id, enabled):
    story = client.get('/api/stories/' + story_id).json()
    settings = {**story['settings'], 'memory': {**story['settings']['memory'], 'summary_recall': enabled}}
    response = client.put('/api/stories/' + story_id, json={'expected_revision': story['revision'],
        'title': story['title'], 'premise': story['premise'], 'settings': settings})
    assert response.status_code == 200, response.text


def writer_snapshot(client, branch_id):
    from server.generation_context import generation_snapshot
    from server.generation_models import GenerateRequest
    branch = client.get('/api/branches/' + branch_id).json()
    body = GenerateRequest(operation_id=uuid4().hex, expected_revision=branch['revision'], direction='lunar doorway')
    with client.app.state.database.connect() as connection:
        return generation_snapshot(connection, branch_id, body)[0]


def test_reviewed_alias_recall_is_opt_in_exact_and_excludable(client):
    from tests.test_history import append
    from tests.test_memory import small_profile
    story, _ = setup(client)
    branch_id = story['branch_id']
    run = started(client, branch_id)
    published = client.post('/api/summaries/' + run['id'] + '/versions', json=publication(client, run, branch_id))
    assert published.status_code == 201, published.text
    for index in range(40):
        append(client, branch_id, ('The market stalls were quiet. Vendors folded cloth beside the fountain. ' * 12) + str(index), index + 1)
    small_profile(client)
    before = writer_snapshot(client, branch_id)
    assert all(item['text'] != TEXT for item in decode(before['content'])['recalled_passages'])
    update_memory(client, story['story_id'], True)
    after = writer_snapshot(client, branch_id)
    exact = [item for item in decode(after['content'])['recalled_passages'] if item['text'] == TEXT]
    assert len(exact) == 1
    assert after['memory']['summary_aids'][0]['version_id'] == published.json()['id']
    assert after['memory']['summary_aids'][0]['summary'] == 'Elin makes an untested claim.'
    assert 'Elin makes an untested claim.' not in after['content']
    exclusion = publication(client, run, branch_id, expected_version_id=published.json()['id'], enabled=False)
    assert client.post('/api/summaries/' + run['id'] + '/versions', json=exclusion).status_code == 201
    excluded = writer_snapshot(client, branch_id)
    assert not excluded['memory'].get('summary_aids')
    assert all(item['text'] != TEXT for item in decode(excluded['content'])['recalled_passages'])


def test_publication_invalidates_prepared_writer_before_any_dispatch(client):
    from server.generation_models import GenerateRequest
    from server.generation_preparation import prepare_writer
    story, _ = setup(client)
    run = started(client, story['branch_id'])
    update_memory(client, story['story_id'], True)
    branch = client.get('/api/branches/' + story['branch_id']).json()
    body = GenerateRequest(operation_id=uuid4().hex, expected_revision=branch['revision'])
    with client.app.state.database.connect() as connection:
        prepared_writer = prepare_writer(connection, story['branch_id'], body)
    assert client.post('/api/summaries/' + run['id'] + '/versions', json=publication(client, run, story['branch_id'])).status_code == 201
    with client.app.state.database.connect(write=True) as connection:
        with pytest.raises(DomainError, match='while context was being assembled'):
            prepared_writer.validate(connection, body)
    assert client.get('/api/branches/' + story['branch_id'] + '/generations').json() == []


def test_summary_preview_defaults_disable_and_no_duplicate_paid_work(client):
    story, profile = setup(client)
    branch_id = story['branch_id']
    body, first = prepared(client, branch_id)
    assert first['jobs'][0]['profile_name'] == profile['name']
    alternate = make_profile(client, 'Summary override')
    saved = client.get('/api/stories/' + story['story_id']).json()
    response = client.put('/api/stories/' + story['story_id'], json={'title': saved['title'], 'premise': saved['premise'],
        'expected_revision': saved['revision'], 'settings': {**saved['settings'], 'step_profiles': {'memory-summary': alternate['profile_id']}}})
    assert response.status_code == 200, response.text
    assert client.post('/api/branches/' + branch_id + '/summaries', json=body).status_code == 409
    body, next_preview = prepared(client, branch_id)
    assert next_preview['jobs'][0]['profile_name'] == alternate['name']
    run = started(client, branch_id, body)
    duplicate = client.post('/api/branches/' + branch_id + '/summaries', json={**body, 'operation_id': uuid4().hex})
    assert duplicate.status_code == 201 and duplicate.json() == {'id': run['id'], 'job_ids': []}
    assert len(client.app.state.summary_runner.provider.calls) == 1
    prompt = saved_prompt(client, 'memory-summary')
    response = client.put('/api/prompts/memory-summary/activation', json={'expected_revision': prompt['activation_revision'], 'enabled': False})
    assert response.status_code == 200, response.text
    preview_body = {key: value for key, value in body.items() if key not in {'operation_id', 'preview_hash'}}
    assert client.post('/api/branches/' + branch_id + '/summary-preview', json=preview_body).status_code == 409


def test_source_pages_bound_request_size_and_partial_cancel_is_preserved(client):
    from tests.test_history import append
    story, _ = setup(client)
    branch_id = story['branch_id']
    append(client, branch_id, 'A long but exact accepted passage. ' * 1000, 1)
    first = client.get('/api/branches/' + branch_id + '/summary-sources').json()
    assert len(first['items']) == 12 and first['next_offset'] == 12
    assert all(len(item['text']) <= 2400 for item in first['items'])
    too_many = {'expected_revision': first['revision'], 'source_ids': [item['id'] for item in first['items']]}
    assert client.post('/api/branches/' + branch_id + '/summary-preview', json=too_many).status_code == 422
    body = {'expected_revision': first['revision'], 'source_ids': [first['items'][0]['id']]}
    preview = client.post('/api/branches/' + branch_id + '/summary-preview', json=body).json()
    provider = client.app.state.summary_runner.provider
    provider.wait = True
    response = client.post('/api/branches/' + branch_id + '/summaries', json={**body, 'operation_id': uuid4().hex, 'preview_hash': preview['preview_hash']})
    assert response.status_code == 201, response.text
    run_id, job_id = response.json()['id'], response.json()['job_ids'][0]
    client.portal.call(asyncio.sleep, 0.03)
    assert client.post('/api/summary-jobs/' + job_id + '/stop').status_code == 200
    client.portal.call(settle, client)
    stopped = detail(client, run_id, branch_id)
    assert stopped['jobs'][0]['status'] == 'cancelled' and stopped['jobs'][0]['output'] == '{"items":['
    assert stopped['current_version'] is None
    assert client.get('/api/summary-jobs/' + job_id + '/attempts').json()[0]['status'] == 'cancelled'
