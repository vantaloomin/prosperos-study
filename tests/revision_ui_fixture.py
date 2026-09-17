"""Explicit saved triage/verdict fixtures; normal provider execution stays real."""
import asyncio
from pathlib import Path
from uuid import uuid4

from server.branches import Branches
from server.database import Database
from server.models import MessageCreate, StoryCreate
from server.profiles import Profiles
from server.prompts import initialize_prompts
from server.providers.config import ProfileConfig, ProfileCreate
from server.scenes.runner import SceneRunner
from server.scenes.service import Scenes
from server.stories import Stories
from server.workflow.models import ReviewPreview, ReviewStart, ReviewStep
from server.workflow.reviews import Reviews
from server.workflow.runner import ReviewRunner
from tests.drafting_ui_fixture import seed_plan
from tests.scene_ui_fixture import choose, generate
from tests.test_profiles import MemoryVault
from tests.test_scene_drafting import DraftProvider
from tests.test_scene_revisions import RevisionProvider, RevisionReviewProvider


async def seed_reports(database, story, scenes, scene_id, profiles):
    reviews = Reviews(database)
    body = ReviewPreview(expected_revision=1, scene_id=scene_id, scene_revision=scenes.detail(scene_id)['revision'],
                         steps=[ReviewStep(key='review-rules', profile_ids=profiles)])
    preview = reviews.preview(story['branch_id'], body)
    result = reviews.create(story['branch_id'], ReviewStart(**body.model_dump(), operation_id=uuid4().hex, preview_hash=preview['preview_hash']))
    runner = ReviewRunner(database, RevisionReviewProvider())
    for job_id in result['job_ids']:
        await runner.run(job_id)
    reviews.select(result['id'], result['job_ids'][1])
    return result


async def seed():
    database = Database(Path(__file__).resolve().parents[1] / 'data' / 'browser-review.sqlite3')
    initialize_prompts(database)
    profiles = [Profiles(database, MemoryVault()).create(ProfileCreate(name=f'Revision partner {label} · UI fixture',
        config=ProfileConfig(provider='local', model=f'ui-revision-{label.lower()}', base_url='http://127.0.0.1:1/v1')))['profile_id']
        for label in ('A', 'B')]
    story = Stories(database).create(StoryCreate(title='Revision decisions · UI review',
        premise='Saved test fixtures only. Real model requests use an unavailable loopback endpoint. The player controls the next action.',
        settings={'primary_profile_id': profiles[0]}))
    Branches(database).append(story['branch_id'], MessageCreate(operation_id=uuid4().hex, expected_revision=0,
        role='narrator', text='UI fixture only. Wren waits beside the sealed letter. The next decision belongs to the player.'))
    scenes, runner = Scenes(database), SceneRunner(database, DraftProvider())
    scene_id = await seed_plan(scenes, runner, story, profiles, 'Settle the letter reviews', False, 'rendered')
    coverage = next(job for job in scenes.detail(scene_id)['jobs'] if job['step'] == 'scene-coverage')
    choose(scenes, scene_id, coverage['id'])
    reports = await seed_reports(database, story, scenes, scene_id, profiles)
    runner.provider = RevisionProvider()
    triage = await generate(scenes, runner, scene_id, 'scene-triage', profiles, review_job_ids=[reports['job_ids'][1]])
    choose(scenes, scene_id, triage)
    await generate(scenes, runner, scene_id, 'scene-verify', profiles, item_id='t1')
    print({'story': story, 'scene_id': scene_id, 'review': reports, 'profiles': profiles, 'database': database.path.name})


if __name__ == '__main__':
    asyncio.run(seed())
