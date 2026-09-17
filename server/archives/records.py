from server.database import many


def related_rows(connection, table, field, ids):
    rows = []
    values = sorted(ids)
    for offset in range(0, len(values), 500):
        chunk = values[offset:offset + 500]
        placeholders = ",".join("?" for _ in chunk)
        rows.extend(many(connection, f"SELECT * FROM {table} WHERE {field} IN ({placeholders}) ORDER BY rowid", chunk))
    return rows
