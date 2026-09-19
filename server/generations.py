from server.agent_switches import require_agent
from server.background.storage import bind
from server.branches import insert_node, touch_branch
from server.cleanup.storage import cleanup_rows, cleanup_view, selected_text
from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.generation_activity import activity_rows, generation_summaries
from server.generation_preparation import prepare_writer
from server.mechanics.storage import accepted_state
from server.memory.writer_recall_runner import reusable
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
        payload = {"branch_id": branch_id, **body.model_dump(exclude_none=True)}
        with self.database.connect() as connection:
            cached = previous(connection, body.operation_id, "generate", payload)
            if cached is not None:
                return cached
            prepared = prepare_writer(connection, branch_id, body)
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "generate", payload)
            if cached is not None:
                return cached
            prepared.validate(connection, body)
            result = record_generation(connection, prepared.snapshot, prepared.profiles)
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
            activity = activity_rows(connection, generation_id)
            cleanups = cleanup_rows(connection, generation_id)
            return {**generation, "snapshot": snapshot, "stale": stale,
                    "candidates": [{**candidate_view(row), 'activity': activity.get(row['id']),
                                    'cleanup': cleanup_view(connection, row, cleanups[row['id']]) if row['id'] in cleanups else None}
                                   for row in candidates]}

    def alternate(self, candidate_id, body):
        payload = {"candidate_id": candidate_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "alternate", payload)
            if cached is not None:
                return cached
            source = one(connection, "SELECT * FROM candidates WHERE id=?", (candidate_id,))
            story = one(connection, 'SELECT s.* FROM stories s JOIN branches b ON b.story_id=s.id '
                        'JOIN generations g ON g.branch_id=b.id WHERE g.id=?', (source['generation_id'],))
            require_agent(connection, 'writer', story)
            require(source["status"] == "done", "Finish this draft before making another telling.", 409)
            candidate = self._candidate(connection, source["generation_id"], decode(source["profile"]))
            connection.execute('UPDATE candidates SET usage=? WHERE id=?',
                               (encode(reusable(decode(source['usage']))), candidate))
            return remember(connection, body.operation_id, "alternate", payload,
                            {"id": source["generation_id"], "candidate_id": candidate})

    def list(self, branch_id):
        with self.database.connect() as connection:
            return generation_summaries(connection, branch_id)

    def revise_continuity(self, candidate_id, body):
        from server.continuity_revision import freeze
        from server.memory.writer_recall import digest
        payload = {'candidate_id': candidate_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'continuity_revision', payload)
            if cached is not None:
                return cached
            require_agent(connection, 'writer')
            source = one(connection, 'SELECT * FROM candidates WHERE id=?', (candidate_id,))
            require(source['status'] == 'done' and not source['accepted_node_id'],
                    'Choose a completed, unaccepted draft for continuity revision.', 409)
            require(source['attempt'] == body.expected_attempt and digest(source['output']) == body.original_sha256,
                    'This draft changed. Refresh before requesting a revision.', 409)
            generation = one(connection, 'SELECT snapshot FROM generations WHERE id=?', (source['generation_id'],))
            usage, profile = decode(source['usage']), decode(source['profile'])
            revision = freeze(decode(generation['snapshot']), profile, usage, source, body.concern)
            candidate = self._candidate(connection, source['generation_id'], profile)
            connection.execute('UPDATE candidates SET usage=? WHERE id=?',
                               (encode({**reusable(usage), 'continuity_revision': revision}), candidate))
            return remember(connection, body.operation_id, 'continuity_revision', payload,
                            {'id': source['generation_id'], 'candidate_id': candidate})

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
            node_id = insert_node(connection, target, selected_text(connection, candidate), "assistant",
                                  {"source": "generated", "candidate_id": candidate_id,
                                   "generation_id": generation["id"], "prompt_version_id": snapshot["prompt"]["id"],
                                   "opportunity_id": opportunity_id}, state)
            touch_branch(connection, target["id"], node_id)
            connection.execute("UPDATE candidate_cleanups SET status='cancelled',selected='original',error='The draft was kept before cleanup finished.' "
                               "WHERE candidate_id=? AND status='running'", (candidate_id,))
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
        from server.memory.control_state import bind_frozen_controls
        bind_frozen_controls(connection, target_id, snapshot)
        from server.memory.plan_state import bind_plan_head
        bind_plan_head(connection, target_id, snapshot.get('continuity_version_id'))
        return {**original, "id": target_id}
