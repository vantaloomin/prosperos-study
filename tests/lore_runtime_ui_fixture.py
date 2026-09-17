"""Fresh local inspection fixture; real saved lore and one pending beat, no model calls."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from tests.test_lore_entries import entry, make_book
from tests.test_mechanics import configure, prepare


def main():
    root = Path(__file__).resolve().parents[1] / 'test-results' / f'lore-runtime-ui-{uuid4().hex}'
    root.mkdir()
    database = root / 'fixture.sqlite3'
    with TestClient(create_app(database), headers={'x-roleplay-client': 'workspace'}) as client:
        book = make_book(client, [entry('tidal-law', placement='header'),
            {**entry('lantern-detail', kind='flavor', chance_enabled=True, chance=100, placement='tail'),
             'text': 'The harbor lanterns use blue glass. This is world color, not a new event.'},
            entry('unpublished-idea', enabled=False),
            {**entry('mountain-custom'), 'activation': 'keywords', 'keywords': ['mountain'], 'text': 'The upland bells ring at noon.'}])
        story = client.post('/api/stories', json={'title': 'Harbor writing · live lore QA',
            'premise': 'A quiet coastal manuscript. This is a disposable interface review.',
            'opening_text': 'A lantern burns on the quay.',
            'attachments': [{'asset_id': book['asset_id'], 'version_id': book['id']}]}).json()
        configure(client, story, narrative_push=False, encounter=False, handling=False)
        revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
        prepared = prepare(client, story['branch_id'], revision=revision, beat={'label': 'The harbor settles', 'family': 'none'})
    manifest = {'root': str(root), 'database': str(database), 'book': book, 'story': story, 'prepared': prepared}
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'root': str(root), 'database': str(database), 'story': story, 'prepared': prepared}))


if __name__ == '__main__':
    main()
