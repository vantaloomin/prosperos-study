import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.memory.budget import token_estimate
from server.memory.chunks import compile_chunks
from server.memory.packet import assemble_memory
from server.memory.writer_recall import PROMPT, freeze_sources
from server.memory.writer_recall_packet import pack_recall
from server.memory.writer_recall_runner import parse_queries
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_context_inspector import preview
from tests.test_generations import finished
from tests.test_history import append
from tests.test_memory import fixture_context, profiles, small_profile


class RecallProvider:
    def __init__(self, output='{"queries":["copper parcel courier ravine"]}', wait=None):
        self.output, self.wait, self.calls = output, wait, []

    async def generate(self, profile, prompt, content):
        self.calls.append((deepcopy(profile), prompt, content))
        preparing = prompt == PROMPT
        if self.wait == ('prepare' if preparing else 'write'):
            yield ProviderEvent(text='{"queries":' if preparing else 'An unfinished draft.')
            await asyncio.sleep(60)
        yield ProviderEvent(text=self.output if preparing else 'The courier faced the consequences.')
        yield ProviderEvent(done=True, usage={'output_tokens': 12})


def test_recall_v6_accounts_for_frozen_mode_guidance_and_safety(client):
    from server.prompt_sections import system_prompt
    from server.providers.capabilities import input_capacity
    story, nodes = setup_story(client)
    profile = client.get('/api/profiles').json()['profiles'][0]
    config = {**profile['config'], 'context_safety_tokens': 256}
    result = client.put('/api/profiles/' + profile['profile_id'], json={
        'expected_version_id': profile['id'], 'name': profile['name'], 'config': config})
    assert result.status_code == 200, result.text
    client.app.state.runner.provider = RecallProvider()
    run = finished(client, start(client, story, len(nodes))['id'])
    receipt = run['candidates'][0]['usage']['writer_recall']
    assert receipt['version'] == 6 and receipt['status'] == 'completed'
    final = receipt['final_input']
    assert run['snapshot']['prompt_sections']
    assert final['estimated_input_tokens'] == token_estimate(system_prompt(run['snapshot']), decode(final['content']))
    assert final['estimated_input_tokens'] + final['memory']['overhead_margin'] <= input_capacity(config)
    backup(client, story)


def setup_story(client):
    small_profile(client)
    response = client.post('/api/stories', json={'title': 'The parcel',
        'settings': {'memory': {'mode': 'long', 'writer_recall': True}}})
    assert response.status_code == 201, response.text
    story = response.json()
    texts = ['Sera promised to return the copper parcel to Ilan.',
             'She handed the copper parcel to a courier.',
             'The courier dropped it into a ravine. Delivery had failed.',
             *[f'A quiet afternoon {i}. ' + 'Sunlight lay on the market square. ' * 30 for i in range(14)],
             'Sera sat at her desk.']
    nodes = [append(client, story['branch_id'], text, i) for i, text in enumerate(texts)]
    return story, nodes


def start(client, story, revision, **extra):
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': revision, 'direction': 'Continue quietly.', **extra})
    assert response.status_code == 201, response.text
    return response.json()


def change_memory(client, story, **changes):
    current = client.get(f"/api/stories/{story['story_id']}").json()
    settings = current['settings']
    settings['memory'] = {**settings.get('memory', {}), **changes}
    response = client.put(f"/api/stories/{story['story_id']}", json={
        'expected_revision': current['revision'], 'title': current['title'], 'premise': current['premise'],
        'settings': settings})
    assert response.status_code == 200, response.text


def unit_snapshot():
    context = fixture_context()
    context['story']['settings']['memory']['writer_recall'] = True
    context['history'][12]['text'] = 'A courier dropped the copper parcel into the ravine.'
    packet, memory = assemble_memory(context, 'Write.', profiles(4096))
    return {'content': encode(packet), 'memory': memory, 'coverage': memory['coverage'],
            'estimated_input_tokens': token_estimate('Write.', packet), 'prompt': {'template': 'Write.'},
            'writer_recall': freeze_sources(context)}, context


