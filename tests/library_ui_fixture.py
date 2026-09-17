"""Small disposable Library fixture; no model profiles, provider calls or user data."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from tests.test_adoption_plans import character, repin
from tests.test_history import append
from tests.test_library import with_book


def fixture(client):
    world = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Harbor customs',
        'content': {'text': 'The harbor closes at dusk. Visitors wait by the north gate.',
                    'activation': {'keywords': ['harbor'], 'scope': 'world'}}, 'note': 'The original harbor rules.'}).json()
    maps = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Tide maps',
        'content': {'text': 'The southern causeway is exposed at low tide.'}}).json()
    people = [character(client, world, name) for name in ['Iona', 'Mara']]
    story = client.post('/api/stories', json={'title': 'At the old harbor',
        'premise': 'Disposable Library review fixture. No live model output.', 'attachments': [
            {'asset_id': item['asset_id'], 'version_id': item['id']} for item in [*people, maps]]}).json()
    node = append(client, story['branch_id'], 'Rain gathers beside the north gate.', 0)
    archived = with_book(client, people[0], 'Earlier crossing')
    detail = client.get(f"/api/stories/{archived['story_id']}").json()
    response = client.put(f"/api/stories/{archived['story_id']}", json={
        'title': detail['title'], 'premise': detail['premise'], 'settings': detail['settings'],
        'expected_revision': detail['revision'], 'archived': True})
    assert response.status_code == 200
    journal = with_book(client, world, 'Harbor journal')
    updated = client.post(f"/api/library/{world['asset_id']}/versions", json={'expected_version_id': world['id'],
        'name': world['name'], 'content': {'text': 'During the dry season, the harbor remains open after dusk. Visitors use the east gate.',
            'activation': {'keywords': ['harbor', 'dry season'], 'scope': 'world'}}, 'note': 'Dry-season hours and a new entrance.'}).json()
    changed_people = [repin(client, person, updated) for person in people]
    future = with_book(client, updated, 'New tide')
    return {'story': story, 'archived': archived, 'journal': journal, 'future': future,
            'historical_node': node, 'world': world, 'updated_world': updated, 'maps': maps,
            'people': people, 'updated_people': changed_people}


def main():
    directory = Path(__file__).resolve().parents[1] / 'test-results' / f'library-ui-{uuid4().hex}'
    directory.mkdir(parents=True)
    path = directory / 'fixture.sqlite3'
    with TestClient(create_app(path), headers={'x-roleplay-client': 'workspace'}) as client:
        result = fixture(client)
    result['database'] = str(path)
    (directory / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'database': str(path), 'story': result['story']}, indent=2))


if __name__ == '__main__':
    main()
