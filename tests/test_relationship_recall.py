import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.memory.relationship_output import PROMPT, parse_annotations
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_generations import finished
from tests.test_writer_recall import RecallProvider, change_memory, setup_story, start


class RelationshipProvider:
    def __init__(self, wait=False, formatted=False):
        self.calls = []
        self.wait = wait
        self.formatted = formatted

    def background_capability(self, profile):
        return {'verified': False, 'reason': 'Controlled foreground provider.'}

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        assert prompt == PROMPT
        if self.wait:
            await asyncio.sleep(60)
        data = decode(content)
        target = next(source for source in data['sources'] if source['id'] == data['target_id'])
        sources = [source for source in data['sources'] if source['passage_number'] <= 3]
        if target not in sources:
            sources = [target]
        relation = {1: 'promise', 2: 'handoff', 3: 'outcome'}.get(target['passage_number'], 'related')
        output = {'items': [{'kind': 'relationship' if len(sources) > 1 else 'event', 'relation': relation,
                  'actor': 'Sera', 'description': 'The copper parcel promise and its outcome.',
                  'evidence': [{'source_id': source['id'], 'quote': source['text'][:80]} for source in sources]}]}
        if self.formatted:
            aliases = {row['id']: row['source_id'] for row in data['sources']}
            for item in output['items']:
                for citation in item['evidence']:
                    citation['source_id'] = aliases[citation['source_id']]
        text = '```json\n' + encode(output) + '\n```' if self.formatted else encode(output)
        yield ProviderEvent(text=text, done=True, usage={'output_tokens': 100})


def prepare(client, story):
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    response = client.post(f"/api/branches/{story['branch_id']}/relationships", json={
        'operation_id': uuid4().hex, 'expected_revision': revision})
    assert response.status_code == 201, response.text
    return response.json()


def wait_jobs(client, ids):
    async def wait():
        runner = client.app.state.relationship_runner
        await asyncio.gather(*(runner.tasks[identity] for identity in ids if identity in runner.tasks))
    client.portal.call(wait)
    return [client.get('/api/relationship-jobs/' + identity).json() for identity in ids]


def test_annotations_are_incremental_search_aids_and_survive_archives(client):
    story, nodes = setup_story(client)
    change_memory(client, story, relationship_recall=True)
    provider = RelationshipProvider(formatted=True)
    client.app.state.relationship_runner.provider = provider
    prepared = prepare(client, story)
    jobs = wait_jobs(client, prepared['job_ids'])
    assert len(jobs) == 4 and all(job['status'] == 'done' for job in jobs), jobs
    assert sorted(decode(call[2])['sources'][-1]['passage_number'] for call in provider.calls) == [1, 2, 3, 4]
    client.app.state.runner.provider = RecallProvider('```json\n{"queries":["copper parcel promise"]}\n```')
    run = finished(client, start(client, story, len(nodes))['id'])
    receipt = run['candidates'][0]['usage']['writer_recall']
    assert run['snapshot']['writer_recall']['annotation_aids']
    assert any(group['kind'] == 'derived relationship' for group in receipt['groups'])
    assert all(text in receipt['final_input']['content'] for text in ('promised to return', 'handed the copper parcel', 'Delivery had failed'))
    assert client.get(f"/api/branches/{story['branch_id']}/plans").json()['entries'] == []
    second = wait_jobs(client, prepare(client, story)['job_ids'])
    assert all(job['snapshot']['target_id'] not in {row['snapshot']['target_id'] for row in jobs} for job in second)
    file, archive = backup(client, story)
    _, mapping = restore(client, file)
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert restored['candidates'][0]['usage']['writer_recall'] == receipt
    restored_story = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    fresh = finished(client, start(client, restored_story, len(nodes))['id'])
    assert fresh['snapshot']['writer_recall']['annotation_aids']
    changed = deepcopy(archive)
    row = changed['data']['relationship_jobs'][0]
    result = decode(row['result'])
    result['items'][0]['evidence'][0]['quote'] = 'Invented evidence.'
    row['result'] = encode(result)
    with pytest.raises(DomainError):
        parse_archive(encode(changed))


