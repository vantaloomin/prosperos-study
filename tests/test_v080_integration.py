"""Cross-feature acceptance against a genuine released manuscript, without live inference."""
import gzip
import hashlib
import json
from copy import deepcopy
from uuid import uuid4

from fastapi.testclient import TestClient

from server.database import decode
from server.main import create_app
from server.prompt_sections import system_prompt
from server.text_edits.selection import whole_text
from tests.test_archive_lineages import FIXTURE
from tests.test_archives import backup, restore
from tests.test_branch_tools import branch, comparison, curate, search
from tests.test_profiles import make_profile
from tests.test_recipe_runs import RecipeProvider, create_run, detail, settled, start_step
from tests.test_side_edits import Provider, ask, reply
from tests.test_side_targets import pin
from tests.test_sidebar import settle, thread
from tests.test_text_edits import apply, target, undo
from tests.test_writing_bundles import exported, imported, proposed
from tests.test_writing_resources import create, pins

HEADERS = {'X-Roleplay-Client': 'workspace'}


def prose(preview):
    return [passage['text'] for chapter in preview['chapters']
            for scene in chapter['scenes'] for passage in scene['passages']]


def publish(client, resource, content):
    response = client.post(f"/api/writing-resources/{resource['asset_id']}/versions", json={
        'operation_id': uuid4().hex, 'expected_version_id': resource['id'], 'kind': resource['kind'],
        'name': resource['name'], 'content': content})
    assert response.status_code == 201, response.text
    return response.json()


def portable_recipe(path):
    with TestClient(create_app(path), headers=HEADERS) as client:
        model = make_profile(client, 'Portable writing partner')
        style = create(client, name='Restrained dialogue', content={'prose': 'Concrete, spare clauses.',
            'dialogue': 'Let the pause carry uncertainty.',
            'examples': [{'label': 'Author sample', 'text': '  She set the cup down.\nNo one answered.\n'}]})
        recipe = create(client, 'recipe', name='A considered revision', content={
            'style': style['id'], 'instructions': 'Preserve {{focus}}.', 'randomness': {'enabled': False},
            'variables': [{'name': 'focus', 'label': 'Focus', 'required': True}],
            'steps': [{'task': 'writer', 'profile_id': model['profile_id']},
                      {'task': 'review', 'lenses': ['dialogue', 'continuity']}, {'task': 'revision'}]})
        return exported(client, recipe, samples=True)


