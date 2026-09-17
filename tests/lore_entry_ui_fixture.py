"""Disposable lore-entry authoring review; no model profiles or generated prose."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from tests.test_card_markdown import card
from tests.test_library_imports import publish_import, stage


def main():
    root = Path(__file__).resolve().parents[1] / 'test-results' / f'lore-entry-ui-{uuid4().hex}'
    root.mkdir()
    database = root / 'fixture.sqlite3'
    with TestClient(create_app(database), headers={'x-roleplay-client': 'workspace'}) as client:
        preview = stage(client, json.dumps(card('v3'), ensure_ascii=False).encode('utf-8'))
        published = publish_import(client, preview).json()['versions']
        book = next(item for item in published if item['kind'] == 'lorebook')
        story = client.post('/api/stories', json={'title': 'Harbor manuscript · lore QA',
            'opening_text': 'A lantern burns on the quay.',
            'attachments': [{'asset_id': book['asset_id'], 'version_id': book['id']}]}).json()
    manifest = {'database': str(database), 'book': book, 'story': story, 'root': str(root), 'import_id': preview['id']}
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