def test_annotations_require_exact_unique_quotes_and_target_support():
    source = {'id': 'a', 'text': 'Sera promised. Sera promised.', 'start': 10, 'sha256': 'digest'}
    snapshot = {'content': encode({'target_id': 'a', 'sources': [source]})}
    item = {'kind': 'testimony', 'relation': 'related', 'actor': 'Sera', 'description': 'A claim, not established truth.',
            'evidence': [{'source_id': 'a', 'quote': 'Sera promised.'}]}
    with pytest.raises(DomainError, match='ambiguous'):
        parse_annotations(encode({'items': [item]}), snapshot)
    source['text'] = 'Sera said she promised.'
    snapshot['content'] = encode({'target_id': 'a', 'sources': [source]})
    item['evidence'][0]['quote'] = source['text']
    result = parse_annotations(encode({'items': [item]}), snapshot)
    assert result['items'][0]['kind'] == 'testimony' and result['items'][0]['evidence'][0]['start'] == 10
    item['evidence'][0]['source_id'] = 'sibling'
    with pytest.raises(DomainError):
        parse_annotations(encode({'items': [item]}), snapshot)


def test_short_source_ids_must_resolve_to_one_supplied_chunk():
    sources = [{'id': 'chunk-a', 'source_id': 'message:one', 'text': 'Sera promised.', 'start': 0, 'sha256': 'a'},
               {'id': 'chunk-b', 'source_id': 'message:one', 'text': 'Sera withdrew.', 'start': 20, 'sha256': 'b'}]
    snapshot = {'content': encode({'target_id': 'chunk-a', 'sources': sources})}
    item = {'kind': 'intention', 'relation': 'promise', 'actor': 'Sera', 'description': 'A promise.',
            'evidence': [{'source_id': 'message:one', 'quote': 'Sera promised.'}]}
    with pytest.raises(DomainError, match='multiple excerpts'):
        parse_annotations(encode({'items': [item]}), snapshot)
    item['evidence'][0]['source_id'] = 'chunk-a'
    assert parse_annotations(encode({'items': [item]}), snapshot)['items'][0]['evidence'][0]['source_id'] == 'chunk-a'


def test_stop_and_retry_preserve_attempts_without_accepting_anything(client):
    story, _ = setup_story(client)
    change_memory(client, story, relationship_recall=True)
    provider = RelationshipProvider(wait=True)
    client.app.state.relationship_runner.provider = provider
    prepared = prepare(client, story)
    for identity in prepared['job_ids']:
        assert client.post(f'/api/relationship-jobs/{identity}/cancel').status_code == 200
    jobs = wait_jobs(client, prepared['job_ids'])
    assert all(job['status'] == 'cancelled' and job['result'] is None for job in jobs)
    provider.wait = False
    identity = prepared['job_ids'][0]
    assert client.post(f'/api/relationship-jobs/{identity}/retry').status_code == 200
    assert wait_jobs(client, [identity])[0]['status'] == 'done'
    backup(client, story)


def test_changed_dependencies_and_sibling_outcomes_do_not_reuse_failed_delivery_links(client):
    from tests.test_memory_controls import entry, evidence, save
    story, nodes = setup_story(client)
    change_memory(client, story, relationship_recall=True)
    client.app.state.relationship_runner.provider = RelationshipProvider()
    wait_jobs(client, prepare(client, story)['job_ids'])
    sibling = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': len(nodes), 'node_id': nodes[2],
        'name': 'Delivered', 'replacement': 'The courier delivered the copper parcel to Ilan. Delivery succeeded.'})
    assert sibling.status_code == 201, sibling.text
    sibling = {**story, 'branch_id': sibling.json()['branch_id']}
    sibling_jobs = wait_jobs(client, prepare(client, sibling)['job_ids'])
    assert any('Delivery succeeded' in job['snapshot']['content'] for job in sibling_jobs)
    client.app.state.runner.provider = RecallProvider('{"queries":["copper parcel promise"]}')
    revision = client.get(f"/api/branches/{sibling['branch_id']}").json()['revision']
    run = finished(client, start(client, sibling, revision)['id'])
    archive = run['snapshot']['writer_recall']
    assert 'Delivery had failed' not in encode(archive)
    assert any('Delivery succeeded' in encode(aid) for aid in archive['annotation_aids'])
    source = next(row for row in evidence(client, story['branch_id']) if row['node_id'] == nodes[1])
    save(client, story['branch_id'], [entry([source], 'emphasis', 'exclude')])
    run = finished(client, start(client, story, len(nodes))['id'])
    archive = run['snapshot']['writer_recall']
    assert source['id'] not in encode(archive)
    assert not any(aid['relation'] == 'outcome' for aid in archive['annotation_aids'])
    backup(client, story)