def released_story(client):
    raw = gzip.decompress(FIXTURE.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == '7c8c54e66ae1844524fba04e06539661a09a849f7da4d0915db803b6821be5d0'
    document = json.loads(raw)
    stage = client.post('/api/archives/imports', json={'content': raw.decode()})
    assert stage.status_code == 201, stage.text
    _, mapping = restore(client, stage.json())
    manuscript = document['data']['manuscripts'][0]
    source = decode(manuscript['document'])['chapters'][0]['scenes'][0]
    story = {'story_id': mapping[manuscript['story_id']], 'branch_id': mapping[source['branch_id']]}
    old_run = document['data']['generations'][0]
    restored = client.get('/api/generations/' + mapping[old_run['id']]).json()
    old_snapshot = decode(old_run['snapshot'])
    assert restored['snapshot']['content'] == old_snapshot['content']
    assert system_prompt(restored['snapshot']) == system_prompt(old_snapshot)
    return story


def run_recipe(client, story, recipe, style, other):
    source_branch = branch(client, story['branch_id'])
    source = target(client, {'kind': 'passage', **story, 'node_id': source_branch['messages'][1]['id']})
    body = {'target': source['ref'], 'expected_version': source['version'],
            'expected_revision': source_branch['revision'], 'selection': whole_text(source['text']),
            'action': 'update', 'writing': {'recipe': recipe['id'], 'variables': {'focus': 'the uncertainty'}},
            'task_switches': {key: True for key in ('review-blind', 'review-informed', 'review-dialogue', 'review-continuity')}}
    identity = create_run(client, story, body)
    original = detail(client, identity)['snapshot']
    changed_style = publish(client, style, {**style['content'], 'prose': 'Use longer, flowing sentences.'})
    publish(client, recipe, {**recipe['content'], 'instructions': 'A different instruction: {{focus}}.'})
    pins(client, other, changed_style['id'])
    assert client.get(f"/api/stories/{story['story_id']}/writing-preferences").json()['style'] == style['id']
    assert client.get(f"/api/stories/{other['story_id']}/writing-preferences").json()['style'] == changed_style['id']
    for expected in ('ready', 'ready', 'complete'):
        start_step(client, identity)
        assert settled(client, identity)['progress']['status'] == expected
    result = detail(client, identity)
    assert result['snapshot'] == original
    assert result['snapshot']['guidance']['style']['id'] == style['id']
    assert result['snapshot']['guidance']['recipe']['id'] == recipe['id']
    assert target(client, source['ref']) == source
    receipt = apply(client, result['proposals'][0])
    revised = branch(client, receipt['result']['branch_id'])
    assert [item['text'] for item in revised['messages'][2:]] == [item['text'] for item in source_branch['messages'][2:]]
    assert branch(client, story['branch_id'])['messages'] == source_branch['messages']
    return identity, revised


def companion_revision(client, story, revised, style):
    identity = thread(client, {**story, 'branch_id': revised['id']})
    source = target(client, {'kind': 'passage', 'story_id': story['story_id'],
                            'branch_id': revised['id'], 'node_id': revised['messages'][1]['id']})
    selected = pin(client, identity, {'kind': 'text', 'branch_id': revised['id'],
        'expected_revision': revised['revision'], 'target': source['ref'],
        'expected_version': source['version'], 'selection': whole_text(source['text'])})
    ask(client, identity, selected, {'task': 'rewrite', 'action': 'update', 'authority': 'suggest',
                                    'writing': {'style': style['id'], 'recipe': 'none'}})
    settle(client)
    response = reply(client, identity)
    assert response['status'] == 'done', response['error']
    assert target(client, source['ref']) == source
    receipt = apply(client, response['edit']['proposals'][0])
    undone = undo(client, receipt)['receipt']
    assert undone['after_target']['text'] == source['text']
    assert branch(client, revised['id'])['messages'] == revised['messages']
    request = client.get(f"/api/side-replies/{response['id']}/requests/0").json()
    assert 'Let the pause carry uncertainty.' in request['content']
    return identity, response, request


def test_v080_portable_workflow_preserves_released_book_through_restart_and_restore(tmp_path):
    bundle = portable_recipe(tmp_path / 'author.sqlite3')
    database = tmp_path / 'reader.sqlite3'
    app = create_app(database)
    recipe_provider, side_provider = RecipeProvider(), Provider()
    app.state.recipe_runner.provider, app.state.side_runner.provider = recipe_provider, side_provider
    with TestClient(app, headers=HEADERS) as client:
        assert client.get('/api/writing-resources').json() == []
        assert not proposed(client, bundle)['can_import']
        local = make_profile(client, 'Local mapped model', primary=True)
        imported_bundle = imported(client, bundle, {'model-1': local['profile_id']})
        recipe = next(item for item in imported_bundle['resources'] if item['id'] == imported_bundle['root_version_id'])
        style = next(item for item in imported_bundle['resources'] if item['kind'] == 'style')
        story = released_story(client)
        other = client.post('/api/stories', json={'title': 'A second Story', 'settings': {'disabled_prompts': []}}).json()
        assert client.get(f"/api/stories/{story['story_id']}/writing-preferences").json()['style'] == 'none'
        pins(client, story, style['id'], recipe['id'])
        pins(client, other, style['id'])
        manuscript = f"/api/stories/{story['story_id']}/manuscript"
        original_book = client.get(manuscript).json()
        original_preview = client.get(manuscript + '/preview').json()
        download = client.post(manuscript + '/exports', json={'expected_revision': original_book['revision']}).json()
        original_docx = client.get(download['docx_url']).content
        run_id, revised = run_recipe(client, story, recipe, style, other)
        compared = comparison(client, story, story['branch_id'], revised['id'])
        assert compared['counts']['changed'] == 1
        curate(client, revised['id'], favorite=True)
        curate(client, story['branch_id'], archived=True)
        query = branch(client, story['branch_id'])['messages'][1]['text'][:40]
        assert not search(client, story, query, branch_ids=[story['branch_id']])['results']
        assert search(client, story, query, branch_ids=[story['branch_id']], include_archived=True)['results']
        identity, response, request = companion_revision(client, story, revised, style)
        assert client.get(manuscript).json() == original_book
        assert client.get(manuscript + '/preview').json() == original_preview
        assert client.get(download['docx_url']).content == original_docx
        run_before = detail(client, run_id)
        calls_before = (len(recipe_provider.calls), len(side_provider.calls))
        assert calls_before == (4, 1)
        saved = {'story': story, 'run_id': run_id, 'companion': identity, 'comparison': compared['id'],
                 'book_prose': prose(original_preview), 'recipe_calls': calls_before[0], 'companion_calls': calls_before[1]}
    restarted = create_app(database)
    restarted.state.recipe_runner.provider, restarted.state.side_runner.provider = recipe_provider, side_provider
    with TestClient(restarted, headers=HEADERS) as client:
        assert detail(client, run_id) == run_before
        assert reply(client, identity)['output'] == response['output']
        assert client.get(manuscript).json() == original_book
        archive, document = backup(client, include_sidebar=True)
        assert document['version'] == 51
        _, mapping = restore(client, archive)
        restored_run = detail(client, mapping[run_id])
        assert [(job['snapshot']['instructions'], job['snapshot']['content']) for job in restored_run['jobs']] == [
            (job['snapshot']['instructions'], job['snapshot']['content']) for job in run_before['jobs']]
        restored_reply = reply(client, mapping[identity])
        restored_request = client.get(f"/api/side-replies/{restored_reply['id']}/requests/0").json()
        assert restored_request['content'] == request['content'] and restored_reply['output'] == response['output']
        restored_preview = client.get(f"/api/stories/{mapping[story['story_id']]}/manuscript/preview").json()
        assert prose(restored_preview) == prose(original_preview)
        assert branch(client, mapping[story['branch_id']])['curation']['archived']
        assert branch(client, mapping[revised['id']])['curation']['favorite']
        assert client.get('/api/branch-comparisons/' + mapping[compared['id']]).status_code == 200
        assert (len(recipe_provider.calls), len(side_provider.calls)) == calls_before
        saved.update(restarts=1, current_archive_version=document['version'], restored_stories=len(document['data']['stories']),
                     additional_restart_or_restore_calls=0, original_docx_sha256=hashlib.sha256(original_docx).hexdigest())
        (tmp_path / 'acceptance-report.json').write_text(json.dumps(deepcopy(saved), indent=2), encoding='utf-8')
