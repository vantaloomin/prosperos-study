from server.agent_templates import initial_agent_settings
from server.branch_tools.curation import story_branches
from server.character_content import opening_metadata
from server.database import Database, decode, encode, identifier, many, now, one
from server.errors import require
from server.manifests import adopt_manifest, create_manifest, manifest_view
from server.mechanics.config import normalize_story_settings
from server.models import AttachmentUpdate, StoryCreate, StoryUpdate
from server.operations import previous, remember


def story_view(row: dict) -> dict:
    return {**row, "settings": decode(row["settings"]), "archived": bool(row["archived"])}


def check_revision(row: dict, expected: int):
    require(row["revision"] == expected, "This changed in another view. Refresh before trying again.", 409)


def create_branch(connection, story_id: str, manifest_id: str, name: str = "Main path") -> str:
    branch_id = identifier()
    connection.execute("INSERT INTO branches VALUES (?,?,?,NULL,?,NULL,NULL,0,?,?)",
                       (branch_id, story_id, name, manifest_id, now(), now()))
    return branch_id


class Stories:
    def __init__(self, database: Database):
        self.database = database

    def list(self) -> list[dict]:
        with self.database.connect() as connection:
            return [story_view(row) for row in many(connection,
                    "SELECT s.*, o.created_at AS restored_at FROM stories s LEFT JOIN archive_origins o ON o.id=s.id "
                    "ORDER BY s.updated_at DESC, s.id")]

    def create(self, body: StoryCreate) -> dict:
        with self.database.connect(write=True) as connection:
            payload = body.model_dump()
            if body.opening_source is None:
                payload.pop('opening_source')  # Preserve pre-greeting idempotency receipts.
            cached = previous(connection, body.operation_id, 'story-create', payload) if body.operation_id else None
            if cached is not None:
                return cached
            result = create_story(connection, body)
            if body.operation_id:
                return remember(connection, body.operation_id, 'story-create', payload, result)
            return result

    def detail(self, story_id: str) -> dict:
        with self.database.connect() as connection:
            story = story_view(one(connection, "SELECT * FROM stories WHERE id=?", (story_id,)))
            branches = story_branches(connection, story_id)
            return {**story, "branches": branches,
                    "attachments": manifest_view(connection, story["manifest_id"])}

    def update(self, story_id: str, body: StoryUpdate) -> dict:
        with self.database.connect(write=True) as connection:
            story = one(connection, "SELECT * FROM stories WHERE id=?", (story_id,))
            check_revision(story, body.expected_revision)
            connection.execute("UPDATE stories SET title=?,premise=?,settings=?,archived=?,"
                               "revision=revision+1,updated_at=? WHERE id=?",
                               (body.title, body.premise, encode(normalize_story_settings(body.settings)), body.archived, now(), story_id))
        return self.detail(story_id)

    def attachments(self, story_id: str, body: AttachmentUpdate) -> dict:
        payload = {"story_id": story_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "attach", payload)
            if cached is not None:
                return cached
            story = one(connection, "SELECT * FROM stories WHERE id=?", (story_id,))
            check_revision(story, body.expected_revision)
            manifest_id = create_manifest(connection, story_id, [a.model_dump() for a in body.attachments])
            adopt_manifest(connection, story, manifest_id, body.operation_id)
            return remember(connection, body.operation_id, "attach", payload, {"manifest_id": manifest_id})


def create_story(connection, body):
    """Create inside the caller's transaction, including source-import receipts."""
    validate_starting_profile(connection, body.settings)
    opening = opening_metadata(connection, body)
    story_id = identifier()
    connection.execute("INSERT INTO stories VALUES (?,?,?,?,NULL,0,0,?,?)",
                       (story_id, body.title, body.premise, encode(normalize_story_settings(initial_agent_settings(body.settings))), now(), now()))
    manifest_id = create_manifest(connection, story_id, [a.model_dump() for a in body.attachments])
    connection.execute("UPDATE stories SET manifest_id=? WHERE id=?", (manifest_id, story_id))
    branch_id = create_branch(connection, story_id, manifest_id)
    if body.opening_text:
        save_opening(connection, branch_id, body.opening_text, opening)
    return {"story_id": story_id, "branch_id": branch_id}


def validate_starting_profile(connection, settings):
    profile = settings.get('primary_profile_id')
    if profile is not None:
        require(isinstance(profile, str) and bool(profile), 'Choose a saved writing profile or the workspace default.')
        one(connection, 'SELECT id FROM profiles WHERE id=?', (profile,))


def save_opening(connection, branch_id, text, metadata):
    # Imported at call time because the branch service uses Story revision checks.
    from server.branches import insert_node, touch_branch

    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
    role = 'assistant' if metadata['source'] == 'character_greeting' else 'narrator'
    node_id = insert_node(connection, branch, text, role, metadata)
    touch_branch(connection, branch_id, node_id)
