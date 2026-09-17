from server.errors import require


class TableSet:
    def __init__(self, versions, settings):
        self.versions = versions
        self.settings = settings
        self.used = {}

    def available(self, table_id, follow_children=True, trail=()):
        if table_id in self.settings.disabled_tables or table_id not in self.versions:
            return []
        require(table_id not in trail and len(trail) < 8, "Table dependencies form a cycle or are too deep.")
        rows = sorted(self.versions[table_id]["definition"]["rows"], key=lambda row: row["low"])
        excluded = self.settings.excluded_rows.get(table_id, [])
        eligible = [row for row in rows if row["id"] not in excluded]
        if follow_children:
            eligible = [row for row in eligible if not row["child"]
                        or self.available(row["child"], True, (*trail, table_id))]
        return eligible

    def odds(self, table_id, follow_children=True):
        eligible = {row["id"] for row in self.available(table_id, follow_children)}
        rows = self.versions[table_id]["definition"]["rows"]
        total = sum(row["high"] - row["low"] + 1 for row in rows if row["id"] in eligible)
        return [{"id": row["id"], "enabled": row["id"] in eligible,
                 "percent": 100 * (row["high"] - row["low"] + 1) / total
                 if row["id"] in eligible else 0} for row in rows]

    def definition(self, table_id):
        self.used[table_id] = self.versions[table_id]
        return self.versions[table_id]["definition"]

    def face(self, table_id, draws, stream, follow_children=True):
        rows = self.available(table_id, follow_children)
        if not rows:
            return None
        self.definition(table_id)
        weight = sum(row["high"] - row["low"] + 1 for row in rows)
        draw = draws.die(weight, stream, table_id)
        for row in rows:
            width = row["high"] - row["low"] + 1
            if draw <= width:
                return {"table_id": table_id, "face": row["low"] + draw - 1, "row": row}
            draw -= width
        raise AssertionError("Validated table has no result")

    def resolve(self, table_id, draws, stream, follow_children=True):
        chain = []
        while table_id:
            selected = self.face(table_id, draws, stream, follow_children)
            if selected is None:
                return {"status": "skipped", "reason": "No enabled outcomes remain.", "chain": chain}
            chain.append(selected)
            row = selected["row"]
            if row["kind"] == "no_event":
                return {"status": "no_event", "reason": "Intentional no-event result; no replacement.", "chain": chain}
            table_id = row["child"] if follow_children else None
        return {"status": "resolved", "chain": chain, "major": any(item["row"]["major"] for item in chain)}


def qualitative(result):
    if result.get("status") != "resolved":
        return None
    return [{"label": item["row"]["label"], "instruction": item["row"]["instruction"]}
            for item in result["chain"]]
