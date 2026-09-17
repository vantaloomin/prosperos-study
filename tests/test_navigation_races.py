import asyncio
from uuid import uuid4

import httpx

from server.branches import Branches
from server.generation_models import GenerateRequest
from server.generations import Generations
from server.main import create_app
from server.models import ForkCreate, MessageCreate, StoryCreate
from server.profiles import Profiles
from server.providers.config import ProfileConfig, ProfileCreate
from server.stories import Stories
from tests.navigation_race_server import install_controls
from tests.test_profiles import MemoryVault


def fixture(tmp_path):
    app = create_app(tmp_path / 'race.sqlite3')
    database = app.state.database
    story = Stories(database).create(StoryCreate(title='Synthetic navigation race'))
    branches = Branches(database)
    first = story['branch_id']
    branches.append(first, MessageCreate(operation_id=uuid4().hex, expected_revision=0, text='Source-only text.'))
    other = branches.fork(first, ForkCreate(operation_id=uuid4().hex, expected_revision=1, name='Empty descendant'))['branch_id']
    gates, writer = install_controls(app, {'a': first, 'b': other})
    return app, gates, writer, first, other


def test_real_branch_responses_can_complete_out_of_order_and_keep_exact_paths(tmp_path):
    async def run():
        app, gates, _, first, other = fixture(tmp_path)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://testserver') as client:
            gates.hold('a')
            gates.hold('b')
            pending = [asyncio.create_task(client.get(f'/api/branches/{key}')) for key in (first, other)]
            await asyncio.wait_for(asyncio.gather(*(g['entered'].wait() for g in gates.gates.values())), 3)
            gates.release('b')
            second = await asyncio.wait_for(pending[1], 3)
            assert second.json()['id'] == other and not pending[0].done()
            gates.release('a')
            initial = await asyncio.wait_for(pending[0], 3)
            assert initial.json()['id'] == first
            assert [m['text'] for m in initial.json()['messages']] == ['Source-only text.']
            assert second.json()['messages'] == []
            assert [x['key'] for x in gates.events if x['kind'] == 'response'] == ['b', 'a']
    asyncio.run(run())


def test_draft_finishes_on_original_branch_without_accepting_or_changing_other_history(tmp_path):
    async def run():
        app, _, writer, first, other = fixture(tmp_path)
        database = app.state.database
        profile = Profiles(database, MemoryVault()).create(ProfileCreate(name='Synthetic writer',
            config=ProfileConfig(provider='local', model='fixture-only')))
        service = Generations(database)
        generation = service.create(first, GenerateRequest(operation_id=uuid4().hex, expected_revision=1,
                                                           profile_ids=[profile['profile_id']]))
        candidate = generation['candidate_ids'][0]
        task = asyncio.create_task(app.state.runner._run(candidate))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://testserver') as client:
            for _ in range(60):
                if writer.phase == 'paused':
                    break
                await asyncio.sleep(0.01)
            partial = service.detail(generation['id'])['candidates'][0]
            assert partial['status'] == 'running' and 'paused draft' in partial['output']
            assert (await client.get(f'/api/branches/{other}/generations')).json() == []
            assert (await client.get(f'/api/branches/{other}')).json()['messages'] == []
            writer.finish.set()
            await asyncio.wait_for(task, 3)
            complete = service.detail(generation['id'])['candidates'][0]
            assert complete['status'] == 'done' and 'original branch' in complete['output']
            assert len((await client.get(f'/api/branches/{first}')).json()['messages']) == 1
            assert (await client.get(f'/api/branches/{other}/generations')).json() == []
            assert writer.calls == 1
    asyncio.run(run())
