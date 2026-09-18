from typing import Literal

from pydantic import Field

from server.database import decode, encode, identifier, many, now, one
from server.errors import require
from server.memory.side_archive import permitted_sources
from server.memory.side_search import SourceArchive
from server.models import Input
from server.operations import previous, remember
from server.side_context import initial_sources, side_snapshot


class SideThreadCreate(Input):
    name: str = Field(default="A conversation beside the story", min_length=1, max_length=120)


class SideQuestion(Input):
    operation_id: str = Field(min_length=8, max_length=100)
    branch_id: str
    expected_revision: int
    question: str = Field(min_length=1, max_length=30000)
    profile_ids: list[str] = Field(default_factory=list, max_length=4)
    compare_branch_ids: list[str] = Field(default_factory=list, max_length=4)
    disclosure: Literal["spoiler-conscious", "full-disclosure"] = "spoiler-conscious"
    max_reads: int = Field(default=3, ge=0, le=4)


def reply_view(row):
    profile = decode(row["profile"])
    profile.pop("credential_ref", None)
    usage = [{key: value for key, value in item.items() if key != 'content'} for item in decode(row['usage'])]
    return {**row, "profile": profile, "usage": usage, "coverage": decode(row["coverage"])}


class SideConversations:
    def __init__(self, database):
        self.database = database

    def threads(self, story_id):
        with self.database.connect() as connection:
            return many(connection, "SELECT * FROM side_threads WHERE story_id=? ORDER BY created_at DESC", (story_id,))

    def create_thread(self, story_id, name):
        with self.database.connect(write=True) as connection:
            one(connection, "SELECT id FROM stories WHERE id=?", (story_id,))
            thread_id = identifier()
            connection.execute("INSERT INTO side_threads VALUES (?,?,?,?)", (thread_id, story_id, name, now()))
            return {"id": thread_id}

    def detail(self, thread_id):
        with self.database.connect() as connection:
            thread = one(connection, "SELECT * FROM side_threads WHERE id=?", (thread_id,))
            turns = many(connection, "SELECT * FROM side_turns WHERE thread_id=? ORDER BY created_at", (thread_id,))
            return {**thread, "turns": [self.turn_view(connection, turn) for turn in turns]}

    @staticmethod
    def turn_view(connection, turn):
        snapshot = decode(turn["snapshot"])
        replies = many(connection, "SELECT * FROM side_replies WHERE turn_id=? ORDER BY rowid", (turn["id"],))
        public = {key: value for key, value in snapshot.items() if key not in {"sources", "conversation", "retrieval"}}
        if snapshot.get("retrieval"):
            public["retrieval"] = {key: snapshot["retrieval"][key] for key in ("version", "input_allowance", "conversation_coverage")}
        return {**turn, "snapshot": public,
                "source_count": len(permitted_sources(snapshot)), "replies": [reply_view(row) for row in replies]}

    def ask(self, thread_id, body):
        payload = {"thread_id": thread_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "side-question", payload)
            if cached is not None:
                return cached
            thread = one(connection, "SELECT * FROM side_threads WHERE id=?", (thread_id,))
            pending = connection.execute("SELECT 1 FROM side_replies r JOIN side_turns t ON r.turn_id=t.id "
                                         "WHERE t.thread_id=? AND r.status IN ('queued','running')", (thread_id,)).fetchone()
            require(pending is None, "Finish or stop this conversation's current replies before asking another question.", 409)
            snapshot, profiles = side_snapshot(connection, thread, body)
            starts = [initial_sources(snapshot, profile) for profile in profiles]
            snapshot["initial_source_ids"] = starts[0] if all(starts) else []
            turn_id = identifier()
            connection.execute("INSERT INTO side_turns VALUES (?,?,?,?,NULL,?)",
                               (turn_id, thread_id, body.question, encode(snapshot), now()))
            replies = [self.new_reply(connection, turn_id, profile) for profile in profiles]
            if len(replies) == 1:
                connection.execute("UPDATE side_turns SET selected_reply_id=? WHERE id=?", (replies[0], turn_id))
            return remember(connection, body.operation_id, "side-question", payload, {"id": turn_id, "reply_ids": replies})

    @staticmethod
    def new_reply(connection, turn_id, profile):
        reply_id = identifier()
        connection.execute("INSERT INTO side_replies (id,turn_id,profile,status,updated_at) VALUES (?,?,?,?,?)",
                           (reply_id, turn_id, encode(profile), "queued", now()))
        return reply_id

    def select(self, reply_id):
        with self.database.connect(write=True) as connection:
            reply = one(connection, "SELECT * FROM side_replies WHERE id=?", (reply_id,))
            require(reply["status"] == "done", "Choose a completed reply.", 409)
            connection.execute("UPDATE side_turns SET selected_reply_id=? WHERE id=?", (reply_id, reply["turn_id"]))
        return {"selected": reply_id}

    def sources(self, turn_id):
        with self.database.connect() as connection:
            turn = one(connection, "SELECT snapshot FROM side_turns WHERE id=?", (turn_id,))
            return decode(turn["snapshot"])["sources"]


    def source_archive(self, turn_id):
        with self.database.connect() as connection:
            row = one(connection, 'SELECT snapshot FROM side_turns WHERE id=?', (turn_id,))
            return SourceArchive(decode(row['snapshot']))

    def search_sources(self, turn_id, query, offset):
        return self.source_archive(turn_id).search(query, offset)

    def read_source(self, turn_id, source_id, offset, length):
        archive = self.source_archive(turn_id)
        require(source_id in archive.by_id, 'This source is not available in this frozen disclosure scope.', 404)
        return archive.read([{'id': source_id, 'offset': offset, 'length': length}])[0]

    def request_inputs(self, reply_id, index):
        with self.database.connect() as connection:
            reply = one(connection, 'SELECT r.usage,t.snapshot FROM side_replies r JOIN side_turns t ON r.turn_id=t.id WHERE r.id=?', (reply_id,))
            usage = decode(reply['usage'])
            require(0 <= index < len(usage), 'This request receipt is unavailable.', 404)
            require('content' in usage[index], 'This older reply does not store a per-request input receipt.', 404)
            return {**usage[index], 'prompt': decode(reply['snapshot'])['prompt']['template']}
