from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.memory.budget import token_estimate
from server.memory.chunks import compile_chunks
from server.memory.evidence_groups import MAX_DEPTH, MAX_GROUPS
from server.memory.group_search import discover_groups
from server.memory.packet import assemble_memory
from server.memory.writer_recall import digest, freeze_sources
from server.memory.writer_recall_packet import pack_recall
from tests.test_archives import backup, restore
from tests.test_generations import finished
from tests.test_memory import fixture_context, profiles, small_profile
from tests.test_planned_events import plan
from tests.test_writer_recall import RecallProvider, change_memory, setup_story, start


def unit_plan_context(count=3):
    context = fixture_context()
    context['story']['settings']['memory']['writer_recall'] = True
    context['history'][12]['text'] = 'She gave it to a courier called Tess.'
    context['history'][20]['text'] = 'Tess dropped the package into a ravine. It never reached the recipient.'
    indices = [0, 12, 20] if count == 3 else list(range(count))
    commits = []
    for index in indices:
        node = context['history'][index]
        citation = compile_chunks(f"passage:{index + 1}:{digest(node['text'])}", 'Passage', node['text'])[0]
        change = {'id': 'return', 'target_id': 'origin:return' if commits else None,
                  'kind': 'plan', 'evidence': [{'source_id': citation.id, 'quote': node['text']}],
                  'subject': 'Observatory key', 'text': 'The promised return remains unresolved.'}
        commits.append({'origin_id': 'origin', 'node_id': node['id'], 'changes': [change], 'summary': ''})
    context['continuity'] = {'commits': commits, 'entries': [{
        'id': 'origin:return', 'kind': 'plan', 'subject': 'Observatory key',
        'text': 'The promised return remains unresolved.', 'status': 'active', 'node_id': 'n20',
        'evidence': commits[-1]['changes'][0]['evidence'], 'plan': plan('attempted')}]}
    return context, indices


def snapshot_for(context, limit=8192, aids=None, version=2):
    packet, memory = assemble_memory(context, 'Write.', profiles(limit), summary_aids=aids)
    return {'content': encode(packet), 'memory': memory, 'coverage': memory['coverage'],
            'estimated_input_tokens': token_estimate('Write.', packet), 'prompt': {'template': 'Write.'},
            'writer_recall': freeze_sources(context, version=version, summary_aids=aids)}


def source_ids(snapshot, indices):
    return {source['id'] for source in snapshot['writer_recall']['sources'] if source['passage_number'] - 1 in indices}


def test_one_promise_hit_fetches_handoff_and_failed_delivery_as_originals():
    context, indices = unit_plan_context()
    snapshot = snapshot_for(context)
    result = pack_recall(snapshot, ['observatory key'])
    assert result['groups'][0]['complete'] is True
    assert set(result['groups'][0]['supplied_ids']) == source_ids(snapshot, indices)
    final = decode(result['final_input']['content'])
    assert all(context['history'][index]['text'] in result['final_input']['content'] for index in indices)
    assert final['plan_memory']['entries'][0]['plan']['status'] == 'attempted'
    assert 'not that every relevant event' in final['recall_groups']['rule']
    assert result['final_input']['estimated_input_tokens'] + snapshot['memory']['overhead_margin'] <= snapshot['memory']['input_allowance']


def test_read_limit_discloses_incomplete_known_group_to_writer_and_author():
    context, _ = unit_plan_context(16)
    result = pack_recall(snapshot_for(context, limit=8192), ['observatory key'])
    assert len(result['decisions']) <= 8 and len(result['groups']) <= MAX_GROUPS
    group = result['groups'][0]
    assert group['complete'] is False and group['missing_ids']
    note = decode(result['final_input']['content'])['recall_groups']['groups'][0]
    assert note['complete_known_group'] is False and note['supplied_passages'] < note['known_passages']


def test_exclusion_removes_group_member_before_search_and_prevents_complete_claim():
    context, _ = unit_plan_context()
    chunk = compile_chunks('message:n12', 'narrator passage', context['history'][12]['text'])[0]
    context['author_memory'] = {'entries': [{'kind': 'emphasis', 'stance': 'exclude',
                                           'sources': [{'id': chunk.id, 'node_id': 'n12'}]}]}
    snapshot = snapshot_for(context)
    assert chunk.id not in encode(snapshot['writer_recall'])
    result = pack_recall(snapshot, ['observatory key'])
    assert not result['groups'][0]['complete'] and result['groups'][0]['unavailable_evidence'] == 1
    assert context['history'][12]['text'] not in result['final_input']['content']


def test_group_graph_has_visited_depth_and_count_bounds():
    groups = [{'id': f'g{i}', 'kind': 'derived relationship', 'label': 'linked',
               'description': 'anchor' if i == 0 else 'other', 'member_ids': [f'c{i}', f'c{(i + 1) % 12}']}
              for i in range(12)]
    chosen = discover_groups(groups, ['anchor'], [])
    assert 1 < len(chosen) <= MAX_GROUPS and max(row['depth'] for row in chosen) <= MAX_DEPTH
    assert len({row['id'] for row in chosen}) == len(chosen)


