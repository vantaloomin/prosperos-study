"""Labeled saved proposals in the separate browser QA database; real adapters stay unchanged."""
import asyncio
from pathlib import Path
from uuid import uuid4

from server.branches import Branches
from server.database import Database, encode
from server.models import MessageCreate, StoryCreate
from server.profiles import Profiles
from server.prompts import initialize_prompts
from server.providers.config import ProfileConfig, ProfileCreate
from server.scenes.runner import SceneRunner
from server.scenes.service import Scenes
from server.stories import Stories
from tests.patch_ui_fixture import patch_plan
from tests.scene_ui_fixture import choose, generate
from tests.test_profiles import MemoryVault
from tests.test_scene_continuity import ContinuityProvider


async def seed():
    database = Database(Path(__file__).resolve().parents[1] / 'data' / 'browser-review.sqlite3')
    initialize_prompts(database)
    profiles = [Profiles(database, MemoryVault()).create(ProfileCreate(name=f'Continuity partner {label} · UI fixture',
        config=ProfileConfig(provider='local', model=f'ui-continuity-{label.lower()}', base_url='http://127.0.0.1:1/v1')))['profile_id']
        for label in ('A', 'B')]
    story = Stories(database).create(StoryCreate(title='Scene acceptance · UI review',
        premise='Labeled saved continuity fixtures. Real requests use an unavailable loopback endpoint. The player decides what happens next.',
        settings={'primary_profile_id': profiles[0]}))
    Branches(database).append(story['branch_id'], MessageCreate(operation_id=uuid4().hex, expected_revision=0,
        role='narrator', text='UI fixture only. Wren waits beside the sealed letter. The player has not acted.'))
    scenes = Scenes(database)
    runner = SceneRunner(database, ContinuityProvider())
    plans = {}
    for title in ('Choose what becomes canon', 'Accept an earlier starting point'):
        scene_id = await patch_plan(database, story, scenes, profiles, title)
        passing = next(job for job in scenes.detail(scene_id)['jobs'] if job['step'] == 'scene-patch-check' and job['snapshot']['profile']['profile_id'] == profiles[1])
        choose(scenes, scene_id, passing['id'])
        proposal = await generate(scenes, runner, scene_id, 'scene-continuity', profiles)
        if title == 'Accept an earlier starting point':
            choose(scenes, scene_id, proposal)
        plans[title] = scene_id
    print(encode({'story': story, 'plans': plans, 'profiles': profiles, 'database': database.path.name}))


if __name__ == '__main__':
    asyncio.run(seed())
