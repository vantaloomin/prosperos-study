"""Disposable UI fixture with labelled protocol outputs, never live-provider evidence."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from tests.test_authoring import AuthoringProvider, request, start
from tests.test_lore_entries import entry, make_book
from tests.test_profiles import make_profile


def main():
    root = Path(__file__).resolve().parents[1] / 'test-results' / f'authoring-ui-{uuid4().hex}'
    root.mkdir()
    database = root / 'fixture.sqlite3'
    with TestClient(create_app(database), headers={'x-roleplay-client': 'workspace'}) as client:
        first = make_profile(client, 'QA fixture writer', primary=True)
        second = make_profile(client, 'QA fixture alternative')
        book = make_book(client, [entry('harbor'), entry('hill', enabled=False)])
        character = client.post('/api/library', json={'kind': 'character', 'name': 'Mara · assistant QA', 'content': {
            'text': 'Mara keeps the harbor records.', 'voice': 'Quiet, with dry humor.', 'behavior_rules': 'Keeps promises.',
            'greetings': [{'id': 'morning', 'label': 'Morning', 'text': 'Mara opens the shutters.'}]}}).json()
        story = client.post('/api/stories', json={'title': 'Library assistant · disposable QA', 'opening_text': 'The harbor is quiet.',
            'attachments': [{'asset_id': book['asset_id'], 'version_id': book['id']}, {'asset_id': character['asset_id'], 'version_id': character['id']}]}).json()
        client.app.state.authoring_runner.provider = AuthoringProvider()
        body = request(book, text=book['content']['text'], profile_ids=[first['profile_id'], second['profile_id']])
        runs = [start(client, body), start(client, {**body, 'step': 'authoring-critique', 'profile_ids': []})]
        selected = book['content']['lore_definition']['entries'][0]
        runs.append(start(client, request(book, text=selected['text'], target_key='entry:harbor', target_label='Entry · harbor')))
        runs.append(start(client, request(character, kind='character', text=character['content']['voice'], target_key='voice', target_label='Voice & manner')))
    manifest = {'root': str(root), 'database': str(database), 'book': book, 'character': character, 'story': story,
        'profiles': [first['profile_id'], second['profile_id']], 'runs': [{'id': run['id'], 'target_key': run['snapshot']['target_key'], 'step': run['snapshot']['step']} for run in runs]}
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=True))


if __name__ == '__main__':
    main()
