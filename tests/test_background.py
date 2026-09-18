import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.background.engine import guidance
from server.background.models import Preparation
from server.background.service import Background
from server.background.storage import state_id
from server.database import decode, one
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.scenes.context import create_snapshot, stage_inputs
from server.scenes.models import SceneCreate
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished, generate
from tests.test_history import append
from tests.test_mechanics import configure
from tests.test_profiles import make_profile


def setup_story(client):
    character = client.post('/api/library', json={'kind': 'character', 'name': 'Tavi', 'content': {'text': 'A supporting archivist.'}}).json()
    story = client.post('/api/stories', json={'title': 'Private potential', 'attachments': [
        {'asset_id': character['asset_id'], 'version_id': character['id']}]}).json()
    return story, character


def prepared(client, story, character=None, **values):
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    body = {'operation_id': uuid4().hex, 'expected_revision': revision, 'hooks': 2,
            'character_ids': [character['asset_id']] if character else [], **values}
    response = client.post(f"/api/branches/{story['branch_id']}/background", json=body)
    assert response.status_code == 201, response.text
    assert client.post(f"/api/branches/{story['branch_id']}/background", json=body).json() == response.json()
    return response.json()


def revealed(client, receipt):
    return client.get(f"/api/background/{receipt['id']}/reveal").json()['snapshot']


