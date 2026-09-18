import json
from uuid import uuid4

import pytest

from server.database import Database, one
from server.models import StoryCreate
from server.prompt_sections import system_prompt
from server.prompts import DEFAULT_WRITER, LEGACY_WRITER, initialize_prompts, prompt_snapshot
from server.stories import Stories
from tests.test_generations import DraftProvider, finished, generate
from tests.test_profiles import make_profile
from tests.test_transcripts import export


@pytest.mark.parametrize('custom_head', [False, True])
def test_writer_default_upgrade_is_versioned_idempotent_and_preserves_explicit_choices(tmp_path, custom_head):
    database = Database(tmp_path / 'legacy.sqlite3')
    with database.connect(write=True) as connection:
        connection.execute('INSERT INTO prompt_versions VALUES (?,?,?,?,?)',
                           ('writer-default-v1', 'writer', 1, LEGACY_WRITER, '2026-01-01'))
        if custom_head:
            connection.execute('INSERT INTO prompt_versions VALUES (?,?,?,?,?)',
                               ('my-writer', 'writer', 2, 'My chosen writing instructions.', '2026-01-02'))
        connection.execute('INSERT INTO prompt_heads VALUES (?,?)',
                           ('writer', 'my-writer' if custom_head else 'writer-default-v1'))
    story = Stories(database).create(StoryCreate(title='Pinned legacy writer', settings={
        'experience': 'directed', 'prompt_versions': {'writer': 'writer-default-v1'}}))
    before = Stories(database).detail(story['story_id'])
    initialize_prompts(database)
    initialize_prompts(database)
    with database.connect() as connection:
        legacy = one(connection, "SELECT * FROM prompt_versions WHERE id='writer-default-v1'")
        latest = one(connection, "SELECT * FROM prompt_versions WHERE id='writer-default-v2'")
        assert legacy['template'] == LEGACY_WRITER and legacy['created_at'] == '2026-01-01'
        assert latest['template'] == DEFAULT_WRITER and latest['number'] == (3 if custom_head else 2)
        assert prompt_snapshot(connection, 'writer')['id'] == ('my-writer' if custom_head else 'writer-default-v070')
        stored = one(connection, 'SELECT * FROM stories WHERE id=?', (story['story_id'],))
        assert prompt_snapshot(connection, 'writer', stored) == legacy
        assert connection.execute("SELECT COUNT(*) FROM prompt_versions WHERE key='writer'").fetchone()[0] == latest['number'] + 2
    assert Stories(database).detail(story['story_id']) == before


@pytest.mark.parametrize('experience,agency', [('directed', 'shared'), ('scene', 'user'), ('roleplay', 'user')])
def test_writing_mode_and_note_are_frozen_for_the_writer_without_accepting_prose(client, experience, agency):
    story = client.post('/api/stories', json={'title': 'Mode context', 'settings': {
        'experience': experience, 'player_agency': agency, 'pov': 'third person', 'tense': 'past'}}).json()
    make_profile(client, 'Protocol fixture', primary=True)
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    result = client.post(f"/api/branches/{story['branch_id']}/messages", json={
        'operation_id': uuid4().hex, 'expected_revision': 0, 'role': 'ooc', 'text': 'Keep the door closed.'})
    assert result.status_code == 201
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    run = generate(client, story, revision=1)
    frozen = finished(client, run['id'])['snapshot']
    context = json.loads(frozen['content'])
    assert context['story']['settings']['experience'] == experience
    assert context['story']['settings']['player_agency'] == agency
    assert context['history'][0]['role'] == 'ooc'
    assert frozen['prompt']['id'] == 'writer-default-v070'
    assert provider.calls[0][1] == system_prompt(frozen)
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    updated = client.get(f"/api/stories/{story['story_id']}").json()
    updated['settings']['experience'] = 'roleplay' if experience != 'roleplay' else 'directed'
    response = client.put(f"/api/stories/{story['story_id']}", json={
        'title': updated['title'], 'premise': updated['premise'], 'settings': updated['settings'],
        'expected_revision': updated['revision']})
    assert response.status_code == 200
    assert client.get(f"/api/generations/{run['id']}").json()['snapshot'] == frozen


@pytest.mark.parametrize('experience,heading,note', [('directed', 'Story text', 'Author note'),
                                                   ('scene', 'Story text', 'Author note'),
                                                   ('roleplay', 'Narration', 'Out of character')])
def test_mode_aware_transcripts_keep_notes_optional_and_prepared_downloads_immutable(client, experience, heading, note):
    story = client.post('/api/stories', json={'title': 'Export labels', 'settings': {'experience': experience}}).json()
    for revision, role, text in [(0, 'narrator', 'Rain on the quay.'), (1, 'ooc', 'Use a quieter ending.')]:
        assert client.post(f"/api/branches/{story['branch_id']}/messages", json={
            'operation_id': uuid4().hex, 'expected_revision': revision, 'role': role, 'text': text}).status_code == 201
    plain = export(client, story['branch_id'], 2).json()
    detailed = export(client, story['branch_id'], 2, include_ooc=True).json()
    assert f'## {heading}' in plain['content'] and 'quieter' not in plain['content']
    assert detailed['omitted_ooc_count'] == 0 and f'## {note}' in detailed['content']
    assert plain['omitted_ooc_count'] == 1
    assert client.get(detailed['download_url']).text == detailed['content']
    assert [n['role'] for n in client.get(f"/api/branches/{story['branch_id']}").json()['messages']] == ['narrator', 'ooc']
