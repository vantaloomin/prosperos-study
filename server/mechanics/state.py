from server.database import decode, encode


def initial_state():
    return {"scene": 1, "beat": 0, "cooldown": None, "major_events": 0, "unresolved_event": False,
            "handling_history": [], "domains": {}, "last_opportunity_id": None}


def node_state(connection, node_id):
    row = connection.execute("SELECT state FROM node_mechanics WHERE node_id=?", (node_id,)).fetchone()
    return decode(row["state"]) if row else initial_state()


def save_node_state(connection, node_id, parent_id, state=None):
    resolved = state if state is not None else node_state(connection, parent_id)
    connection.execute("INSERT INTO node_mechanics VALUES (?,?)", (node_id, encode(resolved)))