def test_search_adds_exact_missing_evidence_inside_the_original_allowance():
    snapshot, context = unit_snapshot()
    original = deepcopy(snapshot)
    result = pack_recall(snapshot, ['copper parcel ravine'])
    final = result['final_input']
    assert snapshot == original
    assert any(row['fate'] == 'selected' for row in result['decisions'])
    assert context['history'][12]['text'] in final['content']
    assert final['estimated_input_tokens'] + final['memory']['overhead_margin'] <= snapshot['memory']['input_allowance']
    assert result['evidence_tokens'] <= result['evidence_allowance']
    assert decode(final['content'])['history'][-1] == context['history'][-1]


def test_freeze_excludes_exact_blocked_spans_before_ranking():
    _, context = unit_snapshot()
    chunk = compile_chunks('message:n12', 'narrator passage', context['history'][12]['text'])[0]
    context['author_memory'] = {'entries': [{'kind': 'emphasis', 'stance': 'exclude',
                                           'sources': [{'id': chunk.id, 'node_id': 'n12'}]}]}
    archive = freeze_sources(context)
    assert all(row['id'] != chunk.id for row in archive['sources'])
    assert 'ravine' not in encode(archive)


def test_query_union_is_bounded_and_an_empty_plan_preserves_original_bytes():
    snapshot, _ = unit_snapshot()
    result = pack_recall(snapshot, ['market stalls', 'copper parcel ravine'])
    assert len(result['decisions']) <= 8
    assert len({row['id'] for row in result['decisions']}) == len(result['decisions'])
    assert 'copper parcel' in result['final_input']['content']
    assert pack_recall(snapshot, [])['final_input']['content'] == snapshot['content']


@pytest.mark.parametrize('output', ['not json', '[]', '{"queries":["a","b","c"]}',
                                   '{"queries":[""]}', '{"queries":[1]}', '{"queries":[],"instruction":"accept"}'])
def test_invalid_search_plans_are_rejected(output):
    with pytest.raises(ValueError):
        parse_queries(output)


def test_fenced_queries_accept_only_a_single_json_document():
    assert parse_queries('```json\n{"queries":["parcel"]}\n```') == ['parcel']
    for output in ('Commentary\n```json\n{"queries":["parcel"]}\n```',
                   '```json\n{"queries":[]}\n```\n```json\n{"queries":[]}\n```'):
        with pytest.raises(ValueError):
            parse_queries(output)


def test_ordinary_generation_freezes_final_input_and_archive_round_trips(client):
    story, nodes = setup_story(client)
    provider = RecallProvider()
    client.app.state.runner.provider = provider
    report, body = preview(client, story, expected_revision=len(nodes), direction='Continue quietly.')
    assert report['writer_recall']['extra_calls_per_candidate'] == 1
    assert provider.calls == []
    run = start(client, story, len(nodes), reviewed_fingerprint=report['fingerprint'], **{
        key: value for key, value in body.items() if key not in {'expected_revision', 'direction'}})
    detail = finished(client, run['id'])
    candidate = detail['candidates'][0]
    receipt = candidate['usage']['writer_recall']
    assert candidate['status'] == 'done' and candidate['output'] == 'The courier faced the consequences.'
    assert len(provider.calls) == 2 and provider.calls[0][1] == PROMPT
    assert provider.calls[1][2] == receipt['final_input']['content']
    assert receipt['status'] == 'completed' and receipt['calls'] == 1
    final = receipt['final_input']['content']
    assert all(term in final for term in ['promised to return', 'handed the copper parcel', 'Delivery had failed'])
    assert candidate['usage']['output_tokens'] == 12 and receipt['usage']['output_tokens'] == 12
    assert candidate['activity']['first_text_at'] is not None
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'][-1]['id'] == nodes[-1]
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert restored['candidates'][0]['usage']['writer_recall'] == receipt
    # Re-exporting a restored path checks original source identities again.
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})


