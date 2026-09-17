"""Explicit UI-only fixture. Never installed in the app or used as a provider fallback.

Run with `python -m tests.sidebar_ui_fixture` against the named browser review database.
The fixture's profile and conversation identify that no model was called.
"""
import asyncio
from pathlib import Path
from uuid import uuid4

from server.database import Database, one
from server.profiles import Profiles
from server.providers.config import ProfileConfig, ProfileCreate
from server.providers.events import ProviderEvent
from server.side_conversations import SideConversations, SideQuestion
from server.side_runner import SideRunner
from tests.test_profiles import MemoryVault


class FixtureProvider:
    async def generate(self, _profile, _prompt, _content):
        yield ProviderEvent(text="UI verification fixture — no model was called.\n\nSuggested unsent line:\nI turn the sealed letter over. ‘Who left this here?’", done=True)


async def seed():
    database = Database(Path(__file__).resolve().parents[1] / "data" / "browser-review.sqlite3")
    with database.connect() as connection:
        story = one(connection, "SELECT * FROM stories WHERE title=?", ("The observatory · UI review",))
        branch = one(connection, "SELECT * FROM branches WHERE story_id=? AND name='Main path'", (story["id"],))
    profile = Profiles(database, MemoryVault()).create(ProfileCreate(name="UI fixture · no model call",
                      config=ProfileConfig(provider="local", model="ui-fixture-only", base_url="http://127.0.0.1:1/v1")))
    service = SideConversations(database)
    thread = service.create_thread(story["id"], "UI fixture · composer handoff")
    result = service.ask(thread["id"], SideQuestion(operation_id=uuid4().hex, branch_id=branch["id"],
                         expected_revision=branch["revision"], profile_ids=[profile["profile_id"]],
                         question="UI fixture only: test carrying a suggested line into an unsent draft. No model call."))
    runner = SideRunner(database, FixtureProvider())
    await runner.run(result["reply_ids"][0])
    print(f"Created UI-only fixture conversation {thread['id']} in {database.path.name}.")


if __name__ == "__main__":
    asyncio.run(seed())
