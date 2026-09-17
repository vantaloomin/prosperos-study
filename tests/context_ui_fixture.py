"""Isolated context-inspector data. No providers, credentials or model requests."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from tests.test_history import append
from tests.test_library import publish
from tests.test_mechanics import configure


def local_profile(client, name, limit, primary=False):
    result = client.post('/api/profiles', json={'name': name, 'make_primary': primary,
        'config': {'provider': 'local', 'model': 'fixture-not-a-live-model',
                   'base_url': 'http://127.0.0.1:9/v1', 'timeout_seconds': 10,
                   'context_tokens': limit, 'max_output_tokens': 1200}})
    assert result.status_code == 201
    return result.json()


def main():
    root = Path(__file__).resolve().parents[1] / 'test-results' / f'context-ui-{uuid4().hex}'
    root.mkdir()
    database = root / 'fixture.sqlite3'
    with TestClient(create_app(database), headers={'x-roleplay-client': 'workspace'}) as client:
        roomy = local_profile(client, 'Roomy local · fixture', 64000, True)
        small = local_profile(client, 'Small local · fixture', 1600)
        book = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Harbor customs',
            'content': {'text': '# Harbor customs\n\nThe last ferry leaves at dusk. 雨'}}).json()
        story = client.post('/api/stories', json={'title': 'The last ferry · context review',
            'premise': 'Inspect a quiet manuscript. These are synthetic local test profiles; no generation is needed.',
            'settings': {'experience': 'directed', 'pov': 'third', 'tense': 'past', 'player_agency': 'shared'},
            'attachments': [{'asset_id': book['asset_id'], 'version_id': book['id']}]}).json()
        for index in range(40):
            append(client, story['branch_id'], f'Passage {index + 1}. The lantern cast a warm pool of light across the quay. '
                   + 'The tide carried rain and the scent of the sea. ' * 12, index)
        publish(client, book)
        assessed = client.post('/api/stories', json={'title': 'Beat check · context review'}).json()
        configure(client, assessed, automatic_assessment=True, chance=100, cooldown=0)
        append(client, assessed['branch_id'], 'The exchange is finished. The room falls quiet.', 0)
        with client.app.state.database.connect() as connection:
            baseline = '\n'.join(connection.iterdump())
    (root / 'before.sql').write_text(baseline, encoding='utf-8')
    manifest = {'database': str(database), 'story': story, 'assessed': assessed,
                'roomy': roomy, 'small': small, 'book': book}
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'database': str(database), 'story': story, 'assessed': assessed}))


if __name__ == '__main__':
    main()
