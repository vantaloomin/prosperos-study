from server.agent_switches import require_agent
from server.background.storage import bind
from server.branches import insert_node, touch_branch
from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.generation_context import generation_snapshot
from server.mechanics.storage import accepted_state
from server.operations import previous, remember


def candidate_view(row: dict):
    profile = decode(row["profile"])
    profile.pop("credential_ref", None)
    return {**row, "profile": profile, "usage": decode(row["usage"])}


def stale_target(connection, snapshot):
    original = snapshot["branch"]
    branch = one(connection, "SELECT * FROM branches WHERE id=?", (original["id"],))
    story = one(connection, "SELECT * FROM stories WHERE id=?", (original["story_id"],))
    stale = branch["revision"] != original["revision"] or story["revision"] != snapshot["story_revision"]
    return branch, stale


def record_generation(connection, snapshot, profiles):
    generation_id = identifier()
    connection.execute("INSERT INTO generations VALUES (?,?,?,?)",
                       (generation_id, snapshot['branch']['id'], encode(snapshot), now()))
    candidates = [Generations._candidate(connection, generation_id, profile) for profile in profiles]
    return {'id': generation_id, 'candidate_ids': candidates}


class Generations:
    def __init__(self, database):
        self.database = database

    def create(self, branch_id, body):
        payload = {"branch_id": branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "generate", payload)
            if cached is not None:
                return cached
            snapshot, profiles = generation_snapshot(connection, branch_id, body)
            result = record_generation(connection, snapshot, profiles)
            return remember(connection, body.operation_id, "generate", payload, result)

    @staticmethod
    def _candidate(connection, generation_id, profile):
        candidate_id = identifier()
        connection.execute("INSERT INTO candidates (id,generation_id,profile,status,updated_at) VALUES (?,?,?,?,?)",
                           (candidate_id, generation_id, encode(profile), "queued", now()))
        return candidate_id

    def detail(self, generation_id):
        with self.database.connect() as connection:
            generation = one(connection, "SELECT * FROM generations WHERE id=?", (generation_id,))
            candidates = many(connection, "SELECT * FROM candidates WHERE generation_id=? ORDER BY rowid", (generation_id,))
            snapshot = decode(generation["snapshot"])
            _, stale = stale_target(connection, snapshot)
            return {**generation, "snapshot": snapshot, "stale": stale,
                    "candidates": [candidate_view(row) for row in candidates]}

    def alternate(self, candidate_id, body):
        payload = {"candidate_id": candidate_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "alternate", payload)
            if cached is not None:
                return cached
            require_agent(connection, "writer")
            source = one(connection, "SELECT * FROM candidates WHERE id=?", (candidate_id,))
            require(source["status"] == "done", "Finish this draft before making another telling.", 409)
            candidate = self._candidate(connection, source["generation_id"], decode(source["profile"]))
            return remember(connection, body.operation_id, "alternate", payload,
                            {"id": source["generation_id"], "candidate_id": candidate})

    def list(self, branch_id):
        with self.database.connect() as connection:
            return many(connection, "SELECT id,branch_id,created_at FROM generations WHERE branch_id=? "
                        "ORDER BY created_at DESC", (branch_id,))

    def attempts(self, candidate_id):
        with self.database.connect() as connection:
            one(connection, "SELECT id FROM candidates WHERE id=?", (candidate_id,))
            rows = many(connection, "SELECT * FROM generation_attempts WHERE candidate_id=? ORDER BY attempt DESC",
                        (candidate_id,))
            return [{**row, "usage": decode(row["usage"])} for row in rows]

    def accept(self, candidate_id, body):
        payload = {"candidate_id": candidate_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "accept", payload)
            if cached is not None:
                return cached
            candidate = one(connection, "SELECT * FROM candidates WHERE id=?", (candidate_id,))
            if candidate["accepted_branch_id"]:
                return {"branch_id": candidate["accepted_branch_id"], "node_id": candidate["accepted_node_id"]}
            require(candidate["status"] == "done", "Only a completed draft can be accepted.", 409)
            generation = one(connection, "SELECT * FROM generations WHERE id=?", (candidate["generation_id"],))
            snapshot = decode(generation["snapshot"])
            branch, stale = stale_target(connection, snapshot)
            require(not stale or body.as_new_branch,
                    "The story changed after this draft started. Keep it as a new branch or generate again.", 409)
            target = self._accept_branch(connection, branch, snapshot, body)
            opportunity_id = snapshot.get("opportunity_id")
            state = accepted_state(connection, target, opportunity_id, allow_fork=True)
            node_id = insert_node(connection, target, candidate["output"], "assistant",
                                  {"source": "generated", "candidate_id": candidate_id,
                                   "generation_id": generation["id"], "prompt_version_id": snapshot["prompt"]["id"],
                                   "opportunity_id": opportunity_id}, state)
            touch_branch(connection, target["id"], node_id)
            connection.execute("UPDATE candidates SET accepted_branch_id=?,accepted_node_id=? WHERE id=?",
                               (target["id"], node_id, candidate_id))
            return remember(connection, body.operation_id, "accept", payload,
                            {"branch_id": target["id"], "node_id": node_id})

    @staticmethod
    def _accept_branch(connection, branch, snapshot, body):
        if not body.as_new_branch:
            return branch
        original = snapshot["branch"]
        target_id = identifier()
        connection.execute("INSERT INTO branches VALUES (?,?,?,?,?,?,?,0,?,?)",
                           (target_id, original["story_id"], body.branch_name, original["head_id"],
                            original["manifest_id"], original["id"], original["head_id"], now(), now()))
        bind(connection, target_id, snapshot.get('background_state_id'))
        return {**original, "id": target_id}
