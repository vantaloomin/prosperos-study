"""Disposable supporting-character Story for real background preparation UI checks."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from tests.test_background import setup_story
from tests.test_history import append


def main():
    directory = Path(__file__).resolve().parents[1] / 'test-results' / f'background-ui-{uuid4().hex}'
    directory.mkdir(parents=True)
    path = directory / 'fixture.sqlite3'
    with TestClient(create_app(path), headers={'x-roleplay-client': 'workspace'}) as client:
        story, character = setup_story(client)
        node = append(client, story['branch_id'], 'The station is quiet. Tavi sets a closed ledger on the counter.', 0)
    manifest = {'database': str(path), **story, 'character_id': character['asset_id'], 'original_node_id': node,
                'purpose': 'Disposable UI fixture. No provider calls or pre-generated secrets.'}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
