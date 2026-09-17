"""Isolated Markdown authoring review; no credentials or provider requests."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app


def main():
    root = Path(__file__).resolve().parents[1] / 'test-results' / f'markdown-ui-{uuid4().hex}'
    root.mkdir()
    database = root / 'fixture.sqlite3'
    with TestClient(create_app(database), headers={'x-roleplay-client': 'workspace'}) as client:
        book = client.post('/api/library', json={'kind': 'lorebook', 'name': 'The harbor', 'content': {
            'text': '# The harbor\n\nThe tide returns each morning.\n', 'extension': {'preserve': True}}}).json()
        stories = [client.post('/api/stories', json={'title': title, 'opening_text': 'A lantern burns on the quay.',
            'attachments': [{'asset_id': book['asset_id'], 'version_id': book['id']}]}).json()
            for title in ('Harbor manuscript · Markdown QA', 'Another tide · pinned QA')]
        source = client.get(f"/api/library/{book['asset_id']}/markdown").json()
    manifest = {'database': str(database), 'book': book, 'stories': stories, 'source': source}
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
