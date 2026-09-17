import json
from uuid import uuid4

from server.archives.format import BACKGROUND_TABLES
from server.background.storage import state_id
from server.database import decode
from server.providers.events import ProviderEvent
from tests.archive_legacy import remove_interpretations
from tests.test_archives import backup, restore
from tests.test_assessments import settled, setup_assessment, start
from tests.test_background import prepared, revealed, setup_story, update
from tests.test_generations import finished
from tests.test_profiles import make_profile
from tests.test_sidebar import ask, settle, thread


class BackgroundReader:
    def __init__(self):
        self.calls = []

    async def generate(self, _profile, _prompt, content):
        context = json.loads(content)
        self.calls.append(context)
        if any(item['id'].startswith('background:') for item in context['sources']):
            yield ProviderEvent(text='Private setup is available as a read-only proposal.', done=True)
        else:
            ids = [item['id'] for item in context['source_index'] if item['id'].startswith('background:')][:2]
            yield ProviderEvent(text='READ_SOURCES: ' + json.dumps(ids), done=True)


def test_assessment_excludes_private_cues_but_writer_and_reroll_keep_them(client, story):
    setup_assessment(client, story)
    receipt = prepared(client, story)
    run = settled(client, start(client, story, expected_revision=2)['assessment_id'])
    generation = finished(client, run['generation_id'])
    assert 'private_background' not in decode(run['jobs'][0]['snapshot']['content'])['context']
    assert 'private_background' in decode(generation['snapshot']['content'])
    opportunity = client.get(f"/api/opportunities/{run['opportunity_id']}").json()
    assert opportunity['snapshot']['background_state_id'] == receipt['id']
    rolled = client.post(f"/api/branches/{story['branch_id']}/opportunities", json={
        'operation_id': uuid4().hex, 'expected_revision': 2,
        'reroll_of': run['opportunity_id'], 'beat': run['jobs'][0]['result']['beat']})
    assert rolled.status_code == 201, rolled.text
    with client.app.state.database.connect() as connection:
        assert state_id(connection, rolled.json()['branch_id']) == receipt['id']
    file, _ = backup(client, story)
    result, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[generation['id']]}").json()
    assert restored['snapshot']['content'] == generation['snapshot']['content']
    again, _ = backup(client, {'story_id': result['selection']['storyId'], 'branch_id': result['selection']['branchId']})
    restore(client, again)


def test_full_context_sidebar_can_inspect_setup_without_mutating_it(client):
    story, character = setup_story(client)
    receipt = prepared(client, story, character)
    before = revealed(client, receipt)
    make_profile(client, 'Side collaborator', primary=True)
    client.app.state.side_runner.provider = BackgroundReader()
    conversation = thread(client, story)
    ask(client, conversation, story, revision=1, disclosure='full-disclosure')
    settle(client)
    context = client.app.state.side_runner.provider.calls[-1]
    assert context['disclosure'] == 'full-disclosure'
    docs = [doc for doc in context['sources'] if doc['id'].startswith('background:')]
    assert docs and 'PRIVATE' in docs[0]['title']
    assert any(before['result']['seed'] in doc['text'] for doc in docs)
    assert revealed(client, receipt) == before
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []
    file, _ = backup(client, story, include_sidebar=True)
    restore(client, file)


def test_inherited_setup_history_survives_new_branch_updates(client):
    story, character = setup_story(client)
    receipt = prepared(client, story, character)
    rolled = prepared(client, story, reroll_of=receipt['id'])
    target = {**story, 'branch_id': rolled['branch_id']}
    changed = update(client, target)
    history = client.get(f"/api/branches/{target['branch_id']}/background").json()
    assert history['current'] == changed['id']
    assert {item['id'] for item in history['history']} == {receipt['id'], rolled['id'], changed['id']}


def test_version_nine_upgrades_without_fabricating_background(client, story):
    _, document = backup(client, story)
    remove_interpretations(document)
    document['version'] = 9
    document['data'].pop('library_imports', None)
    document['data'].pop('asset_import_origins', None)
    document['data'].pop('asset_sources', None)
    document.pop('library_drafts', None)
    for table in BACKGROUND_TABLES:
        assert document['data'].pop(table) == []
    staged = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert staged.status_code == 201, staged.text
    assert staged.json()['summary']['version'] == 19
    result, _ = restore(client, staged.json())
    context = client.get(f"/api/branches/{result['selection']['branchId']}/background").json()
    assert context['current'] is None and context['history'] == []


def test_cross_story_background_links_are_rejected_even_with_valid_foreign_keys(client, story):
    first = prepared(client, story)
    other, _ = setup_story(client)
    second = prepared(client, other)
    _, document = backup(client)
    binding = next(row for row in document['data']['branch_background'] if row['background_state_id'] == first['id'])
    binding['background_state_id'] = second['id']
    response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert response.status_code == 400 and 'crosses Stories' in response.text
