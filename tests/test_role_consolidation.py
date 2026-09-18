import json
from copy import deepcopy

import pytest

from server.agent_switches import agent_enabled, set_agent
from server.archives.migrations import upgrade
from server.database import encode, many, one
from server.profiles import resolve_profile
from server.prompts import (
    LEGACY_PROMPT_LABELS,
    initialize_prompts,
    original_prompt,
    prompt_snapshot,
)
from server.roles import LEGACY_KEYS, ROLE_LABELS
from server.workflow.context import job_snapshot
from server.workflow.models import ReviewStep
from tests.test_archives import backup, restore
from tests.test_profiles import make_profile


def test_eleven_roles_keep_all_legacy_versions_and_initialize_idempotently(client):
    prompts = client.get('/api/prompts').json()
    assert len(prompts) == 11 and {row['key'] for row in prompts} == set(ROLE_LABELS)
    assert set(LEGACY_KEYS) == set(LEGACY_PROMPT_LABELS)
    database = client.app.state.database
    with database.connect() as connection:
        versions = many(connection, 'SELECT * FROM prompt_versions ORDER BY id')
        heads = many(connection, 'SELECT * FROM prompt_heads ORDER BY key')
    initialize_prompts(database)
    with database.connect() as connection:
        assert many(connection, 'SELECT * FROM prompt_versions ORDER BY id') == versions
        assert many(connection, 'SELECT * FROM prompt_heads ORDER BY key') == heads


def test_task_profiles_switches_and_custom_prompt_are_preserved(client, story):
    shared = make_profile(client, 'Shared Scribe', primary=True)
    summary = make_profile(client, 'Summary specialist')
    database = client.app.state.database
    with database.connect(write=True) as connection:
        saved = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        saved['settings'] = encode({'step_profiles': {'scribe': shared['profile_id'], 'memory-summary': summary['profile_id']}})
        assert resolve_profile(connection, saved, 'memory-summary')['profile_id'] == summary['profile_id']
        assert resolve_profile(connection, saved, 'beat-assessment')['profile_id'] == shared['profile_id']
        set_agent(connection, 'memory-summary', False, 0)
        assert not agent_enabled(connection, 'memory-summary', saved)
        assert agent_enabled(connection, 'beat-assessment', saved)
        set_agent(connection, 'scribe', False, 1)
        assert not agent_enabled(connection, 'beat-assessment', saved)
        assert agent_enabled(connection, 'writer', saved)
        original = original_prompt(connection, 'memory-summary')
    updated = client.put('/api/prompts/memory-summary', json={
        'expected_version_id': original['id'], 'template': 'Preserve my summary instructions exactly.',
    })
    assert updated.status_code == 200, updated.text
    initialize_prompts(database)
    with database.connect() as connection:
        assert prompt_snapshot(connection, 'memory-summary')['template'] == 'Preserve my summary instructions exactly.'
        assert prompt_snapshot(connection, 'beat-assessment')['key'] == 'scribe'
    scribe = next(row for row in client.get('/api/prompts').json() if row['key'] == 'scribe')
    task = next(row for row in scribe['tasks'] if row['key'] == 'memory-summary')
    assert task['custom_prompt'] and task['prompt_id'] == updated.json()['id']


def test_explicit_legacy_builtin_story_pin_is_not_advanced(client, story):
    with client.app.state.database.connect() as connection:
        saved = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        original = original_prompt(connection, 'memory-summary')
        saved['settings'] = encode({'prompt_versions': {'memory-summary': original['id']}})
        assert prompt_snapshot(connection, 'memory-summary', saved) == original
        assert prompt_snapshot(connection, 'memory-summary')['key'] == 'scribe'


@pytest.mark.parametrize('key', ['writer', 'scribe', 'scene-options', 'memory-summary'])
def test_published_copy_of_builtin_is_an_explicit_choice_after_restart_and_restore(client, story, key):
    database = client.app.state.database
    with database.connect() as connection:
        old = original_prompt(connection, key)
    saved = client.put(f'/api/prompts/{key}', json={
        'expected_version_id': old['id'], 'template': old['template']}).json()
    initialize_prompts(database)
    with database.connect() as connection:
        assert original_prompt(connection, key)['id'] == saved['id']
        assert prompt_snapshot(connection, key)['id'] == saved['id']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    with database.connect() as connection:
        restored = one(connection, 'SELECT * FROM stories WHERE id=?', (mapping[story['story_id']],))
        assert prompt_snapshot(connection, key, restored)['id'] == mapping[saved['id']]


def test_task_discriminators_preserve_task_directions_and_scope(client, story):
    make_profile(client, 'Local fixture', primary=True)
    with client.app.state.database.connect() as connection:
        saved = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        for key, role, field, task in (
            ('scene-options', 'scene-plan', 'task', 'options'),
            ('memory-summary', 'scribe', 'task', 'summary'),
            ('authoring-critique', 'library-assist', 'action', 'critique'),
        ):
            context = {'sources': [], 'task': 'Keep this task-specific instruction.'}
            snapshot = job_snapshot(connection, saved, ReviewStep(key=key), context)[0]
            content = json.loads(snapshot['content'])
            assert snapshot['step'] == key and snapshot['role'] == role and snapshot['prompt']['key'] == role
            assert content[field] == task and content['sources'] == []
            if field == 'task':
                assert content['task_direction'] == context['task']
            assert context['task'] == 'Keep this task-specific instruction.'


def test_archive_32_preserves_retired_heads_and_imports(client, story):
    record, document = backup(client, story)
    assert document['version'] == 32
    assert set(document['prompt_heads']) == set(ROLE_LABELS) | set(LEGACY_PROMPT_LABELS)
    _, mapping = restore(client, record)
    assert client.get(f"/api/stories/{mapping[story['story_id']]}").status_code == 200


def test_archive_31_upgrade_is_additive_and_deterministic(client, story):
    _, exported = backup(client, story)
    document = deepcopy(exported)
    document['version'] = 31
    document['prompt_heads'] = {key: value for key, value in document['prompt_heads'].items() if key in LEGACY_PROMPT_LABELS}
    document['data']['prompt_versions'] = [row for row in document['data']['prompt_versions'] if row['key'] in LEGACY_PROMPT_LABELS]
    original = deepcopy(document)
    upgraded = upgrade(document)
    assert upgraded == upgrade(deepcopy(original))
    assert upgraded['version'] == 32
    original_versions = {row['id']: row for row in original['data']['prompt_versions']}
    assert all(row == original_versions[row['id']] for row in upgraded['data']['prompt_versions'] if row['id'] in original_versions)
    assert all(upgraded['prompt_heads'][key] == value for key, value in original['prompt_heads'].items())
    imported = client.post('/api/archives/imports', json={'content': json.dumps(original)})
    assert imported.status_code == 201, imported.text
