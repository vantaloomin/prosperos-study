from server.agent_switches import agent_enabled
from server.database import decode, encode, one
from server.errors import require
from server.profiles import primary_id, profile_snapshot
from server.stories import check_revision
from server.workflow.catalog import STEPS


def routing_view(connection, story):
    settings = decode(story["settings"])
    default = settings.get("primary_profile_id") or primary_id(connection)
    overrides = settings.get("step_profiles", {})
    return {"story_revision": story["revision"], "primary_profile_id": settings.get("primary_profile_id"),
            "workspace_primary_id": primary_id(connection), "effective_primary_id": default,
            "step_profiles": overrides, "steps": [{**step, "enabled": agent_enabled(connection, step["key"], story), "effective_profile_id": overrides.get(step["key"]) or default}
                                                     for step in STEPS]}


class Routing:
    def __init__(self, database):
        self.database = database

    def detail(self, story_id):
        with self.database.connect() as connection:
            return routing_view(connection, one(connection, "SELECT * FROM stories WHERE id=?", (story_id,)))

    def update(self, story_id, body):
        with self.database.connect(write=True) as connection:
            story = one(connection, "SELECT * FROM stories WHERE id=?", (story_id,))
            check_revision(story, body.expected_revision)
            allowed = {step["key"] for step in STEPS}
            require(set(body.step_profiles) <= allowed, "Choose a supported workflow step.")
            ids = set(body.step_profiles.values()) | ({body.primary_profile_id} if body.primary_profile_id else set())
            for profile_id in ids:
                profile_snapshot(connection, profile_id)
            settings = {**decode(story["settings"]), "step_profiles": body.step_profiles}
            settings.pop("primary_profile_id", None)
            if body.primary_profile_id:
                settings["primary_profile_id"] = body.primary_profile_id
            connection.execute("UPDATE stories SET settings=?,revision=revision+1 WHERE id=?", (encode(settings), story_id))
            return routing_view(connection, one(connection, "SELECT * FROM stories WHERE id=?", (story_id,)))
