"""Clearly labeled UI fixture, limited to browser-review.sqlite3; never a runtime fallback."""
import asyncio
from pathlib import Path
from uuid import uuid4

from server.branches import Branches
from server.database import Database
from server.generation_models import AcceptCandidate, AlternateRequest, GenerateRequest
from server.generation_runner import GenerationRunner
from server.generations import Generations
from server.mechanics.models import Beat, PrepareBeat
from server.mechanics.service import Mechanics
from server.models import MessageCreate, StoryCreate
from server.profiles import Profiles
from server.providers.config import ProfileConfig, ProfileCreate
from server.providers.events import ProviderEvent
from server.stories import Stories
from tests.test_profiles import MemoryVault


class FixtureProvider:
    def __init__(self):
        self.count = 0

    async def generate(self, _profile, _prompt, _content):
        self.count += 1
        yield ProviderEvent(text=f"UI fixture only — no model was called. Telling {self.count}.\n\n"
                            "Wren rests the letter beside the lamp and leaves the question open.", done=True)


async def seed():
    database = Database(Path(__file__).resolve().parents[1] / "data" / "browser-review.sqlite3")
    profile = Profiles(database, MemoryVault()).create(ProfileCreate(name="Alternative UI fixture · no model call",
        config=ProfileConfig(provider="local", model="ui-fixture-only", base_url="http://127.0.0.1:1/v1")))
    story = Stories(database).create(StoryCreate(title="Alternative tellings · UI review",
        premise="UI fixtures, not model output. Test draft navigation, preserved rolls and branch acceptance.",
        settings={"primary_profile_id": profile["profile_id"]}))
    Mechanics(database).prepare(story["branch_id"], PrepareBeat(operation_id=uuid4().hex,
        expected_revision=0, beat=Beat(label="UI fixture: a quiet opening"), manual=True))
    service = Generations(database)
    generation = service.create(story["branch_id"], GenerateRequest(operation_id=uuid4().hex,
        expected_revision=0, profile_ids=[profile["profile_id"]]))
    runner = GenerationRunner(database, MemoryVault())
    runner.provider = FixtureProvider()
    source = generation["candidate_ids"][0]
    await runner._run(source)
    alternate = service.alternate(source, AlternateRequest(operation_id=uuid4().hex))
    await runner._run(alternate["candidate_id"])
    service.accept(source, AcceptCandidate(operation_id=uuid4().hex))
    Branches(database).append(story["branch_id"], MessageCreate(operation_id=uuid4().hex,
        expected_revision=1, text="UI fixture continuation: this later choice must remain on the original path."))
    print({"story": story, "generation_id": generation["id"], "database": database.path.name})


if __name__ == "__main__":
    asyncio.run(seed())
