from server.database import decode, encode, identifier, now, one
from server.errors import require
from server.scenes.catalog import DRAFT_KEYS, PLAN_KEYS, SCENE_KEYS
from server.scenes.continuity_catalog import CONTINUITY_KEYS
from server.scenes.models import SceneState
from server.scenes.patch_catalog import PATCH_KEYS
from server.scenes.switches import enabled_steps


def run_record(connection, run_id):
    row = one(connection, "SELECT * FROM scene_runs WHERE id=?", (run_id,))
    return {**row, "snapshot": decode(row["snapshot"]), "state": SceneState.model_validate(decode(row["state"])).model_dump()}


def selected_result(connection, run, key):
    if key == "scene-beats" and run["state"].get("beat_edit"):
        return run["state"]["beat_edit"]
    job_id = run["state"]["selections"].get(key)
    if not job_id:
        return None
    return decode(one(connection, "SELECT result FROM scene_jobs WHERE id=?", (job_id,))["result"])


def next_step(run):
    selected = run["state"]["selections"]
    keys = stage_keys(run) if run["state"]["gate_a"] else planning_keys(run)
    return next((key for key in keys if key not in selected), None)


def planning_keys(run):
    return enabled_steps(run, PLAN_KEYS if run["snapshot"]["propose_options"] else PLAN_KEYS[1:])


def stage_keys(run):
    keys = planning_keys(run) + enabled_steps(run, DRAFT_KEYS)
    return [key for key in keys if key != "scene-dialogue" or run["snapshot"].get("dialogue_split", False)]


def dependency_keys(run, key):
    if key in CONTINUITY_KEYS:
        patches = [step for step in PATCH_KEYS if step != 'scene-dialogue-patch' or run['snapshot'].get('dialogue_split', False)]
        needed = patches if (run['state'].get('gate_b') or {}).get('items') else []
        return stage_keys(run) + ['scene-triage'] + needed
    if key in PATCH_KEYS:
        patches = [step for step in PATCH_KEYS if step != 'scene-dialogue-patch' or run['snapshot'].get('dialogue_split', False)]
        require(key in patches, 'Split dialogue is not enabled for this scene.')
        return stage_keys(run) + ['scene-triage'] + patches[:patches.index(key)]
    if key in {'scene-triage', 'scene-verify'}:
        return stage_keys(run) + (['scene-triage'] if key == 'scene-verify' else [])
    allowed = stage_keys(run)
    require(key in allowed, 'This stage is not enabled for this scene.')
    return allowed[:allowed.index(key)]


def reviewed_state(state):
    return {'selections': {key: value for key, value in state['selections'].items() if key in PLAN_KEYS + DRAFT_KEYS},
            'option_id': state.get('option_id'), 'beat_edit': state.get('beat_edit'), 'gate_a': state.get('gate_a')}


def planning_selections(run):
    return {key: value for key, value in run["state"]["selections"].items() if key in PLAN_KEYS}


def upstream(run, key):
    earlier = SCENE_KEYS[:SCENE_KEYS.index(key)]
    state = run["state"]
    result = {"selections": {step: value for step, value in state["selections"].items() if step in earlier},
              "option_id": state.get("option_id") if "scene-options" in earlier else None,
              "beat_edit": state.get("beat_edit") if "scene-beats" in earlier else None}
    if key not in PLAN_KEYS:
        result["gate_a"] = state["gate_a"]
    if key in PATCH_KEYS + CONTINUITY_KEYS:
        result.update({name: state[name] for name in ('gate_b', 'triage_edits', 'verifications', 'patch_round', 'repair_selections')})
    return result


def require_step(run, key):
    require(key not in run["snapshot"].get("disabled_steps", []), "This stage was disabled when the scene began. Start a new scene to change its workflow.", 409)
    approved = bool(run["state"]["gate_a"])
    require(not (key in PLAN_KEYS and approved), "This plan is approved. Start another plan to explore changes.", 409)
    require(key in PLAN_KEYS or approved, "Approve the plan before drafting or checking its prose.", 409)
    require(key not in PATCH_KEYS + CONTINUITY_KEYS or bool(run['state'].get('gate_b')), 'Approve the revision package before patching or recording continuity.', 409)
    earlier = dependency_keys(run, key)
    require(all(step in run["state"]["selections"] for step in earlier), "Choose the preceding stage results first.", 409)


def choose_state(run, job, option_id):
    state = run["state"]
    require_step(run, job["step"])
    require(decode(job["snapshot"])["upstream"] == upstream(run, job["step"]),
            "This result belongs to an earlier plan. Generate again using the current selections.", 409)
    if job['step'] == 'scene-verify':
        require(option_id is None, 'Only the options stage accepts an option choice.')
        state['verifications'][decode(job['snapshot'])['item_id']] = job['id']
        state['triage_edits'].pop(decode(job['snapshot'])['item_id'], None)
        state['gate_b'] = None
        clear_patches(state)
        return state
    if job["step"] == "scene-options":
        options = decode(job["result"])["options"]
        require(option_id in {item["id"] for item in options}, "Choose an option from this result.")
        state["option_id"] = option_id
    else:
        require(option_id is None, "Only the options stage accepts an option choice.")
    keep = SCENE_KEYS[:SCENE_KEYS.index(job["step"]) + 1]
    state["selections"] = {key: value for key, value in state["selections"].items() if key in keep}
    state["selections"][job["step"]] = job["id"]
    if job['step'] not in PATCH_KEYS + CONTINUITY_KEYS:
        state.update(triage_edits={}, verifications={}, gate_b=None)
        clear_patches(state)
    if job["step"] in {"scene-options", "scene-beats"}:
        state["beat_edit"] = None
    return state


def clear_patches(state):
    state['selections'] = {key: value for key, value in state['selections'].items() if key not in PATCH_KEYS + CONTINUITY_KEYS}
    state.update(patch_round=0, repair_selections={})


def save_decision(connection, run, kind, payload, state):
    state = SceneState.model_validate(state).model_dump()
    revision = run["revision"] + 1
    connection.execute("INSERT INTO scene_decisions VALUES (?,?,?,?,?,?)",
                       (identifier(), run["id"], revision, kind, encode(payload), now()))
    connection.execute("UPDATE scene_runs SET revision=?,state=? WHERE id=?", (revision, encode(state), run["id"]))
    return {"id": run["id"], "revision": revision, "state": state}
