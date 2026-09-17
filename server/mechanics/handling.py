from server.mechanics.table_engine import qualitative

DICE = {1: 4, 2: 6, 3: 8, 4: 10, 5: 20}


def modifiers(attempt, settings, state, draws):
    domain_key = f"{attempt.actor.casefold()}:{attempt.domain.casefold()}"
    level = state["domains"].get(domain_key, attempt.level) if attempt.domain else 0
    parts = []
    if settings.proficiency and level:
        value = draws.die(DICE[abs(level)], "handling", "proficiency")
        parts.append({"kind": "proficiency", "value": value if level > 0 else -value})
    if settings.fracture and attempt.fractured:
        parts.append({"kind": "fracture", "value": -draws.die(6, "handling", "fracture")})
    if settings.preparation and attempt.prepared:
        parts.append({"kind": "preparation", "value": draws.die(4, "handling", "preparation")})
    return parts, domain_key, level


def select_band(definition, total):
    if total < 1:
        return definition["low_overflow"]
    if total > definition["die"]:
        return definition["high_overflow"]
    return next(row for row in definition["rows"] if row["low"] <= total <= row["high"])


def pressure_total(total, state, enabled):
    recent = state["handling_history"][-2:]
    capped = enabled and len(recent) == 2 and all(value >= 81 for value in recent) and total > 75
    return (75 if capped else total), capped


def progression(attempt, band, settings, state, domain_key, level):
    move = band.get("domain_move", 0)
    if not settings.domain_progression or not attempt.domain or not move:
        return None
    updated = max(-5, min(5, level + move))
    state["domains"][domain_key] = updated
    return {"actor": attempt.actor, "domain": attempt.domain, "before": level, "after": updated}


def texture_keys(band, carrier):
    keys = []
    if band["id"] in {"disaster", "poorly", "sideways", "shift"}:
        keys.append("small-wrongs")
    if band["id"] in {"well", "critical"}:
        keys.append("small-rights")
    tags = [tag for item in carrier.get("chain", []) for tag in item["row"]["tags"]]
    return keys + [key for tag, key in [("person", "who-shows-up"), ("timing", "interruptions")] if tag in tags]


def followups(band, tables, draws, settings):
    sub = tables.resolve(band["child"], draws, "handling") if settings.subresults and band["child"] else {}
    if sub.get("status") == "no_event":
        return sub, {}, {}
    carrier = tables.resolve("vector", draws, "handling") if settings.carriers else {}
    textures = {}
    if settings.textures:
        for key in texture_keys(band, carrier):
            table_id = settings.texture_tables.get(key)
            if table_id:
                textures[key] = tables.resolve(table_id, draws, f"texture:{key}")
    return sub, carrier, textures


def handling(attempt, tables, draws, settings, state):
    base = tables.face("handling", draws, "handling", settings.subresults)
    if base is None:
        return {"status": "skipped", "reason": "Handling has no enabled outcomes."}
    parts, domain_key, level = modifiers(attempt, settings, state, draws)
    uncapped = base["face"] + sum(part["value"] for part in parts)
    total, capped = pressure_total(uncapped, state, settings.pressure_cap)
    band = select_band(tables.definition("handling"), total)
    detail = {"raw": base["face"], "modifiers": parts, "uncapped": uncapped, "total": total, "capped": capped,
              "domain_level": level, "attempt": attempt.model_dump()}
    if not usable_band(band, tables, settings):
        return {**detail, "status": "suppressed", "reason": "Modified result is disabled or has no enabled dependency."}
    if band.get("kind") == "no_event":
        return {**detail, "status": "no_event", "reason": "Intentional no-event result; the attempt gets no mechanical outcome."}
    sub, carrier, textures = followups(band, tables, draws, settings)
    if sub.get("status") == "no_event":
        return {**detail, "status": "no_event", "subresult": sub, "reason": "The child no-event result cancels this outcome."}
    state["handling_history"] = [*state["handling_history"], total][-2:]
    move = progression(attempt, band, settings, state, domain_key, level)
    return {**detail, "status": "resolved", "band": band, "subresult": sub, "carrier": carrier,
            "textures": textures, "domain_change": move}


def usable_band(band, tables, settings):
    if band is None or band["id"] in settings.excluded_rows.get("handling", []):
        return False
    return not settings.subresults or not band["child"] or bool(tables.available(band["child"]))


def handling_instruction(result):
    if result.get("status") != "resolved":
        return None
    band = result["band"]
    return {"action": result["attempt"]["action"], "actor": result["attempt"]["actor"],
            "outcome": {"label": band["label"], "instruction": band["instruction"]},
            "shape": qualitative(result["subresult"]), "carrier": qualitative(result["carrier"]),
            "textures": {key: qualitative(value) for key, value in result["textures"].items()}}
