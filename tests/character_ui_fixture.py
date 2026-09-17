"""Disposable character authoring review. No model calls or user data."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from tests.test_character_content import character_body, opening_body


def main():
    directory = Path(__file__).resolve().parents[1] / 'test-results' / f'character-ui-{uuid4().hex}'
    directory.mkdir(parents=True)
    path = directory / 'fixture.sqlite3'
    with TestClient(create_app(path), headers={'x-roleplay-client': 'workspace'}) as client:
        character = client.post('/api/library', json=character_body()).json()
        story = client.post('/api/stories', json={**opening_body(character), 'title': 'Original harbor · character review'}).json()
    result = {'database': str(path), 'character': character, 'story': story}
    (directory / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
