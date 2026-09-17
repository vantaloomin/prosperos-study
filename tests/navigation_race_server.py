"""Disposable HTTP race controls; never installed by the production app factory."""
import argparse
import asyncio
import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from server.main import create_app
from server.providers.events import ProviderEvent


class ResponseGates:
    def __init__(self, paths):
        self.paths, self.gates, self.events = paths, {}, []

    def hold(self, key, fail=False):
        if key not in self.paths:
            raise HTTPException(404, 'Unknown fixture path.')
        previous = self.gates.get(key)
        if previous and not previous['released'].is_set():
            raise HTTPException(409, 'Release the existing gate first.')
        self.gates[key] = {'released': asyncio.Event(), 'entered': asyncio.Event(), 'fail': fail}
        return {'held': key, 'fail': fail}

    def release(self, key):
        if key not in self.gates:
            raise HTTPException(404, 'No gate to release.')
        self.events.append({'kind': 'released', 'key': key})
        self.gates[key]['released'].set()
        return {'released': key}

    async def intercept(self, request, call_next):
        key = next((key for key, branch in self.paths.items()
                    if request.url.path == f'/api/branches/{branch}'), None)
        gate = self.gates.get(key) if request.method == 'GET' else None
        if gate is None or gate['released'].is_set():
            return await call_next(request)
        self.events.append({'kind': 'waiting', 'key': key})
        gate['entered'].set()
        await gate['released'].wait()
        response = JSONResponse({'detail': 'Synthetic delayed retrieval failure.'}, status_code=503) if gate['fail'] else await call_next(request)
        self.events.append({'kind': 'response', 'key': key, 'status': response.status_code})
        return response

    def status(self):
        return {'events': self.events, 'gates': {key: {'waiting': gate['entered'].is_set(),
                'released': gate['released'].is_set()} for key, gate in self.gates.items()}}


class ControlledWriter:
    def __init__(self):
        self.finish = asyncio.Event()
        self.phase = 'idle'
        self.calls = 0

    async def generate(self, _profile, _prompt, _content):
        self.calls += 1
        self.phase = 'starting'
        await asyncio.sleep(0.2)
        yield ProviderEvent(text='SYNTHETIC NAVIGATION CHECK — paused draft, no model called.\n\n')
        self.phase = 'paused'
        await self.finish.wait()
        yield ProviderEvent(text='The draft finished on its original branch. No Story text was accepted.', done=True)
        self.phase = 'done'


def install_controls(app, paths):
    gates, writer = ResponseGates(paths), ControlledWriter()
    app.state.runner.provider = writer
    app.middleware('http')(gates.intercept)
    router = APIRouter(prefix='/_test')

    @router.get('/status')
    async def status():
        return {**gates.status(), 'writer': {'phase': writer.phase, 'calls': writer.calls}}

    @router.post('/hold/{key}')
    async def hold(key: str, fail: bool = False):
        return gates.hold(key, fail)

    @router.post('/release/{key}')
    async def release(key: str):
        return gates.release(key)

    @router.post('/finish-writer')
    async def finish_writer():
        writer.finish.set()
        return {'released': True}

    # The production factory mounts the frontend last; test endpoints precede it.
    frontend = app.router.routes.pop() if app.router.routes[-1].name == 'frontend' else None
    app.include_router(router)
    if frontend:
        app.router.routes.append(frontend)
    return gates, writer


def factory():
    folder = Path(os.environ['ROLEPLAY_RACE_DIR']).resolve()
    allowed = (Path(__file__).resolve().parents[1] / 'test-results').resolve()
    if folder.parent != allowed or not folder.name.startswith('navigation-race-'):
        raise ValueError('Use a newly copied disposable navigation-race fixture.')
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    app = create_app(folder / 'fixture.sqlite3')
    install_controls(app, {key: value['id'] for key, value in manifest['paths'].items()})
    return app


def copy_fixture(source):
    source = Path(source).resolve()
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    folder = Path(__file__).resolve().parents[1] / 'test-results' / f'navigation-race-{uuid4().hex}'
    folder.mkdir()
    target = folder / 'fixture.sqlite3'
    with sqlite3.connect((source / 'fixture.sqlite3').as_uri() + '?mode=ro', uri=True) as origin:
        with sqlite3.connect(target) as destination:
            origin.backup(destination)
            destination.execute('UPDATE stories SET title=? WHERE id=?',
                ('Navigation race review · synthetic records', manifest['story_id']))
    manifest.update(database=str(target), source_fixture=str(source), purpose='Controlled navigation races; synthetic writer only.')
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    print(folder)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Existing mature fixture directory to copy read-only.')
    copy_fixture(parser.parse_args().source)
