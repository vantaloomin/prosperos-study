"""Explicitly labeled scene artifacts for UI QA in the isolated review database only."""
import asyncio
from pathlib import Path
from uuid import uuid4

from server.branches import Branches
from server.database import Database
from server.models import MessageCreate, StoryCreate
from server.profiles import Profiles
from server.prompts import initialize_prompts
from server.providers.config import ProfileConfig, ProfileCreate
from server.scenes.models import SceneChoice, SceneCreate, SceneStart, SceneStep
from server.scenes.runner import SceneRunner
from server.scenes.service import Scenes
from server.stories import Stories
from tests.test_profiles import MemoryVault
from tests.test_scenes import SceneProvider


async def generate(service, runner, run_id, step, profiles, **targets):
    run = service.detail(run_id)
    body = SceneStep(expected_revision=run["revision"], key=step, profile_ids=profiles, **targets)
    preview = service.preview(run_id, body)
    started = service.start(run_id, SceneStart(**body.model_dump(), preview_hash=preview["preview_hash"], operation_id=uuid4().hex))
    for job_id in started["job_ids"]:
        await runner.run(job_id)
    return started["job_ids"][0]


def choose(service, run_id, job_id, option=None):
    run = service.detail(run_id)
    service.decide(run_id, SceneChoice(operation_id=uuid4().hex, expected_revision=run["revision"], job_id=job_id, option_id=option), "choose")


async def seed():
    database = Database(Path(__file__).resolve().parents[1] / "data" / "browser-review.sqlite3")
    initialize_prompts(database)
    profiles = [Profiles(database, MemoryVault()).create(ProfileCreate(name=f"Scene fixture {label} · no model call",
                config=ProfileConfig(provider="local", model=f"ui-scene-{label.lower()}", base_url="http://127.0.0.1:1/v1")))
                for label in ("A", "B")]
    story = Stories(database).create(StoryCreate(title="Scene planning · UI review",
        premise="UI fixtures only. Validate plan choices, beat editing, saved approvals, and real unavailable-endpoint failures.",
        settings={"primary_profile_id": profiles[0]["profile_id"]}))
    Branches(database).append(story["branch_id"], MessageCreate(operation_id=uuid4().hex, expected_revision=0, role="narrator",
        text="UI fixture only. Wren waits beside the sealed letter. The player has not decided whether to inspect it."))
    service = Scenes(database)
    runner = SceneRunner(database, SceneProvider())
    ids = []
    for title in ("Choose the approach", "Edit the beats", "Approve the plan"):
        run = service.create(story["branch_id"], SceneCreate(operation_id=uuid4().hex, expected_revision=1,
                             title=f"{title} · UI fixture", direction="UI fixture only. Explore the sealed letter; leave the player's decisions open."))
        run_id = run["id"]
        ids.append(run_id)
        job_id = await generate(service, runner, run_id, "scene-options", [profile["profile_id"] for profile in profiles])
        if title == "Choose the approach":
            continue
        choose(service, run_id, job_id, "B")
        job_id = await generate(service, runner, run_id, "scene-beats", [])
        choose(service, run_id, job_id)
        await generate(service, runner, run_id, "scene-brief", [])
    print({"story": story, "scene_ids": ids, "database": database.path.name})


if __name__ == "__main__":
    asyncio.run(seed())
