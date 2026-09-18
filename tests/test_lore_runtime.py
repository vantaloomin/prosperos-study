import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.mechanics.state import node_state
from server.workflow.context import review_snapshot
from server.workflow.models import ReviewPreview
from tests.test_archives import backup, restore
from tests.test_assessments import settled, setup_assessment, start
from tests.test_generations import DraftProvider, finished, generate
from tests.test_history import append
from tests.test_library import with_book
from tests.test_lore_entries import entry, make_book
from tests.test_mechanics import accept_manual, configure, counts, prepare
from tests.test_profiles import make_profile
from tests.test_scene_continuity import acceptance_body, ready_continuity
from tests.test_scenes import PLAN, get_plan


def fixture_story(client):
    entries = [entry('law', placement='header'), entry('detail', placement='tail', kind='flavor', chance_enabled=True, chance=100),
               {**entry('hidden'), 'activation': 'keywords', 'keywords': ['SECRET_FUTURE'], 'text': 'EXCLUDED_ENTRY_PROSE'}]
    book = make_book(client, entries)
    story = with_book(client, book, 'Pinned lore runtime')
    return book, story


def inspect(client, story):
    response = client.get(f"/api/branches/{story['branch_id']}/lore")
    assert response.status_code == 200, response.text
    return response.json()


def receipt(client, prepared):
    return client.get(f"/api/opportunities/{prepared['id']}").json()['snapshot']


def test_live_reads_never_draw_and_writer_uses_only_selected_prose(client, monkeypatch):
    _, story = fixture_story(client)
    make_profile(client, 'Writer', primary=True)
    configure(client, story, narrative_push=False, encounter=False, handling=False)
    append(client, story['branch_id'], 'Quiet at the quay.', 0)
    before = counts(client)
    def forbidden(*_args):
        pytest.fail('A read tried to roll dice')
    monkeypatch.setattr('server.lore.engine.Draws.die', forbidden)
    first = inspect(client, story)
    assert inspect(client, story) == first and counts(client) == before
    assert [row['included'] for row in first['current']['entries']] == [False, True, False]
    with client.app.state.database.connect() as connection:
        snapshot, _ = generation_snapshot(connection, story['branch_id'], GenerateRequest(operation_id=uuid4().hex, expected_revision=1))
    context = decode(snapshot['content'])
    assert list(context)[0] == 'lore_header' and list(context)[-1] == 'lore_tail'
    assert context['lore_header'][0]['title'].endswith('Law') and not context['lore_tail']
    assert 'EXCLUDED_ENTRY_PROSE' not in snapshot['content'] and 'lore_definition' not in snapshot['content']
    assert snapshot['lore']['after']['clock'] == 0


def test_prepared_lore_reused_for_comparison_alternate_acceptance_and_archive(client):
    book, story = fixture_story(client)
    first = make_profile(client, 'One', primary=True)
    second = make_profile(client, 'Two')
    configure(client, story, narrative_push=False, encounter=False, handling=False)
    prepared = prepare(client, story['branch_id'], beat={'label': 'A boundary', 'family': 'none'})
    saved = receipt(client, prepared)
    assert saved['after']['beat'] == 0 and saved['lore']['after']['clock'] == 1
    assert len(saved['lore']['draws']) == 1 and not saved['draws']
    assert inspect(client, story)['current']['after']['clock'] == 0
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    run = generate(client, story, [first['profile_id'], second['profile_id']])
    detail = finished(client, run['id'])
    assert provider.calls[0][1:] == provider.calls[1][1:]
    assert detail['snapshot']['lore'] == saved['lore']
    candidate = detail['candidates'][0]['id']
    alternate = client.post(f'/api/candidates/{candidate}/alternatives', json={'operation_id': uuid4().hex})
    assert alternate.status_code == 201, alternate.text
    finished(client, run['id'])
    assert all(call[2] == detail['snapshot']['content'] for call in provider.calls)
    accepted = client.post(f'/api/candidates/{candidate}/accept', json={'operation_id': uuid4().hex})
    assert accepted.status_code == 200, accepted.text
    after = inspect(client, story)['current']
    assert after['after']['clock'] == 1 and not after['draws']
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, file)
    restored = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    assert inspect(client, restored)['current']['after']['entries'][0]['version_id'] == mapping[book['id']]
    restored_run = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert restored_run['snapshot']['content'] == detail['snapshot']['content']
    _, reexport = backup(client, restored)
    parse_archive(json.dumps(reexport))
    corrupt = deepcopy(document)
    row = corrupt['data']['mechanic_opportunities'][0]
    snapshot = decode(row['snapshot'])
    snapshot['lore']['draws'][0]['result'] = 101
    row['snapshot'] = encode(snapshot)
    with pytest.raises(DomainError, match='Lore beat'):
        parse_archive(json.dumps(corrupt))


