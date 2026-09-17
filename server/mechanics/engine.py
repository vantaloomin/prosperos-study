from copy import deepcopy

from server.mechanics.handling import handling, handling_instruction
from server.mechanics.randomness import ALGORITHM, Draws
from server.mechanics.table_engine import TableSet, qualitative


def eligible(beat):
    if not beat.completed:
        return "The narrative beat is not complete."
    if beat.waiting_for_player:
        return "A decision or action still belongs to the player."
    if beat.protected:
        return "The director protected this moment."
    return None


def begin_beat(state, beat, settings):
    updated = deepcopy(state)
    if beat.new_scene:
        updated.update(scene=state["scene"] + 1, beat=0, cooldown=settings.cooldown,
                       major_events=0, unresolved_event=False, handling_history=[])
    if updated["cooldown"] is None:
        updated["cooldown"] = settings.cooldown
    if beat.resolves_event:
        updated["unresolved_event"] = False
    updated["beat"] += 1
    return updated


def event_outcome(beat, tables, draws, settings, state, manual):
    if beat.family == "none":
        return {"status": "skipped", "reason": "No event family selected."}
    enabled = getattr(settings, beat.family.replace("-", "_"))
    if not enabled and not manual:
        return {"status": "skipped", "reason": "This event family is off."}
    if state["unresolved_event"]:
        return {"status": "skipped", "reason": "The previous generated event is still unresolved."}
    if not tables.available(beat.family):
        return {"status": "skipped", "reason": "No enabled outcomes remain in this event family."}
    return consult_event(beat.family, tables, draws, settings, state, manual)


def consult_event(family, tables, draws, settings, state, manual):
    if not manual and settings.chance == 0:
        return {"status": "skipped", "reason": "Activation is set to zero; no draw or cooldown change."}
    if not manual and state["cooldown"] > 0:
        state["cooldown"] -= 1
        return {"status": "cooldown", "reason": "An eligible beat of breathing room; no draw."}
    if not manual and draws.die(100, "events", "activation") > settings.chance:
        return {"status": "miss", "reason": "Activation missed; the cooldown is not restarted."}
    result = tables.resolve(family, draws, "events")
    state["cooldown"] = settings.cooldown
    if result.get("major") and state["major_events"] >= settings.major_limit:
        return {**result, "status": "suppressed", "reason": "The scene's major-disruption limit is reached; no replacement."}
    if result["status"] == "resolved":
        state["major_events"] += int(result["major"])
        state["unresolved_event"] = result["chain"][-1]["row"]["kind"] != "progress"
    return result


def extra_outcomes(beat, tables, draws, settings, manual):
    results = {}
    for table_id in dict.fromkeys(beat.extras):
        if manual or table_id in settings.enabled_extras:
            results[table_id] = tables.resolve(table_id, draws, f"extra:{table_id}")
        else:
            results[table_id] = {"status": "skipped", "reason": "This optional table is off."}
    return results


def resolve_beat(versions, settings, beat, before, seed, manual=False):
    tables, draws = TableSet(versions, settings), Draws(seed)
    blocked = eligible(beat) or disabled_reason(beat, settings, tables, manual)
    after = deepcopy(before) if blocked else begin_beat(before, beat, settings)
    result = {"beat": beat.model_dump(), "manual": manual, "algorithm": ALGORITHM, "seed": seed,
              "before": before, "after": after, "settings": settings.model_dump(), "eligibility": blocked,
              "event": {}, "handling": {}, "extras": {}, "writer": {}}
    if not blocked:
        result["event"] = event_outcome(beat, tables, draws, settings, after, manual)
        if beat.attempt and (settings.handling or manual):
            result["handling"] = handling(beat.attempt, tables, draws, settings, after)
        result["extras"] = extra_outcomes(beat, tables, draws, settings, manual)
        result["writer"] = writer_instructions(result)
    return {**result, "draws": draws.log, "tables": tables.used}


def disabled_reason(beat, settings, tables, manual):
    event = event_enabled(beat, settings, tables)
    attempt = beat.attempt is not None and settings.handling and tables.available("handling", settings.subresults)
    extra = any(key in settings.enabled_extras and tables.available(key) for key in beat.extras)
    if not manual and not (event or attempt or extra):
        return "All selected mechanics are disabled; no state changes."
    return None


def event_enabled(beat, settings, tables):
    return beat.family != "none" and settings.chance > 0 and getattr(settings, beat.family.replace("-", "_")) \
        and bool(tables.available(beat.family))


def writer_instructions(result):
    instructions = {"event": qualitative(result["event"]), "handling": handling_instruction(result["handling"]),
                    "extras": {key: qualitative(value) for key, value in result["extras"].items()
                               if value.get("status") == "resolved"}}
    return {**instructions, "constraints": "Use only the resolved qualitative instructions. Match established genre, "
            "world rules and scene scope. Never mention rolls or mechanical totals. Do not replace a no-event result. "
            "Only resolve the specifically attempted action; leave the player's unchosen actions, consent, decisions "
            "and private feelings to the player. External pressure presents a choice; it cannot take that choice."}
