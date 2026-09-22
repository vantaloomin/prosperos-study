from server.background.storage import bind, state_id
from server.branch_timing import BranchTimings
from server.branch_tools.curation import curation
from server.database import Database, decode, encode, identifier, many, now, one
from server.errors import require
from server.manifests import manifest_view
from server.mechanics.state import save_node_state
from server.mechanics.storage import accepted_state, mechanics_brief
from server.models import ForkCreate, MessageCreate
from server.operations import previous, remember
from server.stories import check_revision


def path_nodes(connection, head_id: str | None, *, include_removed=False) -> list[dict]:
    rows = many(connection, "WITH RECURSIVE path AS (SELECT *, 0 AS depth FROM nodes WHERE id=? "
                "UNION ALL SELECT n.*, p.depth+1 FROM nodes n JOIN path p ON p.parent_id=n.id) "
                "SELECT * FROM path ORDER BY depth DESC", (head_id,))
    nodes = [{**row, "metadata": decode(row["metadata"])} for row in rows]
    return nodes if include_removed else [node for node in nodes if not node['metadata'].get('removed')]


def insert_node(connection, branch: dict, text: str, role: str, metadata: dict, mechanics_state=None) -> str:
    node_id = identifier()
    connection.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?)",
                       (node_id, branch["story_id"], branch["head_id"], role, text,
                        branch["manifest_id"], encode(metadata), now()))
    save_node_state(connection, node_id, branch["head_id"], mechanics_state)
    background = branch.get('background_state_id') if 'background_state_id' in branch else state_id(connection, branch['id'])
    bind(connection, node_id, background, node=True)
    return node_id


def touch_branch(connection, branch_id: str, node_id: str):
    from server.memory.maintenance_intents import enqueue_accepted
    enqueue_accepted(connection, branch_id, node_id)
    connection.execute("UPDATE branches SET head_id=?,revision=revision+1,updated_at=? WHERE id=?",
                       (node_id, now(), branch_id))
    connection.execute("UPDATE stories SET updated_at=? WHERE id="
                       "(SELECT story_id FROM branches WHERE id=?)", (now(), branch_id))


def fork_boundary(connection, source: dict, body: ForkCreate) -> dict:
    if body.node_id is None:
        require(body.replacement is None, "Choose a message to edit.")
        initial = one(connection, "SELECT * FROM manifests WHERE story_id=? ORDER BY created_at LIMIT 1",
                      (source["story_id"],))
        return {**source, "head_id": None, "manifest_id": initial["id"]}
    path = {node["id"]: node for node in path_nodes(connection, source["head_id"])}
    require(body.node_id in path, "This message is not on the selected path.", 409)
    node = path[body.node_id]
    parent_id = node["parent_id"] if body.replacement is not None else node["id"]
    return {**source, "head_id": parent_id, "manifest_id": node["manifest_id"], "edited_node": node}


class Branches:
    def __init__(self, database: Database):
        self.database = database

    def detail(self, branch_id: str, timing: BranchTimings | None = None) -> dict:
        timing = timing or BranchTimings()
        with self.database.connect() as connection:
            branch = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
            branch['curation'] = curation(connection, branch_id)
            timing.mark("lookup")
            messages = path_nodes(connection, branch["head_id"], include_removed=True)
            timing.mark("path")
            attachments = manifest_view(connection, branch["manifest_id"])
            timing.mark("attachments")
            mechanics = mechanics_brief(connection, branch)
            timing.mark("mechanics")
        timing.mark("close")
        return {**branch, "messages": messages, "attachments": attachments, "mechanics": mechanics}

    def append(self, branch_id: str, body: MessageCreate) -> dict:
        payload = {"branch_id": branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "message", payload)
            if cached is not None:
                return cached
            branch = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
            check_revision(branch, body.expected_revision)
            require(not body.opportunity_id or body.role in {"narrator", "assistant"},
                    "Only completed narration can accept a prepared beat. Dialogue and OOC notes cannot advance it.")
            state = accepted_state(connection, branch, body.opportunity_id)
            from server.text_edits.documents import consume_document
            text = consume_document(connection, branch, 'author-note' if body.role == 'ooc' else 'composer', body.expected_document_version, body.text)
            node_id = insert_node(connection, branch, text, body.role,
                                  {"source": "manual", "opportunity_id": body.opportunity_id}, state)
            touch_branch(connection, branch_id, node_id)
            return remember(connection, body.operation_id, "message", payload,
                            {"node_id": node_id, "branch_id": branch_id})

    def fork(self, branch_id: str, body: ForkCreate) -> dict:
        payload = {"branch_id": branch_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "fork", payload)
            if cached is not None:
                return cached
            source = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
            check_revision(source, body.expected_revision)
            boundary = fork_boundary(connection, source, body)
            boundary['background_state_id'] = state_id(connection, boundary['head_id'], node=True)
            return self._insert_fork(connection, source, boundary, body, payload)

    @staticmethod
    def _insert_fork(connection, source, boundary, body, payload):
        branch_id = identifier()
        head_id = boundary["head_id"]
        if body.replacement is not None:
            head_id = insert_node(connection, boundary, body.replacement,
                                  boundary["edited_node"]["role"],
                                  {"source": "manual_edit", "replaces": body.node_id})
        connection.execute("INSERT INTO branches VALUES (?,?,?,?,?,?,?,0,?,?)",
                           (branch_id, source["story_id"], body.name, head_id, boundary["manifest_id"],
                            source["id"], body.node_id, now(), now()))
        bind(connection, branch_id, boundary['background_state_id'])
        from server.memory.control_state import fork_controls
        fork_controls(connection, source, branch_id, head_id)
        from server.memory.plan_state import fork_plans
        fork_plans(connection, source, branch_id, head_id)
        if body.replacement is not None:
            from server.memory.maintenance_intents import enqueue_accepted
            enqueue_accepted(connection, branch_id, head_id)
        return remember(connection, body.operation_id, "fork", payload, {"branch_id": branch_id})
