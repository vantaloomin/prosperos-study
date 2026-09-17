"""Combined branch/context/workspace benchmark in a new disposable database only.

Run ``python -m tests.branch_context_fixture``. Workflow results are labeled
synthetic fixtures. No model service is contacted, and no measured DB is reused.
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.database import encode, many, one
from server.library import Library
from server.main import create_app
from server.models import AssetCreate, AssetPublish, Attachment, StoryCreate
from server.stories import Stories
from tests.branch_adversarial_fixture import build_adversarial, transition_metrics, validate_budget
from tests.branch_topology_fixture import TopologySize
from tests.context_workflow_fixture import (
    fixture_profile,
    frozen_input_bytes,
    pending_jobs,
    seed_workflow,
)
from tests.performance_fixture import add_pairs
from tests.topology_manifest import describe_fixture, text_fingerprint


@dataclass(frozen=True)
class ContextSize:
    lorebooks: int = 16
    characters: int = 4
    lore_characters: int = 12000
    continuity_entries: int = 60
    assessments: int = 6
    sidebar_turns: int = 2
    other_stories: int = 16
    other_responses: int = 500

    def validate(self):
        ceilings = (24, 8, 20000, 90, 12, 2, 24, 1000)
        if any(not 1 <= value <= ceiling for value, ceiling in zip(asdict(self).values(), ceilings)):
            raise ValueError('Context fixture exceeds its explicit resource budget; these are not product limits.')


def make_library(database, size):
    library = Library(database)
    books = []
    for index in range(size.lorebooks):
        fragment = f'Lore marker {index + 1:03d}: café, 東京, and 🌙 are part of this synthetic world. '
        text = (fragment * (size.lore_characters // len(fragment) + 1))[:size.lore_characters]
        books.append(library.create(AssetCreate(kind='lorebook', name=f'Benchmark lore {index + 1:03d}',
            content={'text': text}, note='Synthetic benchmark, historical version.')))
    characters = [library.create(AssetCreate(kind='character', name=f'Benchmark character {index + 1:03d}',
        content={'text': 'A synthetic supporting character. ' * 30,
                 'lorebook_versions': [books[index % len(books)]['id']]},
        note='Synthetic benchmark, historical version.')) for index in range(size.characters)]
    return books + characters


def future_versions(database, versions):
    result, replaced = [], {}
    for old in versions:
        content = {**old['content'], 'text': 'FUTURE STORY VERSION. ' + old['content']['text']}
        if 'lorebook_versions' in content:
            content['lorebook_versions'] = [replaced[item] for item in content['lorebook_versions']]
        new = Library(database).publish(old['asset_id'], AssetPublish(expected_version_id=old['id'],
            name=old['name'], content=content, note='Future Stories only; preserve the measured Story.'))
        result.append(new)
        replaced[old['id']] = new['id']
    return result


def attachments(versions):
    return [Attachment(asset_id=version['asset_id'], version_id=version['id']) for version in versions]


def add_workspace_stories(database, versions, size):
    result = []
    for index in range(size.other_stories):
        story = Stories(database).create(StoryCreate(title=f'Other benchmark Story {index + 1:03d}',
            premise='Unrelated synthetic history. Must never appear on the target Story path.',
            attachments=attachments(versions)))
        with database.connect(write=True) as connection:
            branch = one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],))
            add_pairs(connection, branch, 0, size.other_responses, f'UNRELATED STORY {index + 1:03d}')
            archived = index % 2 == 0
            connection.execute('UPDATE stories SET archived=? WHERE id=?', (archived, story['story_id']))
        result.append({**story, 'archived': archived, 'responses': size.other_responses})
    return result


def workspace_metrics(database, target):
    with database.connect() as connection:
        nodes = many(connection, 'SELECT role,text FROM nodes WHERE story_id<>? ORDER BY rowid', (target,))
        counts = {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for table in ('stories', 'branches', 'nodes', 'asset_versions', 'continuity_commits',
                                'candidates', 'mechanic_opportunities', 'scene_jobs', 'review_jobs', 'side_turns',
                                'background_states', 'background_runs', 'background_jobs', 'background_attempts',
                                'branch_background', 'node_background')}
        foreign_keys = connection.execute('PRAGMA foreign_key_check').fetchall()
        active = pending_jobs(connection)
        frozen = frozen_input_bytes(connection)
    assert not foreign_keys and not any(active.values()), (foreign_keys, active)
    return {'counts': counts, 'frozen_snapshots': frozen, 'pending_jobs': active, 'foreign_key_errors': 0,
            'unrelated_messages': len(nodes), 'unrelated_text_utf8_bytes': sum(len(row['text'].encode('utf-8')) for row in nodes),
            'unrelated_text_sha256': text_fingerprint(nodes)}


def build_context(client, topology=TopologySize(), size=ContextSize(), deep_width=1000):
    size.validate()
    validate_budget(topology, deep_width)
    database = client.app.state.database
    profiles = [fixture_profile(client, f'Benchmark writer {index + 1}') for index in range(2)]
    versions = make_library(database, size)
    story = Stories(database).create(StoryCreate(title='Heavy context benchmark · synthetic records',
        premise='Disposable benchmark. All saved model outputs are synthetic fixtures, not live provider results.',
        attachments=attachments(versions), settings={'primary_profile_id': profiles[0]}))
    workflow = seed_workflow(client, story, profiles, size)
    baseline = build_adversarial(database, topology, deep_width, story=story)
    latest = future_versions(database, versions)
    unrelated = add_workspace_stories(database, latest, size)
    selected = {key: {'id': value['id']} for key, value in baseline['paths'].items()}
    result = describe_fixture(database, story['story_id'], selected, 'heavy-context', baseline['sizes'])
    assert result['content_sha256'] == baseline['content_sha256']
    result.update({'context_size': asdict(size), 'workflow': workflow, 'other_stories': unrelated,
                   'historical_version_ids': [item['id'] for item in versions],
                   'future_version_ids': [item['id'] for item in latest],
                   'deep_parent_id': baseline['deep_parent_id'],
                   'workspace': workspace_metrics(database, story['story_id'])})
    result['transitions'] = transition_metrics(result['paths'])
    result['limitations'] = ['Synthetic workflow history created before the large topology; no live providers.',
        'Workflow snapshots contain the early short history and substantial lore, not every 3,000-response path.',
        'Counts and content checks do not measure browser responsiveness or constrained-device performance.']
    return result


def main():
    directory = Path(__file__).resolve().parents[1] / 'test-results' / f'topology-context-{uuid4().hex}'
    directory.mkdir(parents=True)
    path = directory / 'fixture.sqlite3'
    with TestClient(create_app(path), headers={'x-roleplay-client': 'workspace'}) as client:
        result = build_context(client)
    result['database'] = str(path)
    result['database_bytes'] = path.stat().st_size
    if result['database_bytes'] > 512 * 1024 * 1024:
        raise ValueError(f'Fixture exceeded 512 MiB; preserved for inspection at {directory}')
    manifest = directory / 'manifest.json'
    manifest.write_text(encode(result), encoding='utf-8')
    print(json.dumps({'manifest': str(manifest), 'database_bytes': result['database_bytes'],
                      'story_id': result['story_id'], 'branches': result['branch_count'],
                      'workspace_counts': result['workspace']['counts']}, indent=2))


if __name__ == '__main__':
    main()