@pytest.mark.parametrize('protected,waiting,completed,expected', [(True, False, True, 0), (False, True, True, 0), (False, False, False, 0), (False, False, True, 1)])
def test_only_eligible_boundaries_advance_lore_even_with_master_rng_off(client, protected, waiting, completed, expected):
    _, story = fixture_story(client)
    prepared = prepare(client, story['branch_id'], manual=True, beat={'label': 'Boundary', 'family': 'none',
        'completed': completed, 'protected': protected, 'waiting_for_player': waiting})
    saved = receipt(client, prepared)
    assert saved['lore']['after']['clock'] == expected
    assert not saved['lore']['draws'] and not saved['draws']
    accept_manual(client, story['branch_id'], prepared['id'])
    assert inspect(client, story)['current']['after']['clock'] == expected


def test_historical_edit_resets_to_parent_lore_and_reviews_exclude_future_and_blind_lore(client):
    _, story = fixture_story(client)
    make_profile(client, 'Reviewer', primary=True)
    configure(client, story)
    opening = append(client, story['branch_id'], 'An earlier quiet moment.', 0)
    prepared = prepare(client, story['branch_id'], revision=1)
    accepted = accept_manual(client, story['branch_id'], prepared['id'], revision=1)
    append(client, story['branch_id'], 'SECRET_FUTURE', 2)
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={'operation_id': uuid4().hex,
        'expected_revision': 3, 'node_id': accepted['node_id'], 'replacement': 'A different quiet moment.', 'name': 'Earlier edit'}).json()
    assert inspect(client, fork)['current']['after']['clock'] == 0
    with client.app.state.database.connect() as connection:
        body = ReviewPreview(expected_revision=3, through_node_id=opening, steps=[{'key': 'review-continuity'}, {'key': 'review-pacing'}])
        snapshot = review_snapshot(connection, story['branch_id'], body)
    informed, blind = [decode(job['content']) for job in snapshot['jobs']]
    assert any(source['kind'] == 'world reference' for source in informed['sources'])
    assert not any(source['kind'] == 'world reference' for source in blind['sources'])
    assert 'EXCLUDED_ENTRY_PROSE' not in encode(informed) and 'SECRET_FUTURE' not in encode(informed)
    assert inspect(client, story)['current']['after']['clock'] == 1


def test_scene_plan_lore_commits_only_on_acceptance_and_restores(client, monkeypatch):
    _, story = fixture_story(client)
    monkeypatch.setitem(PLAN['beats'][0], 'chance', {'completed': True, 'waiting_for_player': False, 'family': 'none'})
    run_id, _ = ready_continuity(client, story)
    run = get_plan(client, run_id)
    schedule = run['state']['gate_a']['mechanics']
    assert schedule['after']['lore']['clock'] == 1
    assert not any(item['result']['lore']['draws'] for item in schedule['entries'])
    assert inspect(client, story)['current']['after']['clock'] == 0
    draft = next(job for job in run['jobs'] if job['step'] == 'scene-draft')
    sources = decode(draft['snapshot']['content'])['sources']
    assert any(source['id'].startswith('planned:') for source in sources)
    response = client.post(f'/api/scenes/{run_id}/accept', json=acceptance_body(client, run_id))
    assert response.status_code == 200, response.text
    with client.app.state.database.connect() as connection:
        state = node_state(connection, response.json()['state']['accepted']['node_id'])
    assert state['lore']['clock'] == 1
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    _, document = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    parse_archive(json.dumps(document))


def test_assessed_lore_uses_the_same_saved_inputs_after_restore(client):
    _, story = fixture_story(client)
    setup_assessment(client, story)
    assessment = settled(client, start(client, story)['assessment_id'])
    generation = finished(client, assessment['generation_id'])
    lore = generation['snapshot']['lore']
    assert lore['advanced'] and len(lore['draws']) == 1
    repeated = finished(client, start(client, story)['id'])
    assert repeated['snapshot']['content'] == generation['snapshot']['content']
    assert repeated['snapshot']['lore'] == lore
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    _, document = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    parse_archive(json.dumps(document))
