"""Historical neighboring-passage policy and replay compatibility; not current defaults."""
import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, one
from server.errors import DomainError
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.memory.budget import token_estimate
from server.memory.chunks import compile_chunks
from server.memory.neighbors import NEIGHBOR_REASON, with_following_context
from server.memory.packet import add_recall, assemble_memory, minimum_context
from server.memory.retrieval import Corpus, Hit
from server.memory.settings import MemorySettings
from server.memory.source_packet import assemble_sources
from server.memory.source_replay import replay_sources
from tests.memory_retired_neighbors import enable_retired_policy
from tests.test_archives import backup, restore
from tests.test_context_inspector import database_dump, preview
from tests.test_generations import DraftProvider, finished
from tests.test_history import append
from tests.test_memory import fixture_context, profiles, small_profile
from tests.test_source_memory import saved

CLAIM = 'The valet alleged that Sima had taken the garnet cufflink.'
CORRECTION = 'At the hearing, the valet retracted that allegation. Sima had taken nothing.'


@pytest.fixture(autouse=True)
def historical_neighbor_policy(monkeypatch):
    enable_retired_policy(monkeypatch)


def pair_context():
    context = fixture_context()
    context['history'][0]['text'] = CLAIM
    context['history'][1]['text'] = CORRECTION
    context['direction'] = 'Preserve both accounts of the garnet cufflink.'
    return context


def specialist_context(writer=None):
    context = writer or pair_context()
    return {'stage': 'scene-draft', 'director_direction': context['direction'],
            'sources': [{'id': f"message:{node['id']}", 'kind': 'accepted',
                         'title': f"{node['role']} contribution", 'text': node['text']}
                        for node in context['history']]}


def neighbor_rows(report):
    return [row for row in report.get('selected', report.get('selection', [])) if 'adjacent_to' in row]


@pytest.mark.parametrize('budget', [4096, 8192])
def test_writer_recalls_the_retraction_with_exact_inspectable_proximity_and_budget(budget):
    context = pair_context()
    preserved = deepcopy(context)
    packet, report = assemble_memory(context, 'Write.', profiles(budget, budget * 2))
    items = packet['recalled_passages']
    assert [item['text'] for item in items[:2]] == [CLAIM, CORRECTION]
    neighbor = neighbor_rows(report)
    assert len(neighbor) == 1 and neighbor[0]['reason'] == NEIGHBOR_REASON
    assert neighbor[0]['adjacent_to'] == items[0]['id']
    assert neighbor[0]['score'] == 0 and neighbor[0]['matched_terms'] == []
    assert len(items) <= 8 and context == preserved
    assert items[1]['sha256'] == hashlib.sha256(CORRECTION.encode()).hexdigest()
    assert token_estimate('Write.', packet) + report['overhead_margin'] <= budget - 512
    assert (packet, report) == assemble_memory(context, 'Write.', profiles(budget * 2, budget))


def test_one_result_limit_keeps_anchor_without_silently_exceeding_the_cap():
    context = pair_context()
    context['story']['settings']['memory']['recall_limit'] = 1
    packet, report = assemble_memory(context, 'Write.', profiles(4096))
    assert [item['text'] for item in packet['recalled_passages']] == [CLAIM]
    assert not neighbor_rows(report)


@pytest.mark.parametrize('barrier', ['ooc', 'excluded', 'historical-cutoff'])
def test_writer_does_not_jump_across_missing_or_ineligible_following_evidence(barrier):
    context = pair_context()
    if barrier == 'ooc':
        context['history'][1]['role'] = 'ooc'
    elif barrier == 'excluded':
        chunk = compile_chunks('message:n1', 'narrator passage', CORRECTION)[0]
        context['author_memory'] = {'entries': [{'kind': 'emphasis', 'stance': 'exclude',
                                    'sources': [{'id': chunk.id, 'node_id': 'n1'}]}]}
    else:
        context['history'] = context['history'][:1]
    packet, report = assemble_memory(context, 'Write.', profiles(4096))
    assert not neighbor_rows(report)
    assert all(item['text'] != CORRECTION for item in packet.get('recalled_passages', []))
    # An author note remains required guidance, but is never a recalled event.


def test_within_passage_continuation_cannot_skip_an_excluded_middle_chunk():
    chunks = compile_chunks('a', '', 'A long exact passage. ' * 400)
    following = compile_chunks('b', '', 'A later passage.')[0]
    hit = Hit(chunks[0], .9, ('passage',))
    order = [('a', sum(len(chunk.text) for chunk in chunks)), ('b', len(following.text))]
    all_hits = with_following_context([hit], Corpus([*chunks, following]), order)
    assert all_hits[1].chunk.id == chunks[1].id
    assert all_hits[1].anchor_id == hit.chunk.id
    blocked = with_following_context([hit], Corpus([chunks[0], *chunks[2:], following]), order)
    assert blocked == [hit]


@pytest.mark.parametrize('independent', [False, True])
def test_unfittable_anchor_cannot_admit_an_orphan_but_independent_matches_still_work(monkeypatch, independent):
    context = pair_context()
    context['history'][0]['text'] = 'Overlarge evidence. ' * 120
    context['history'][1]['text'] = 'Short correction.'
    anchor = compile_chunks('message:n0', '', context['history'][0]['text'])[0]
    child = compile_chunks('message:n1', '', context['history'][1]['text'])[0]
    hits = [Hit(anchor, 1, ('evidence',))]
    if independent:
        hits.append(Hit(child, .5, ('correction',)))
    candidates = with_following_context(hits, Corpus([anchor, child]),
                                        [('message:n0', len(anchor.text)), ('message:n1', len(child.text))])
    monkeypatch.setattr('server.memory.packet.recall_candidates', lambda *_args: candidates)
    packet, included = minimum_context(context)
    report = add_recall(context, packet, included, '', token_estimate('', packet) + 300, MemorySettings(mode='long'), {})
    assert len(report) == int(independent)
    assert not any('adjacent_to' in item for item in report)


