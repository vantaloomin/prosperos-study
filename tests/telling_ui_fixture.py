"""Disposable saved alternatives for gesture review. No live provider requests."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from server.providers.events import ProviderEvent
from tests.assessment_ui_fixture import profile
from tests.test_generations import finished, generate
from tests.test_history import append


class TellingProvider:
    async def generate(self, config, _prompt, _content):
        name = config['name']
        count = 30 if 'Long' in name else 2
        paragraphs = [f'{name} · passage {index + 1}. The traveler pauses beneath the station clock. '
                      'Rain follows the platform edge, and the still-open door offers another way onward. '
                      'This passage is labeled test data for reading-position and alternative navigation checks.'
                      for index in range(count)]
        yield ProviderEvent(text='\n\n'.join(paragraphs))
        yield ProviderEvent(done=True)


def main():
    directory = Path(__file__).resolve().parents[1] / 'test-results' / f'telling-ui-{uuid4().hex}'
    directory.mkdir(parents=True)
    path = directory / 'fixture.sqlite3'
    with TestClient(create_app(path), headers={'x-roleplay-client': 'workspace'}) as client:
        profiles = [profile(client, name, index == 0) for index, name in enumerate(
            ['Fixture Long A', 'Fixture Short B', 'Fixture Long C'])]
        client.app.state.runner.provider = TellingProvider()
        story = client.post('/api/stories', json={'title': 'Another telling · gesture fixture',
            'premise': 'Disposable UI test data. Saved drafts are fixtures, not live model output.'}).json()
        append(client, story['branch_id'], 'I wait on the platform.', 0)
        run = finished(client, generate(client, story, profiles, revision=1)['id'])
    manifest = {'database': str(path), **story, 'generation_id': run['id'],
                'candidate_ids': [item['id'] for item in run['candidates']]}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
