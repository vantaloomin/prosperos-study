"""Saved drafting results for UI review only; no production provider is replaced."""
import asyncio
from pathlib import Path
from uuid import uuid4

from server.branches import Branches
from server.database import Database
from server.models import MessageCreate, StoryCreate
from server.profiles import Profiles
from server.prompts import initialize_prompts
from server.providers.config import ProfileConfig, ProfileCreate
from server.scenes.models import SceneApproval, SceneCreate
from server.scenes.runner import SceneRunner
from server.scenes.service import Scenes
from server.stories import Stories
from tests.scene_ui_fixture import choose, generate
from tests.test_profiles import MemoryVault
from tests.test_scene_drafting import DraftProvider


async def seed_plan(service, runner, story, profiles, title, split, coverage):
    run_id = service.create(story["branch_id"], SceneCreate(operation_id=uuid4().hex, expected_revision=1,
        title=f"{title} · UI fixture", direction="UI fixture only. Offer the unopened letter, leaving the player's actions open.",
        propose_options=False, dialogue_split=split))["id"]
    for key in ["scene-beats", "scene-brief"]:
        choose(service, run_id, await generate(service, runner, run_id, key, profiles[:1]))
    run = service.detail(run_id)
    service.decide(run_id, SceneApproval(operation_id=uuid4().hex, expected_revision=run["revision"],
                   note="UI fixture approval only. No Story text is added."), "approve")
    choose(service, run_id, await generate(service, runner, run_id, "scene-draft", profiles))
    if split:
        await generate(service, runner, run_id, "scene-dialogue", profiles)
    else:
        runner.provider.coverage_status = coverage
        await generate(service, runner, run_id, "scene-coverage", profiles[:1])
    return run_id


async def seed():
    database = Database(Path(__file__).resolve().parents[1] / "data" / "browser-review.sqlite3")
    initialize_prompts(database)
    profiles = [Profiles(database, MemoryVault()).create(ProfileCreate(name=f"Draft fixture {label} · no model call",
        config=ProfileConfig(provider="local", model=f"ui-draft-{label.lower()}", base_url="http://127.0.0.1:1/v1")))["profile_id"]
        for label in ("A", "B")]
    story = Stories(database).create(StoryCreate(title="Scene drafting · UI review",
        premise="Labeled saved fixtures for dialogue, coverage and redrafting. Live generation uses an unavailable local endpoint.",
        settings={"primary_profile_id": profiles[0]}))
    Branches(database).append(story["branch_id"], MessageCreate(operation_id=uuid4().hex, expected_revision=0,
        role="narrator", text="UI fixture only. Wren waits beside the sealed letter. No player decision has been made."))
    service, runner = Scenes(database), SceneRunner(database, DraftProvider())
    plans = {}
    for title, split, coverage in [("Fill the spoken lines", True, "rendered"),
                                    ("A beat needs more room", False, "compressed"),
                                    ("Ready for independent review", False, "rendered")]:
        plans[title] = await seed_plan(service, runner, story, profiles, title, split, coverage)
    print({"story": story, "plans": plans, "profiles": profiles, "database": database.path.name})


if __name__ == "__main__":
    asyncio.run(seed())
