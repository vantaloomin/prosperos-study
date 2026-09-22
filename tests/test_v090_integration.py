from uuid import uuid4

from fastapi.testclient import TestClient

from server.database import decode
from server.main import create_app
from server.manuscript.models import ManuscriptDocument
from tests.test_archives import restore
from tests.test_automatic_backups import configure, scheduled
from tests.test_character_containers import charx_members, zipped
from tests.test_generations import DraftProvider, finished
from tests.test_history import append
from tests.test_inspiration import draw, import_pack
from tests.test_inspiration import stage as stage_pack
from tests.test_library_imports import publish_body
from tests.test_migration_batches import adopt_reviewed_resources, preview, publish, stage, upload
from tests.test_preset_migration import body as preset_body
from tests.test_preset_migration import source as preset_source
from tests.test_profiles import make_profile
from tests.test_transcript_migration import body as transcript_body
from tests.test_transcript_migration import st_source


def test_scheduled_recovery_retains_migration_deck_request_and_html_book(client, tmp_path):
    originals = [st_source(), zipped(charx_members()), preset_source()]
    batch = stage(client, [upload(name, raw) for name, raw in zip(('chat.jsonl', 'hero.charx', 'preset.json'), originals, strict=True)])
    builders = (transcript_body, publish_body, preset_body)
    outcomes = [publish(client, item, builder(preview(client, item))) for item, builder in zip(batch['items'], builders, strict=True)]
    adopt_reviewed_resources(client, outcomes)
    story = outcomes[0]['result']
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    report, pack_bytes = stage_pack(client, client.get('/api/inspiration/starters').json()[0]['document'])
    deck = import_pack(client, report)['versions'][0]
    receipt, _ = draw(client, deck, branch_id=branch['id'], expected_revision=branch['revision'])
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    make_profile(client, 'Local test writer', primary=True)
    response = client.post(f"/api/branches/{branch['id']}/generations", json={
        'operation_id': uuid4().hex, 'expected_revision': branch['revision'], 'direction': receipt['card']['text']})
    assert response.status_code == 201, response.text
    request = finished(client, response.json()['id'])
    manuscript = ManuscriptDocument(title='Recovered selected Book', author='Test Author').model_dump()
    manuscript['chapters'] = [{'id': 'chapter', 'title': 'The gate', 'scenes': [
        {'id': 'scene', 'title': 'The selected telling', 'branch_id': branch['id'], 'head_id': branch['head_id'],
         'from_node_id': branch['messages'][0]['id'], 'through_node_id': branch['messages'][-1]['id']}]}]
    book_url = f"/api/stories/{story['story_id']}/manuscript"
    assert client.put(book_url, json={'expected_revision': 0, 'document': manuscript}).status_code == 200
    publication = client.post(book_url + '/exports', json={'expected_revision': 1}).json()
    original_html = client.get(publication['html_url']).content
    assert b'SYSTEM ONLY' not in original_html and b'HIDDEN REASONING' not in original_html
    destination = tmp_path / 'chosen backup destination'
    destination.mkdir()
    configure(client, enabled=True, interval_minutes=15, destination=str(destination), keep_count=2)
    saved = scheduled(client)
    assert saved['status'] == 'ready'
    append(client, branch['id'], 'Later prose must not appear in recovery.', branch['revision'])
    revised = client.post(f"/api/inspiration/decks/{deck['deck_id']}/versions", json={
        'operation_id': uuid4().hex, 'expected_version_id': deck['id'], 'name': 'Later deck',
        'content': {'cards': [{**deck['content']['cards'][0], 'text': 'Later card must not rewrite history.'}]}})
    assert revised.status_code == 201
    review = client.post(f"/api/backups/{saved['id']}/review", json={}).json()
    archive = client.get(review['download_url']).text
    with TestClient(create_app(tmp_path / 'clean-workspace.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as fresh:
        staged = fresh.post('/api/archives/imports', json={'content': archive}).json()
        _, mapping = restore(fresh, staged)
        restored = fresh.get(f"/api/branches/{mapping[branch['id']]}").json()
        assert [node['text'] for node in restored['messages']] == [node['text'] for node in branch['messages']]
        assert not restored['mechanics']['enabled']
        recovered_request = fresh.get(f"/api/generations/{mapping[request['id']]}").json()
        assert decode(recovered_request['snapshot']['content'])['direction'] == receipt['card']['text'].strip()
        assert recovered_request['candidates'][0]['output'] == request['candidates'][0]['output']
        recovered_draw = fresh.get(f"/api/inspiration/draws/{mapping[receipt['id']]}").json()
        assert recovered_draw['card'] == receipt['card'] and recovered_draw['selection'] == receipt['selection']
        assert recovered_draw['version_id'] == mapping[deck['id']]
        assert fresh.get(f"/api/inspiration/packs/{mapping[report['id']]}/original").content == pack_bytes
        for root, item, raw in zip(('/api/migration/transcripts', '/api/library-imports', '/api/migration/presets'), batch['items'], originals, strict=True):
            assert fresh.get(f"{root}/{mapping[item['import_id']]}/original").content == raw
        recipe_id = outcomes[2]['result']['resource']['id']
        assert fresh.get(f"/api/stories/{mapping[story['story_id']]}/writing-preferences").json()['recipe'] == mapping[recipe_id]
        assert len(fresh.get(f"/api/stories/{mapping[story['story_id']]}").json()['attachments']) == 2
        recovered_book = fresh.post(f"/api/stories/{mapping[story['story_id']]}/manuscript/exports", json={'expected_revision': 1}).json()
        assert fresh.get(recovered_book['html_url']).content == original_html
        assert fresh.get('/api/backups/settings').json()['enabled'] is False
        assert fresh.get('/api/backups').json() == fresh.get('/api/migration/batches').json() == []
    assert len(provider.calls) == 1
    assert len(client.get(f"/api/branches/{branch['id']}").json()['messages']) == len(branch['messages']) + 1