def test_scene_description_expands_actual_originals_but_keeps_granular_sources():
    context = fixture_context()
    context['history'][10]['text'] = 'A chamber of reeds. ' * 170
    context['continuity']['commits'] = [{'node_id': 'n10', 'scene_id': 's1', 'changes': [],
                                       'summary': 'The unforgettable lunar doorway.'}]
    snapshot = snapshot_for(context)
    originals = source_ids(snapshot, [10])
    assert len(originals) >= 2
    result = pack_recall(snapshot, ['lunar doorway'])
    assert result['groups'][0]['kind'] == 'accepted scene summary'
    assert set(result['groups'][0]['member_ids']) == originals
    assert result['groups'][0]['supplied_ids']
    assert 'unforgettable lunar doorway' not in result['final_input']['content']
    assert any(row['text'].startswith('A chamber') for row in decode(result['final_input']['content'])['recalled_passages'])


def save_plan_history(client, story, nodes):
    sources = client.get(f"/api/branches/{story['branch_id']}/plan-sources").json()['items']
    target = None
    for index in range(3):
        current = client.get(f"/api/branches/{story['branch_id']}/plans").json()
        source = next(row for row in sources if row['node_id'] == nodes[index])
        change = {'id': 'delivery', 'action': 'replace' if target else 'add', 'target_id': target,
                  'kind': 'plan', 'subject': 'Copper parcel promise', 'text': 'The promised delivery remains unresolved.',
                  'reason': 'Fixture records exact earlier evidence.', 'plan': plan('attempted'),
                  'evidence': [{'source_id': source['id'], 'quote': source['text']}]}
        response = client.post(f"/api/branches/{story['branch_id']}/plans", json={
            'operation_id': uuid4().hex, 'expected_revision': current['revision'],
            'expected_version_id': current['version_id'], 'change': change})
        assert response.status_code == 200, response.text
        target = response.json()['entry_id']
    return target


def test_plan_journal_groups_round_trip_and_reject_tampering(client):
    story, nodes = setup_story(client)
    save_plan_history(client, story, nodes)
    larger = small_profile(client, 'Larger group writer', 8192)
    client.app.state.runner.provider = RecallProvider('{"queries":["copper parcel promise"]}')
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    result = finished(client, start(client, story, revision, profile_ids=[larger['profile_id']])['id'])
    receipt = result['candidates'][0]['usage']['writer_recall']
    assert receipt['groups'][0]['complete']
    assert len(receipt['groups'][0]['supplied_ids']) == 3
    file, archive = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[result['id']]}").json()['candidates'][0]
    assert restored['usage']['writer_recall'] == receipt
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    changed = deepcopy(archive)
    row = changed['data']['generations'][0]
    snapshot = decode(row['snapshot'])
    snapshot['writer_recall']['groups'][0]['member_ids'].pop()
    row['snapshot'] = encode(snapshot)
    with pytest.raises(DomainError):
        parse_archive(encode(changed))


def test_reviewed_alias_search_resolves_original_and_preserves_edition_on_restore(client):
    from tests.test_summary_context import setup_story as summary_story
    story, _, _, _, _ = summary_story(client)
    larger = small_profile(client, 'Larger', 8192)
    change_memory(client, story, writer_recall=True, summary_recall=True)
    client.app.state.runner.provider = RecallProvider('{"queries":["lunar doorway"]}')
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    result = finished(client, start(client, story, revision, profile_ids=[larger['profile_id']])['id'])
    receipt = result['candidates'][0]['usage']['writer_recall']
    assert receipt['status'] == 'completed' and receipt['groups'][0]['kind'] == 'reviewed summary'
    assert receipt['groups'][0]['complete']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})


def test_v1_requests_keep_the_original_packing_algorithm():
    context, _ = unit_plan_context()
    original = snapshot_for(context, version=1)
    result = pack_recall(original, ['observatory key'])
    assert 'groups' not in original['writer_recall'] and 'groups' not in result
    assert 'recall_groups' not in decode(result['final_input']['content'])


def test_saved_v1_request_still_generates_and_restores_with_its_old_receipt(client):
    from server.generation_context import generation_snapshot
    from server.generation_models import GenerateRequest
    from server.generations import record_generation
    from tests.test_memory_readiness import settings
    story, nodes = setup_story(client)
    settings(client, story, prompt_sections=False)
    database = client.app.state.database
    with database.connect() as connection:
        snapshot, selected_profiles = generation_snapshot(connection, story['branch_id'], GenerateRequest(
            operation_id=uuid4().hex, expected_revision=len(nodes)))
    snapshot['writer_recall'] = {key: value for key, value in snapshot['writer_recall'].items()
                                 if key in {'sources', 'sources_sha256', 'prompt', 'max_queries', 'max_reads'}} | {'version': 1}
    with database.connect(write=True) as connection:
        run = record_generation(connection, snapshot, selected_profiles)
    client.app.state.runner.provider = RecallProvider()

    async def complete():
        client.app.state.runner.start(run['candidate_ids'][0])
        await client.app.state.runner.tasks[run['candidate_ids'][0]]

    client.portal.call(complete)
    result = finished(client, run['id'])
    receipt = result['candidates'][0]['usage']['writer_recall']
    assert receipt['version'] == 1 and 'groups' not in receipt and 'archive_sha256' not in receipt
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()['candidates'][0]
    assert restored['usage']['writer_recall'] == receipt
