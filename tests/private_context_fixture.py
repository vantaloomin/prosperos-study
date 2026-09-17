"""Populate real private workflow storage using explicitly synthetic test output."""
from pytest import MonkeyPatch

from server.database import decode, one
from tests.test_background import prepared, update
from tests.test_background_interpretations import PrivateProvider, choose_private, start_private
from tests.test_history import append


def seed_private_history(client, story_id, branch_id, profiles, rounds, seed, budget):
    story = {'story_id': story_id, 'branch_id': branch_id}
    branch = client.get(f'/api/branches/{branch_id}').json()
    characters = [item['asset_id'] for item in branch['attachments'] if item['kind'] == 'character']
    with MonkeyPatch.context() as patch:
        patch.setattr('server.background.service.secrets.token_hex', lambda _length: seed)
        initial = prepared(client, story, character_ids=characters, day=10, horizon=30,
                           origin='Synthetic benchmark origin')
    client.app.state.background_runner.provider = PrivateProvider()
    records = []
    for ordinal in range(rounds):
        run = start_private(client, story, profiles)
        job = run['jobs'][ordinal % len(profiles)]
        chosen = choose_private(client, job)
        assert chosen.status_code == 200, chosen.text
        version = update(client, story, drives_enabled=True, hooks_enabled=True, day=10 + ordinal)
        current = client.get(f'/api/branches/{branch_id}').json()
        node = append(client, branch_id, f'Synthetic private-history checkpoint {ordinal + 1}.', current['revision'])
        records.append({'run_id': run['id'], 'chosen_state': chosen.json()['id'],
                        'updated_state': version['id'], 'node_id': node,
                        'input_messages': sum(item['kind'] == 'accepted' for item in decode(run['jobs'][0]['snapshot']['content'])['sources']),
                        'input_utf8_bytes': len(run['jobs'][0]['snapshot']['content'].encode('utf-8'))})
        with client.app.state.database.connect() as connection:
            budget.check(connection)
    with client.app.state.database.connect() as connection:
        original = decode(one(connection, 'SELECT snapshot FROM background_states WHERE id=?', (initial['id'],))['snapshot'])
    return {'branch_id': branch_id, 'initial_state': initial['id'], 'seed': original['result']['seed'], 'rounds': records}