def update(client, story, **values):
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    body = {'operation_id': uuid4().hex, 'expected_revision': revision,
            'drives_enabled': False, 'hooks_enabled': False, 'day': 50, **values}
    response = client.put(f"/api/branches/{story['branch_id']}/background", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def fork(client, story, node, replacement=None):
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    response = client.post(f"/api/branches/{story['branch_id']}/forks", json={'operation_id': uuid4().hex,
        'expected_revision': revision, 'node_id': node, 'name': 'Historical fork', 'replacement': replacement})
    assert response.status_code == 201, response.text
    return response.json()['branch_id']


def test_private_preparation_idempotence_no_story_progress_and_real_draws(client):
    story, character = setup_story(client)
    receipt = prepared(client, story, character, day=12, horizon=7, origin='Arrival at the station')
    snapshot = revealed(client, receipt)
    assert len(snapshot['result']['draws']) == 6
    assert all(13 <= item['day'] <= 19 for item in snapshot['result']['hooks'])
    assert snapshot['result']['drives'][0]['character']['version_id'] == character['id']
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []
    summary = client.get(f"/api/branches/{story['branch_id']}/background").json()
    assert summary['current'] == receipt['id'] and len(summary['history']) == 1
    assert not any(word in json.dumps(summary) for word in ('seed', 'instruction', 'draws', 'tables'))
    denied = client.post(f"/api/branches/{story['branch_id']}/background", json={
        'operation_id': uuid4().hex, 'expected_revision': 1, 'hooks': 1})
    assert denied.status_code == 409


def test_forks_and_historical_edits_pin_setup_at_message_boundaries(client):
    story, character = setup_story(client)
    early = append(client, story['branch_id'], 'Before preparation.', 0)
    receipt = prepared(client, story, character)
    later = append(client, story['branch_id'], 'After preparation.', 2)
    changed = update(client, story)
    earlier_fork = fork(client, story, early)
    later_fork = fork(client, story, later)
    edited = fork(client, story, later, 'A different second contribution.')
    with client.app.state.database.connect() as connection:
        assert state_id(connection, earlier_fork) is None
        assert state_id(connection, later_fork) == receipt['id']
        assert state_id(connection, edited) is None
        assert state_id(connection, story['branch_id']) == changed['id']
    assert revealed(client, receipt)['day'] == 0
    assert revealed(client, changed)['result'] == revealed(client, receipt)['result']


def test_reroll_retains_original_point_versions_and_records(client):
    story, character = setup_story(client)
    receipt = prepared(client, story, character)
    append(client, story['branch_id'], 'Only on the original future.', 1)
    configure(client, story, disabled_tables=['hooks', 'automaton-a', 'automaton-b'])
    rerolled = prepared(client, story, reroll_of=receipt['id'])
    snapshot = revealed(client, rerolled)
    original = revealed(client, receipt)
    assert snapshot['result']['seed'] != original['result']['seed']
    assert snapshot['recipe'] == original['recipe'] and snapshot['result']['tables'] == original['result']['tables']
    assert client.get(f"/api/branches/{rerolled['branch_id']}").json()['messages'] == []
    assert len(client.get(f"/api/branches/{story['branch_id']}").json()['messages']) == 1


def test_disabled_tables_and_no_event_never_get_replacement_draws(client, monkeypatch):
    story, character = setup_story(client)
    configure(client, story, disabled_tables=['hooks', 'automaton-a', 'automaton-b'])
    receipt = prepared(client, story, character)
    assert revealed(client, receipt)['result']['draws'] == []
    assert guidance(revealed(client, receipt))['hooks'] == []
    from server.background.engine import resolve_background
    from server.mechanics.tables import catalog
    with client.app.state.database.connect() as connection:
        tables = catalog(connection)
    for table in tables.values():
        for row in table['definition']['rows']:
            row.update(kind='no_event', child=None)
    recipe = {'characters': [], 'hooks': 2, 'horizon': 30, 'day': 0}
    result = resolve_background(recipe, tables, {}, 'no-event-check')
    assert len(result['draws']) == 2 and all(hook['day'] is None for hook in result['hooks'])


def test_writer_comparison_frozen_inputs_and_stale_acceptance_pin_background(client):
    story, character = setup_story(client)
    client.app.state.runner.provider = DraftProvider()
    primary = make_profile(client, 'Primary', primary=True)
    other = make_profile(client, 'Other')
    receipt = prepared(client, story, character)
    run = generate(client, story, [primary['profile_id'], other['profile_id']], revision=1)
    detail = finished(client, run['id'])
    assert detail['snapshot']['background_state_id'] == receipt['id']
    assert len(json.loads(detail['snapshot']['content'])['private_background']['drives']) == 1
    assert client.app.state.runner.provider.calls[0][1:] == client.app.state.runner.provider.calls[1][1:]
    update(client, story)
    candidate = detail['candidates'][0]['id']
    assert client.post(f'/api/candidates/{candidate}/accept', json={'operation_id': uuid4().hex}).status_code == 409
    accepted = client.post(f'/api/candidates/{candidate}/accept', json={'operation_id': uuid4().hex, 'as_new_branch': True}).json()
    with client.app.state.database.connect() as connection:
        assert state_id(connection, accepted['branch_id']) == state_id(connection, accepted['node_id'], node=True) == receipt['id']
        body = GenerateRequest(operation_id=uuid4().hex, expected_revision=2)
        snapshot, _ = generation_snapshot(connection, story['branch_id'], body)
        assert not json.loads(snapshot['content'])['private_background']['drives']


def test_background_archive_roundtrip_reexport_and_tamper_rejection(client):
    story, character = setup_story(client)
    receipt = prepared(client, story, character)
    append(client, story['branch_id'], 'An accepted contribution.', 1)
    update(client, story)
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    result, mapping = restore(client, file)
    restored = revealed(client, {'id': mapping[receipt['id']]})
    assert restored['result']['seed'] == revealed(client, receipt)['result']['seed']
    assert restored['recipe']['characters'][0]['version_id'] == mapping[character['id']]
    again, _ = backup(client, {'story_id': result['selection']['storyId'], 'branch_id': result['selection']['branchId']})
    restore(client, again)
    bad = deepcopy(document)
    row = bad['data']['background_states'][0]
    snapshot = decode(row['snapshot'])
    snapshot['result']['draws'][0]['result'] += 1
    row['snapshot'] = json.dumps(snapshot)
    response = client.post('/api/archives/imports', json={'content': json.dumps(bad)})
    assert response.status_code == 400, response.text


def test_failed_record_rolls_back_setup_revision_and_retry_receipt(client, story, monkeypatch):
    def fail(*_args):
        raise RuntimeError('Injected receipt failure')
    monkeypatch.setattr('server.background.service.remember', fail)
    service = Background(client.app.state.database)
    with pytest.raises(RuntimeError, match='Injected'):
        service.prepare(story['branch_id'], Preparation(operation_id=uuid4().hex, expected_revision=0, hooks=1))
    assert service.context(story['branch_id']) == {'current': None, 'revision': 0, 'history': []}


def test_planning_only_receives_private_guidance_in_allowed_stages(client):
    story, character = setup_story(client)
    receipt = prepared(client, story, character)
    with client.app.state.database.connect() as connection:
        snapshot = create_snapshot(connection, story['branch_id'], SceneCreate(operation_id=uuid4().hex, expected_revision=1, title='Listen', direction='Listen.'))
        run = {'id': 'unsaved-plan', 'snapshot': snapshot, 'state': {'selections': {}}}
        assert snapshot['background_state_id'] == receipt['id']
        assert 'private_background' in stage_inputs(connection, run, 'scene-options')
        assert all('private_background' not in source['text'] for source in snapshot['sources'])
        assert 'private_background' not in stage_inputs(connection, run, 'scene-draft')
        assert one(connection, 'SELECT COUNT(*) AS n FROM nodes')['n'] == 0