def test_disabling_relationships_stops_active_preparation(client):
    story, _ = setup_story(client)
    change_memory(client, story, relationship_recall=True)
    provider = RelationshipProvider(wait=True)
    client.app.state.relationship_runner.provider = provider
    ids = prepare(client, story)['job_ids']
    change_memory(client, story, relationship_recall=False)
    jobs = wait_jobs(client, ids)
    assert all(job['status'] in {'cancelled', 'error'} and job['result'] is None for job in jobs)
    assert client.post(f'/api/relationship-jobs/{ids[0]}/retry').status_code == 409


def test_automatic_annotations_hold_lease_until_background_stop_is_acknowledged(client):
    from server.providers.scheduling import WRITING, BackgroundInterrupted
    from tests.test_history import append
    story, nodes = setup_story(client)
    change_memory(client, story, relationship_recall=True, relationship_automatic=True)
    profile = client.post('/api/profiles', json={'name': 'Native test', 'make_primary': True,
        'config': {'provider': 'local', 'local_protocol': 'lmstudio', 'model': 'fixture',
                   'max_output_tokens': 2048, 'context_tokens': 8192, 'timeout_seconds': 180}}).json()
    service = client.app.state.relationship_runner.provider

    class Background:
        def __init__(self):
            self.entered, self.stopped, self.release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        def capability(self, config, key):
            assert config == profile['config']
            return {'verified': True, 'reason': 'Controlled verified adapter.'}

        async def generate_interruptible(self, config, key, prompt, content, stop):
            self.entered.set()
            await stop.wait()
            self.stopped.set()
            await self.release.wait()
            raise BackgroundInterrupted()
            yield  # This deliberately models a streamed provider.

    background = Background()
    service.background = background
    append(client, story['branch_id'], 'Sera withdrew the promise to return the parcel.', len(nodes))

    async def interrupt():
        await asyncio.wait_for(background.entered.wait(), 5)
        writer_entered = asyncio.Event()
        async def writer():
            async with service.scheduler.reserve(profile['config'], WRITING):
                writer_entered.set()
        writer_task = asyncio.create_task(writer())
        await asyncio.wait_for(background.stopped.wait(), 2)
        assert not writer_entered.is_set() and len(service.scheduler.active) == 1
        background.release.set()
        await asyncio.wait_for(writer_task, 2)
        await asyncio.gather(*list(client.app.state.relationship_runner.tasks.values()))
        assert not service.scheduler.active

    client.portal.call(interrupt)
    with client.app.state.database.connect() as connection:
        jobs = connection.execute('SELECT status,mode FROM relationship_jobs').fetchall()
    assert len(jobs) == 1 and tuple(jobs[0]) == ('cancelled', 'automatic')


def test_recovery_does_not_resend_and_repeated_operations_do_not_replay_jobs(client, monkeypatch):
    story, nodes = setup_story(client)
    change_memory(client, story, relationship_recall=True)
    runner = client.app.state.relationship_runner
    runner.provider = RelationshipProvider()
    start_job = runner.start_job
    monkeypatch.setattr(runner, 'start_job', lambda identity: None)
    body = {'operation_id': uuid4().hex, 'expected_revision': len(nodes)}
    url = f"/api/branches/{story['branch_id']}/relationships"
    initial = client.post(url, json=body).json()
    with client.app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE relationship_jobs SET status='running',attempt=1,output='partial'")
    runner.recover()
    jobs = [client.get('/api/relationship-jobs/' + identity).json() for identity in initial['job_ids']]
    assert all(job['status'] == 'interrupted' and job['output'] == 'partial' for job in jobs)
    assert not runner.provider.calls
    monkeypatch.setattr(runner, 'start_job', start_job)
    assert client.post(url, json=body).json() == initial
    assert all(job['status'] == 'interrupted' for job in wait_jobs(client, initial['job_ids']))
    assert not runner.provider.calls
    backup(client, story)
    identity = initial['job_ids'][0]
    assert client.post(f'/api/relationship-jobs/{identity}/retry').status_code == 200
    job = wait_jobs(client, [identity])[0]
    assert job['status'] == 'done' and job['attempt'] == 2
    with client.app.state.database.connect() as connection:
        attempts = connection.execute('SELECT status,output FROM relationship_attempts WHERE job_id=? ORDER BY attempt', (identity,)).fetchall()
    assert [row['status'] for row in attempts] == ['interrupted', 'done'] and attempts[0]['output'] == 'partial'
    change_memory(client, story, relationship_recall=False)
    assert client.post(url, json=body).json() == initial
    wait_jobs(client, initial['job_ids'])
    assert client.get('/api/relationship-jobs/' + identity).json() == job
    assert len(runner.provider.calls) == 1
