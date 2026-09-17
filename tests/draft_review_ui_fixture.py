"""Saved unaccepted-draft reports in the isolated QA database, never a live adapter."""
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
from tests.review_ui_fixture import ReviewFixture
from tests.scene_ui_fixture import choose
from tests.test_profiles import MemoryVault
from tests.test_scene_drafting import DraftProvider


async def seed():
    database = Database(Path(__file__).resolve().parents[1] / "data" / "browser-review.sqlite3")
    initialize_prompts(database)
    profiles = [Profiles(database, MemoryVault()).create(ProfileCreate(name=f"Draft reader {label} · UI fixture",
        config=ProfileConfig(provider="local", model=f"ui-draft-reader-{label.lower()}", base_url="http://127.0.0.1:1/v1")))["profile_id"]
        for label in ("A", "B")]
    story = Stories(database).create(StoryCreate(title="Independent draft reviews · UI review",
        premise="Labeled saved draft and reviewer fixtures. Real requests use an unavailable endpoint; no model output is simulated in production.",
        settings={"primary_profile_id": profiles[0]}))
    Branches(database).append(story["branch_id"], MessageCreate(operation_id=uuid4().hex, expected_revision=0,
        role="narrator", text="UI fixture only. Wren waits beside the sealed letter. The next action belongs to the player."))
    scenes, scene_runner = Scenes(database), SceneRunner(database, DraftProvider())
    scene_id = await seed_plan(scenes, scene_runner, story, profiles, "The unaccepted letter scene", False, "rendered")
    scene = scenes.detail(scene_id)
    coverage = next(job for job in scene["jobs"] if job["step"] == "scene-coverage")
    choose(scenes, scene_id, coverage["id"])
    body = ReviewPreview(expected_revision=1, scene_id=scene_id, scene_revision=scenes.detail(scene_id)["revision"], steps=[
        ReviewStep(key="review-dialogue", profile_ids=profiles), ReviewStep(key="review-continuity"), ReviewStep(key="review-rules")])
    reviews = Reviews(database)
    preview = reviews.preview(story["branch_id"], body)
    result = reviews.create(story["branch_id"], ReviewStart(**body.model_dump(), operation_id=uuid4().hex, preview_hash=preview["preview_hash"]))
    runner = ReviewRunner(database, ReviewFixture())
    for job_id in result["job_ids"]:
        await runner.run(job_id)
    print({"story": story, "scene_id": scene_id, "review_id": result["id"], "profiles": profiles, "database": database.path.name})


if __name__ == "__main__":
    asyncio.run(seed())
