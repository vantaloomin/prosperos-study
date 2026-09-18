import pytest

from server.database import one
from server.prompts import original_prompt
from server.scenes.prompts import stage_prompt


@pytest.mark.parametrize('key', ['scene-triage', 'scene-verify', 'scene-patch', 'scene-dialogue-patch'])
def test_old_scene_defaults_match_the_original_stage_contract(client, story, key):
    with client.app.state.database.connect() as connection:
        saved = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        prompt = stage_prompt(connection, saved, {'snapshot': {}}, key)
        assert prompt['id'] == f'{key}-default-v1'
        assert prompt['key'] == key


@pytest.mark.parametrize('key', ['scene-triage', 'scene-patch'])
def test_new_scene_uses_combined_defaults_but_old_scene_keeps_explicit_edits(client, story, key):
    database = client.app.state.database
    with database.connect() as connection:
        saved = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        assert stage_prompt(connection, saved, {'snapshot': {'workflow_version': 2}}, key)['id'] == f'{key}-default-v062'
        original = original_prompt(connection, key)
    custom = client.put(f'/api/prompts/{key}', json={
        'expected_version_id': original['id'], 'template': 'My deliberately chosen revision contract.'}).json()
    with database.connect() as connection:
        assert stage_prompt(connection, saved, {'snapshot': {}}, key)['id'] == custom['id']
