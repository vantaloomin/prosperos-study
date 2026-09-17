"""Labeled saved patch results in the isolated QA database; no live runner replacement."""
import asyncio
from pathlib import Path
from uuid import uuid4

from server.branches import Branches
from server.database import Database
from server.models import MessageCreate, StoryCreate
from server.profiles import Profiles
from server.prompts import initialize_prompts
from server.providers.config import ProfileConfig, ProfileCreate
from server.scenes.revision_models import Resolution, RevisionApproval, TriageEdit
from server.scenes.runner import SceneRunner
from server.scenes.service import Scenes
from server.stories import Stories
from tests.drafting_ui_fixture import seed_plan
from tests.revision_ui_fixture import seed_reports
from tests.scene_ui_fixture import choose, generate
from tests.test_profiles import MemoryVault
from tests.test_scene_drafting import DraftProvider
from tests.test_scene_patches import PatchProvider
from tests.test_scene_revisions import RevisionProvider


async def approve_fixture(database, story, scenes, scene_id, profiles, runner):
    reports = await seed_reports(database, story, scenes, scene_id, profiles)
    runner.provider = RevisionProvider()
    triage = await generate(scenes, runner, scene_id, 'scene-triage', profiles[:1], review_job_ids=[reports['job_ids'][1]])
    choose(scenes, scene_id, triage)
    verdict = await generate(scenes, runner, scene_id, 'scene-verify', profiles[:1], item_id='t1')
    choose(scenes, scene_id, verdict)
    run = scenes.detail(scene_id)
    evidence = run['revision_plan']['verifications']['t1']['evidence']
    scenes.decide(scene_id, TriageEdit(operation_id=uuid4().hex, expected_revision=run['revision'], item_id='t1',
        resolution=Resolution(disposition='overrule', reason='Fixture evidence leaves the player’s decision open.', evidence=evidence)), 'resolve')
    scenes.decide(scene_id, RevisionApproval(operation_id=uuid4().hex, expected_revision=scenes.detail(scene_id)['revision'],
        package='C', confirmed_hold_ids=['t2'], note='UI fixture only: approved changes, not accepted Story text.'), 'approve-revision')


async def patch_plan(database, story, scenes, profiles, title):
    runner = SceneRunner(database, DraftProvider())
    scene_id = await seed_plan(scenes, runner, story, profiles, title, True, 'rendered')
    dialogue = next(job for job in scenes.detail(scene_id)['jobs'] if job['step'] == 'scene-dialogue')
    choose(scenes, scene_id, dialogue['id'])
    choose(scenes, scene_id, await generate(scenes, runner, scene_id, 'scene-coverage', profiles[:1]))
    await approve_fixture(database, story, scenes, scene_id, profiles, runner)
    runner.provider = PatchProvider()
    for step in ('scene-patch', 'scene-dialogue-patch'):
        choose(scenes, scene_id, await generate(scenes, runner, scene_id, step, profiles))
    runner.provider.fail_check = True
    failed = await generate(scenes, runner, scene_id, 'scene-patch-check', profiles[:1])
    runner.provider.fail_check = False
    await generate(scenes, runner, scene_id, 'scene-patch-check', profiles[1:])
    if title == 'Correct one failed check':
        choose(scenes, scene_id, failed)
    return scene_id


async def seed():
    database = Database(Path(__file__).resolve().parents[1] / 'data' / 'browser-review.sqlite3')
    initialize_prompts(database)
    profiles = [Profiles(database, MemoryVault()).create(ProfileCreate(name=f'Patch partner {label} · UI fixture',
        config=ProfileConfig(provider='local', model=f'ui-patch-{label.lower()}', base_url='http://127.0.0.1:1/v1')))['profile_id']
        for label in ('A', 'B')]
    story = Stories(database).create(StoryCreate(title='Scene patches · UI review',
        premise='Labeled saved patch/check fixtures. Real requests use an unavailable loopback endpoint. The player decides what happens next.',
        settings={'primary_profile_id': profiles[0]}))
    Branches(database).append(story['branch_id'], MessageCreate(operation_id=uuid4().hex, expected_revision=0,
        role='narrator', text='UI fixture only. Wren waits beside the sealed letter. The player has not acted.'))
    scenes = Scenes(database)
    plans = {title: await patch_plan(database, story, scenes, profiles, title)
             for title in ('Inspect revisions', 'Correct one failed check')}
    print({'story': story, 'plans': plans, 'profiles': profiles, 'database': database.path.name})


if __name__ == '__main__':
    asyncio.run(seed())
