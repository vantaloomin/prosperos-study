"""Disposable, labeled assessment reports; the served app keeps its real provider adapters."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.main import create_app
from tests.test_assessments import AssessmentProvider, settled, start
from tests.test_generations import DraftProvider, finished
from tests.test_history import append
from tests.test_mechanics import configure


def profile(client, name, primary=False):
    return client.post('/api/profiles', json={'name': name, 'make_primary': primary,
        'config': {'provider': 'local', 'model': 'fixture-not-a-live-model',
                   'base_url': 'http://127.0.0.1:9/v1', 'timeout_seconds': 10}}).json()['profile_id']


def create_story(client, label):
    story = client.post('/api/stories', json={'title': f'Assessment - {label} - UI fixture',
        'premise': 'Disposable test data. Saved assessment reports and drafts are fixtures, not live provider output. Connection attempts use a closed local test port.'}).json()
    configure(client, story, automatic_assessment=True, chance=100, cooldown=0)
    append(client, story['branch_id'], 'The exchange is finished. The room falls quiet.', 0)
    return story


def main():
    directory = Path(__file__).resolve().parents[1] / 'test-results' / f'assessment-ui-{uuid4().hex}'
    directory.mkdir(parents=True)
    path = directory / 'fixture.sqlite3'
    with TestClient(create_app(path), headers={'x-roleplay-client': 'workspace'}) as client:
        first, second = profile(client, 'Fixture - Primary', True), profile(client, 'Fixture - Second')
        client.app.state.assessment_runner.provider = AssessmentProvider()
        client.app.state.runner.provider = DraftProvider()
        comparison = create_story(client, 'Comparison')
        compared = settled(client, start(client, comparison, assessment_profile_ids=[first, second])['assessment_id'])
        completed = create_story(client, 'Completed')
        done = settled(client, start(client, completed)['assessment_id'])
        finished(client, done['generation_id'])
        fresh = create_story(client, 'New request')
    manifest = {'database': str(path), 'comparison': {**comparison, 'assessment_id': compared['id']},
                'completed': {**completed, 'assessment_id': done['id'], 'generation_id': done['generation_id']}, 'fresh': fresh}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
