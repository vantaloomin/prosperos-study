import hashlib

from server.database import decode, encode, now
from server.errors import require


def fingerprint(kind: str, payload: dict) -> str:
    return hashlib.sha256(encode([kind, payload]).encode()).hexdigest()


def previous(connection, operation_id: str, kind: str, payload: dict):
    row = connection.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
    if row is None:
        return None
    require(row["fingerprint"] == fingerprint(kind, payload),
            "This action identifier was already used for different input.", 409)
    return decode(row["result"])


def remember(connection, operation_id: str, kind: str, payload: dict, result: dict):
    connection.execute("INSERT INTO operations VALUES (?,?,?,?,?)",
                       (operation_id, kind, fingerprint(kind, payload), encode(result), now()))
    return result
