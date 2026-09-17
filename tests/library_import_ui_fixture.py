"""Isolated import UI review with local source fixtures and no model profiles."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from tests.test_card_markdown import card


def main():
    root = Path(__file__).resolve().parents[1] / 'test-results' / f'library-import-ui-{uuid4().hex}'
    root.mkdir()
    database = root / 'fixture.sqlite3'
    with TestClient(create_app(database), headers={'x-roleplay-client': 'workspace'}) as client:
        book = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Harbor notes',
            'content': {'text': '# Harbor notes\n\nThe tide follows the moon.\n'}}).json()
        story = client.post('/api/stories', json={'title': 'Harbor manuscript · import QA',
            'opening_text': 'A lantern burns on the quay.',
            'attachments': [{'asset_id': book['asset_id'], 'version_id': book['id']}]}).json()
    value = card()
    value['data']['name'] = 'Iona'
    (root / 'Iona-v3.json').write_bytes(b'\xef\xbb\xbf' + json.dumps(value, ensure_ascii=False, indent=3).encode('utf-8'))
    (root / 'Harbor-notes.md').write_bytes(b'# Harbor notes\r\n\r\nA violet tide arrives at dusk.\n\n')
    (root / 'Invalid-card.json').write_text('{unfinished', encoding='utf-8')
    manifest = {'database': str(database), 'book': book, 'story': story, 'root': str(root)}
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