def test_already_ranked_following_passage_is_not_duplicated():
    context = pair_context()
    context['direction'] += ' The valet retracted the allegation.'
    packet, report = assemble_memory(context, 'Write.', profiles(4096))
    ids = [item['id'] for item in report['selected']]
    assert len(ids) == len(set(ids))
    assert sum(item['text'] == CORRECTION for item in packet['recalled_passages']) == 1


def test_scene_and_privileged_review_evidence_has_one_neighbor_and_exact_replay():
    context = specialist_context()
    packet, report = assemble_sources(context, 'Review.', profiles(4096), {'mode': 'long'})
    assert [item['text'] for item in packet['sources'][:2]] == [CLAIM, CORRECTION]
    assert packet['sources'][1]['recall_relation'] == NEIGHBOR_REASON
    assert len(neighbor_rows(report)) == 1
    assert replay_sources(context, saved(context, packet, report)) == packet


@pytest.mark.parametrize('barrier', ['ooc', 'private-kind', 'excluded'])
def test_specialist_neighbor_stops_at_role_or_author_exclusion_boundaries(barrier):
    context = specialist_context()
    if barrier == 'ooc':
        context['sources'][1]['title'] = 'ooc contribution'
    elif barrier == 'private-kind':
        context['sources'][1]['kind'] = 'private background'
    else:
        chunk = compile_chunks('message:n1', 'narrator contribution', CORRECTION)[0]
        context['author_memory'] = {'entries': [{'kind': 'emphasis', 'stance': 'exclude',
                                    'sources': [{'id': chunk.id, 'node_id': 'n1'}]}]}
    _packet, report = assemble_sources(context, 'Review.', profiles(4096), {'mode': 'long'})
    assert not neighbor_rows(report)


@pytest.mark.parametrize('tamper', ['anchor', 'non-adjacent', 'reason', 'aid', 'old-algorithm'])
def test_restoration_rejects_false_neighbor_provenance(tamper):
    context = specialist_context()
    packet, report = assemble_sources(context, 'Review.', profiles(4096), {'mode': 'long'})
    item = neighbor_rows(report)[0]
    if tamper == 'anchor':
        item['adjacent_to'] = '99999@0:5:000000000000'
    elif tamper == 'non-adjacent':
        context['sources'].insert(1, {'id': 'gap', 'kind': 'accepted', 'title': 'ooc contribution', 'text': 'Barrier'})
        for row in report['selection']:
            if row['index'] >= 1:
                row['index'] += 1
    elif tamper == 'reason':
        item['reason'] = 'A verified correction of the preceding claim.'
    elif tamper == 'aid':
        item['reviewed_aid'] = {}
    else:
        report['algorithm'] = 'prospero-source-lexical-v1'
    with pytest.raises(DomainError):
        replay_sources(context, saved(context, packet, report))


def test_legacy_specialist_receipts_without_neighbors_still_replay(monkeypatch):
    monkeypatch.setattr('tests.memory_retired_neighbors.with_following_context', lambda hits, *_args: hits)
    context = specialist_context()
    packet, report = assemble_sources(context, 'Review.', profiles(4096), {'mode': 'long'})
    report['algorithm'] = 'prospero-source-lexical-v1'
    assert replay_sources(context, saved(context, packet, report)) == packet


def test_preview_historical_fork_and_repeated_archives_preserve_exact_neighbor_inputs(client):
    small_profile(client)
    story = client.post('/api/stories', json={'title': 'Witness accounts', 'settings': {'memory': {'mode': 'long'}}}).json()
    context = pair_context()
    ids = [append(client, story['branch_id'], node['text'], index) for index, node in enumerate(context['history'])]
    before = database_dump(client)
    report, body = preview(client, story, expected_revision=len(ids), direction=context['direction'])
    assert len(neighbor_rows(report['memory'])) == 1
    assert database_dump(client) == before
    response = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': len(ids), 'name': 'Before the retraction', 'node_id': ids[0]})
    assert response.status_code == 201, response.text
    cut = response.json()
    with client.app.state.database.connect() as connection:
        old, _ = generation_snapshot(connection, cut['branch_id'], GenerateRequest(operation_id=uuid4().hex, expected_revision=0))
    assert CORRECTION not in old['content']
    client.app.state.runner.provider = DraftProvider()
    run = client.post(f"/api/branches/{story['branch_id']}/generations", json={**body, 'operation_id': uuid4().hex}).json()
    original = finished(client, run['id'])['snapshot']
    for _ in range(2):
        archive, _receipt = backup(client, story)
        _restored, mapping = restore(client, archive)
        with client.app.state.database.connect() as connection:
            snapshot = decode(one(connection, 'SELECT snapshot FROM generations WHERE id=?', (mapping[run['id']],))['snapshot'])
        assert snapshot['content'] == original['content'] and snapshot['memory'] == original['memory']
        story = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
        run = {'id': mapping[run['id']]}
