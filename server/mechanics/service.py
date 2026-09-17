import secrets

from server.background.storage import bind, state_id
from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.lore.runtime import attach_lore, frozen_lore
from server.mechanics.config import configured_tables, read_settings
from server.mechanics.engine import resolve_beat
from server.mechanics.randomness import ALGORITHM, Draws
from server.mechanics.state import node_state
from server.mechanics.storage import mechanics_brief, opportunity_view
from server.mechanics.table_engine import TableSet
from server.operations import previous, remember
from server.stories import check_revision


class Mechanics:
    def __init__(self, database):
        self.database = database

    def context(self, branch_id):
        with self.database.connect() as connection:
            branch, story = self._source(connection, branch_id)
            settings = read_settings(story)
            versions = configured_tables(connection, settings)
            tables = TableSet(versions, settings)
            return {**mechanics_brief(connection, branch), "story_revision": story["revision"],
                    "settings": settings.model_dump(), "tables": list(versions.values()),
                    "odds": {key: tables.odds(key, settings.subresults if key == "handling" else True) for key in versions},
                    "history": many(connection, "SELECT id,branch_id,head_key,created_at FROM mechanic_opportunities "
                                    "WHERE branch_id=? ORDER BY created_at DESC", (branch_id,))}

    def configure(self, story_id, body):
        with self.database.connect(write=True) as connection:
            story = one(connection, "SELECT * FROM stories WHERE id=?", (story_id,))
            check_revision(story, body.expected_revision)
            settings = body.settings.model_copy(deep=True)
            if body.use_latest_tables:
                settings.table_versions = {}
            versions = configured_tables(connection, settings)
            settings.table_versions = {key: value["id"] for key, value in versions.items()}
            data = {**decode(story["settings"]), "randomness": settings.model_dump()}
            connection.execute("UPDATE stories SET settings=?,revision=revision+1,updated_at=? WHERE id=?",
                               (encode(data), now(), story_id))
            return {"settings": settings.model_dump()}

    def detail(self, opportunity_id):
        with self.database.connect() as connection:
            return opportunity_view(one(connection, "SELECT * FROM mechanic_opportunities WHERE id=?", (opportunity_id,)))

    def prepare(self, branch_id, body):
        payload = {"branch_id": branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "prepare_beat", payload)
            if cached is not None:
                return cached
            branch, story = self._source(connection, branch_id)
            check_revision(branch, body.expected_revision)
            settings = read_settings(story)
            require(settings.enabled or body.manual or body.reroll_of,
                    "Automatic randomness is off. Enable it or explicitly choose Roll now.", 409)
            if body.reroll_of:
                branch = self._reroll_branch(connection, branch, body)
            result = self._prepare(connection, branch, story, settings, body)
            return remember(connection, body.operation_id, "prepare_beat", payload, result)

    @staticmethod
    def _source(connection, branch_id):
        branch = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
        story = one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
        return branch, story

    @staticmethod
    def _prepare(connection, branch, story, settings, body):
        existing = connection.execute("SELECT * FROM mechanic_opportunities WHERE branch_id=? AND head_key=?",
                                      (branch["id"], branch["head_id"] or "")).fetchone()
        if existing:
            snapshot = decode(existing["snapshot"])
            require(snapshot["beat"] == body.beat.model_dump() and snapshot["manual"] == body.manual,
                    "This point already has a frozen beat. Reuse it or reroll on a new branch.", 409)
            return {"id": existing["id"], "branch_id": branch["id"], "reused": True}
        versions = configured_tables(connection, settings)
        settings = settings.model_copy(update={"table_versions": {key: value["id"] for key, value in versions.items()}})
        snapshot = resolve_beat(versions, settings, body.beat, node_state(connection, branch["head_id"]),
                                secrets.token_hex(16), body.manual)
        attach_lore(snapshot, frozen_lore(connection, branch))
        snapshot.update(branch=branch, story_revision=story["revision"], reroll_of=body.reroll_of)
        snapshot['background_state_id'] = state_id(connection, branch['id'])
        opportunity_id = identifier()
        connection.execute("INSERT INTO mechanic_opportunities VALUES (?,?,?,?,?,?)",
                           (opportunity_id, story["id"], branch["id"], branch["head_id"] or "", encode(snapshot), now()))
        return {"id": opportunity_id, "branch_id": branch["id"], "reused": False}

    @staticmethod
    def _reroll_branch(connection, branch, body):
        original = opportunity_view(one(connection, "SELECT * FROM mechanic_opportunities WHERE id=?", (body.reroll_of,)))
        require(original["story_id"] == branch["story_id"], "Choose a roll from this story.")
        source = original["snapshot"]["branch"]
        target_id = identifier()
        connection.execute("INSERT INTO branches VALUES (?,?,?,?,?,?,?,0,?,?)",
                           (target_id, source["story_id"], body.branch_name, source["head_id"], source["manifest_id"],
                            source["id"], source["head_id"], now(), now()))
        bind(connection, target_id, original['snapshot'].get('background_state_id'))
        return {**source, "id": target_id, "revision": 0, "name": body.branch_name}

    def preview(self, table_id, body):
        with self.database.connect() as connection:
            versions = configured_tables(connection, body.settings)
            require(table_id in versions, "This table does not exist.", 404)
            tables, draws = TableSet(versions, body.settings), Draws(body.seed)
            result = tables.resolve(table_id, draws, "preview")
            return {"preview_only": True, "algorithm": ALGORITHM, "seed": body.seed, "result": result,
                    "draws": draws.log, "tables": tables.used, "odds": tables.odds(table_id)}
