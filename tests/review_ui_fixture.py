"""Labeled specialist reports for UI checks; writes only the isolated browser review database."""
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from server.branches import Branches
from server.database import Database, decode
from server.models import MessageCreate, StoryCreate
from server.profiles import Profiles
from server.prompts import initialize_prompts
from server.providers.config import ProfileConfig, ProfileCreate
from server.providers.events import ProviderEvent
from server.stories import Stories
from server.workflow.models import ReviewPreview, ReviewStart, ReviewStep
from server.workflow.reviews import Reviews
from server.workflow.runner import ReviewRunner
from tests.test_profiles import MemoryVault


class ReviewFixture:
    async def generate(self, _profile, _prompt, content):
        context = decode(content)
        source = next(item for item in context["sources"] if item["kind"] == "draft")
        result = {"summary": f"UI fixture only — no model was called. {context['role']}: the pause leaves the next decision open.",
                  "findings": [{"severity": "soft", "source_id": source["id"], "quote": source["text"],
                                "explanation": "Fixture observation: this wording leaves the letter's origin unresolved.",
                                "suggestion": "Keep the uncertainty if the next choice belongs to the player."}]}
        yield ProviderEvent(text=json.dumps(result), done=True)


async def seed():
    database = Database(Path(__file__).resolve().parents[1] / "data" / "browser-review.sqlite3")
    initialize_prompts(database)
    profiles = [Profiles(database, MemoryVault()).create(ProfileCreate(name=f"Review fixture {label} · no model call",
                config=ProfileConfig(provider="local", model=f"ui-review-{label.lower()}", base_url="http://127.0.0.1:1/v1")))
                for label in ["A", "B"]]
    story = Stories(database).create(StoryCreate(title="Specialist reviews · UI review",
        premise="Clearly labeled UI fixtures for specialist reports, explicit comparison and editable step routing.",
        settings={"primary_profile_id": profiles[0]["profile_id"]}))
    branches = Branches(database)
    branches.append(story["branch_id"], MessageCreate(operation_id=uuid4().hex, expected_revision=0, role="narrator",
                    text="UI fixture only. Wren places a sealed letter beside the lamp. She waits for an answer."))
    branches.append(story["branch_id"], MessageCreate(operation_id=uuid4().hex, expected_revision=1,
                    text='“Who left this here?” I ask, leaving the seal intact.'))
    service = Reviews(database)
    body = ReviewPreview(expected_revision=2, steps=[
        ReviewStep(key="review-dialogue", profile_ids=[item["profile_id"] for item in profiles]),
        ReviewStep(key="review-continuity")])
    preview = service.preview(story["branch_id"], body)
    run = service.create(story["branch_id"], ReviewStart(**body.model_dump(), operation_id=uuid4().hex,
                                                     preview_hash=preview["preview_hash"]))
    runner = ReviewRunner(database, ReviewFixture())
    for job_id in run["job_ids"]:
        await runner.run(job_id)
    print({"story": story, "review_id": run["id"], "profile_ids": [item["profile_id"] for item in profiles],
           "database": database.path.name})


if __name__ == "__main__":
    asyncio.run(seed())
