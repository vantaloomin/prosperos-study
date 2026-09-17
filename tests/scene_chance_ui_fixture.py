"""Create isolated, explicitly labeled scene chance fixtures without provider calls."""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from server.database import encode
from server.main import create_app
from tests.test_mechanics import configure
from tests.test_scene_chance import BOUNDARY, no_event_seed
from tests.test_scene_continuity import ready_continuity
from tests.test_scenes import PLAN, ready_plan


def create_fixture(client, patch, label, enabled=True, checked=False):
    story = client.post('/api/stories', json={'title': f'Chance · {label} · UI fixture',
        'premise': 'Disposable UI fixture only. Saved stage results are test data, not live model output.'}).json()
    if enabled:
        configure(client, story, chance=100, cooldown=0)
    beats = [{**deepcopy(PLAN['beats'][0]), 'chance': dict(BOUNDARY)}]
    if not checked:
        for name, flags in [('Player decision', {'waiting_for_player': True}), ('Protected moment', {'protected': True})]:
            beats.append({**deepcopy(beats[0]), 'id': uuid4().hex, 'title': name,
                          'chance': {**BOUNDARY, **flags}})
    patch.setitem(PLAN, 'beats', beats)
    run_id, _ = ready_continuity(client, story) if checked else ready_plan(client, story)
    return {**story, 'run_id': run_id}


def main():
    directory = Path(__file__).resolve().parents[1] / 'test-results' / f'scene-chance-ui-{uuid4().hex}'
    directory.mkdir(parents=True)
    path = directory / 'fixture.sqlite3'
    with TestClient(create_app(path), headers={'x-roleplay-client': 'workspace'}) as client, MonkeyPatch.context() as patch:
        seed = no_event_seed(client)
        patch.setattr('server.scenes.chance.secrets.token_hex', lambda _length: seed)
        scenes = {label: create_fixture(client, patch, label, enabled, checked) for label, enabled, checked in [
            ('Edit boundaries', True, False), ('Approve boundaries', True, False),
            ('Accept checked scene', True, True), ('Automatic off', False, False)]}
    manifest = {'database': str(path), 'scenes': scenes, 'label': 'Test-only outputs; no provider calls.'}
    (directory / 'manifest.json').write_text(encode(manifest), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