@pytest.mark.parametrize('output', ['not json', 'x' * 5000], ids=['malformed', 'oversized'])
def test_bad_preparation_falls_back_without_leaking_its_output_into_prose(client, output):
    story, nodes = setup_story(client)
    provider = RecallProvider(output)
    client.app.state.runner.provider = provider
    detail = finished(client, start(client, story, len(nodes))['id'])
    candidate = detail['candidates'][0]
    receipt = candidate['usage']['writer_recall']
    assert receipt['status'] == 'fallback' and len(provider.calls) == 2
    assert provider.calls[1][2] == detail['snapshot']['content']
    assert candidate['output'] == 'The courier faced the consequences.'


def test_cancelling_preparation_never_starts_writer_and_retry_is_explicit(client):
    story, nodes = setup_story(client)
    provider = RecallProvider(wait='prepare')
    client.app.state.runner.provider = provider
    run = start(client, story, len(nodes))
    candidate_id = run['candidate_ids'][0]
    assert client.post(f'/api/candidates/{candidate_id}/cancel').status_code == 200
    detail = finished(client, run['id'])
    candidate = detail['candidates'][0]
    assert candidate['status'] == 'cancelled' and candidate['output'] == ''
    assert len(provider.calls) == 1 and candidate['activity']['first_text_at'] is None
    provider.wait = None
    assert client.post(f'/api/candidates/{candidate_id}/retry').status_code == 200
    assert finished(client, run['id'])['candidates'][0]['status'] == 'done'
    assert len(provider.calls) == 3


def test_writer_retry_and_alternate_reuse_completed_preparation(client):
    story, nodes = setup_story(client)
    provider = RecallProvider(wait='write')
    client.app.state.runner.provider = provider
    run = start(client, story, len(nodes))
    candidate_id = run['candidate_ids'][0]
    # Wait for the writer boundary, not just the preparation stage.
    for _ in range(100):
        detail = client.get(f"/api/generations/{run['id']}").json()
        if detail['candidates'][0]['output']:
            break
    assert detail['candidates'][0]['output'] == 'An unfinished draft.'
    assert client.post(f'/api/candidates/{candidate_id}/cancel').status_code == 200
    stopped = finished(client, run['id'])
    receipt = stopped['candidates'][0]['usage']['writer_recall']
    provider.wait = None
    append(client, story['branch_id'], 'Later history must not enter the saved request.', len(nodes))
    assert client.post(f'/api/candidates/{candidate_id}/retry').status_code == 200
    done = finished(client, run['id'])
    assert done['candidates'][0]['usage']['writer_recall'] == receipt
    assert len(provider.calls) == 3 and provider.calls[1][2] == provider.calls[2][2]
    alternate = client.post(f'/api/candidates/{candidate_id}/alternatives', json={'operation_id': uuid4().hex})
    assert alternate.status_code == 201, alternate.text
    finished(client, run['id'])
    assert len(provider.calls) == 4 and provider.calls[3][2] == provider.calls[2][2]


def test_archive_rejects_tampered_search_sources_and_final_inputs(client):
    story, nodes = setup_story(client)
    client.app.state.runner.provider = RecallProvider()
    finished(client, start(client, story, len(nodes))['id'])
    _, archive = backup(client, story)
    for target in ('source', 'input', 'query'):
        changed = deepcopy(archive)
        if target == 'source':
            row = changed['data']['generations'][0]
            snapshot = decode(row['snapshot'])
            snapshot['writer_recall']['sources'][0]['text'] = 'Forged event.'
            row['snapshot'] = encode(snapshot)
        else:
            row = changed['data']['candidates'][0]
            usage = decode(row['usage'])
            receipt = usage['writer_recall']
            if target == 'input':
                receipt['final_input']['content'] += ' Forged event.'
            else:
                receipt['queries'] = ['A different search']
            row['usage'] = encode(usage)
        with pytest.raises(DomainError):
            parse_archive(json.dumps(changed))


