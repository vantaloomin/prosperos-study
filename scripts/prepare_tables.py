"""Transcribe the reviewed planning tables and original oracle into runtime data."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENT_IDS = ["narrative-push", "momentum", "micro-friction", "complication", "transition-pressure",
             "dramatic-turn", "anomaly", "encounter", "atmosphere", "obstacle", "direct-challenge",
             "contact", "interest-point", "find", "clue"]
CHILDREN = {
    "narrative-push": {1: "momentum", 16: "micro-friction", 51: "complication",
                       76: "transition-pressure", 88: "dramatic-turn", 96: "anomaly"},
    "encounter": {2: "atmosphere", 5: "obstacle", 6: "direct-challenge", 7: "contact",
                  8: "interest-point", 9: "find", 10: "clue"},
}


def row(key, low, high, label, instruction, **extra):
    return {"id": key, "low": low, "high": high, "label": label, "instruction": instruction,
            "kind": "event", "child": None, "major": False, "tags": [], **extra}


def document(key, name, die, rows, purpose="event", **extra):
    return {"id": key, "name": name, "die": die, "rows": rows, "purpose": purpose,
            "note": "", "low_overflow": None, "high_overflow": None, **extra}


def event_row(table_id, cells):
    bounds = [int(part) for part in cells[0].split("-")]
    low, high = bounds[0], bounds[-1]
    kind = {"No new event": "no_event", "Unremarkable Progress": "progress"}.get(cells[1], "event")
    child = CHILDREN.get(table_id, {}).get(low)
    return row(f"result-{low}", low, high, cells[1], cells[2], kind=kind, child=child,
               major=child in {"dramatic-turn", "anomaly"})


def events():
    tables = []
    current = None
    source = ROOT / "planning" / "narrative-event-tables.md"
    for line in source.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^#{2,3} (.+), d(\d+)", line)
        if heading:
            key = EVENT_IDS[len(tables)]
            name = re.sub(r"^\d+\. ", "", heading[1])
            current = document(key, name, int(heading[2]), [])
            current["note"] = "Proposed completion of the missing Dramatic Turn subtable." if key == "dramatic-turn" else "Genre-neutral adaptation; original probabilities preserved."
            tables.append(current)
        if current and re.match(r"^\| \d", line):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            current["rows"].append(event_row(current["id"], cells))
    assert len(tables) == 15
    return tables


def core_table(key, content):
    entries = content["entries"]
    rows = [row(f"result-{i}", i, i, text, text) for i, text in enumerate(entries, 1)]
    if key == "vector":
        for item in rows:
            item["tags"] = {2: ["person"], 3: ["person"], 6: ["person"], 8: ["timing"]}.get(item["low"], [])
    return document(key, key.replace("-", " ").title(), len(entries),
                    rows,
                    "carrier" if key == "vector" else "extra", note=content.get("note", ""))


def handling_tables(content):
    bands = [row(band["key"], band["min"], band["max"], band["label"], band["text"],
                 child=f"handling-{band['sub']}") for band in content["bands"]]
    parent = document("handling", "Handling an attempted action", 100, bands, "handling")
    for field, key, move in [("low_overflow", "catastrophe", -1), ("high_overflow", "legend", 1)]:
        source = content["overflow"][key]
        parent[field] = {"id": key, "label": source["label"],
                         "instruction": source["text"].split(". ", 1)[1].split(" The scribe")[0],
                         "child": f"handling-{source['sub']}", "domain_move": move}
    children = [document(f"handling-{key}", f"Handling · {key}", table["die"],
                         [row(f"result-{entry[0]}", *entry) for entry in table["entries"]], "handling")
                for key, table in content["sub"].items()]
    return [parent, *children]


def originals():
    tables = []
    for path in sorted((ROOT / "zz_Example" / "tables" / "core").glob("*.json")):
        content = json.loads(path.read_text(encoding="utf-8"))
        if path.stem == "handling":
            tables.extend(handling_tables(content))
        elif path.stem == "automaton":
            for part in ["A", "B"]:
                tables.append(core_table(f"automaton-{part.lower()}", {"entries": content[part]}))
        else:
            tables.append(core_table(path.stem, content))
    return tables


def main():
    tables = events() + originals()
    destination = ROOT / "server" / "mechanics" / "defaults.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(tables, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Prepared {len(tables)} tables in {destination}")


if __name__ == "__main__":
    main()