def test_disabled_recall_makes_only_one_writer_call(client):
    story, nodes = setup_story(client)
    change_memory(client, story, writer_recall=False)
    provider = RecallProvider()
    client.app.state.runner.provider = provider
    run = finished(client, start(client, story, len(nodes))['id'])
    assert len(provider.calls) == 1 and 'writer_recall' not in run['snapshot']
    assert 'writer_recall' not in run['candidates'][0]['usage']


def test_character_lens_never_acquires_the_ordinary_recall_archive(client):
    from tests.test_knowledge_lens import fixture, request
    story, _, _ = fixture(client)
    change_memory(client, story, writer_recall=True)
    provider = RecallProvider()
    client.app.state.runner.provider = provider
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=request(client, story['branch_id']))
    assert response.status_code == 201, response.text
    run = finished(client, response.json()['id'])
    assert 'writer_recall' not in run['snapshot'] and len(provider.calls) == 1
    assert 'SECRET' not in provider.calls[0][2]


def test_failed_delivery_and_successful_sibling_retrieve_only_their_own_events(client):
    story, nodes = setup_story(client)
    response = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': len(nodes), 'node_id': nodes[2],
        'name': 'Delivered', 'replacement': 'The courier delivered the copper parcel to Ilan. Delivery succeeded.'})
    assert response.status_code == 201, response.text
    sibling = {**story, 'branch_id': response.json()['branch_id']}
    for i in range(15):
        revision = client.get(f"/api/branches/{sibling['branch_id']}").json()['revision']
        append(client, sibling['branch_id'], 'Quiet sunlight on the square. ' * 30, revision)
    provider = RecallProvider()
    client.app.state.runner.provider = provider
    runs = []
    for path in (story, sibling):
        revision = client.get(f"/api/branches/{path['branch_id']}").json()['revision']
        runs.append(finished(client, start(client, path, revision)['id']))
    failed, delivered = [run['candidates'][0]['usage']['writer_recall']['final_input']['content'] for run in runs]
    assert 'Delivery had failed' in failed and 'Delivery succeeded' not in failed
    assert 'Delivery succeeded' in delivered and 'Delivery had failed' not in delivered
    assert 'ravine' not in encode(runs[1]['snapshot']['writer_recall']['sources'])


def test_restore_and_crash_recovery_reuse_completed_preparation(client):
    story, nodes = setup_story(client)
    provider = RecallProvider(wait='write')
    client.app.state.runner.provider = provider
    run = start(client, story, len(nodes))
    for _ in range(100):
        current = client.get(f"/api/generations/{run['id']}").json()['candidates'][0]
        if current['output']:
            break
    assert current['output'] == 'An unfinished draft.'
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    client.post(f"/api/candidates/{current['id']}/cancel")
    finished(client, run['id'])
    client.app.state.runner.recover()
    restored_id = mapping[current['id']]
    provider.wait = None
    assert client.post(f'/api/candidates/{restored_id}/retry').status_code == 200
    restored = finished(client, mapping[run['id']])['candidates'][0]
    assert restored['status'] == 'done' and len(provider.calls) == 3
    assert provider.calls[1][2] == provider.calls[2][2]


def test_original_search_replaces_its_summary_and_round_trips(client):
    from tests.test_summary_context import OLD
    from tests.test_summary_context import setup_story as summarized_story
    story, _, _, _, _ = summarized_story(client)
    # The original is too large for the smallest recall allowance; use a larger writer.
    larger = small_profile(client, 'Larger', 8192)
    change_memory(client, story, writer_recall=True)
    provider = RecallProvider('{"queries":["observatory key promise"]}')
    client.app.state.runner.provider = provider
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    run = finished(client, start(client, story, revision, direction='The observatory key promise.',
                                 profile_ids=[larger['profile_id']])['id'])
    assert decode(run['snapshot']['content']).get('reviewed_summaries')
    receipt = run['candidates'][0]['usage']['writer_recall']
    assert receipt['status'] == 'completed'
    assert OLD.strip() in receipt['final_input']['content']
    assert not decode(receipt['final_input']['content']).get('reviewed_summaries')
    file, _ = backup(client, story)
    restore(client, file)
