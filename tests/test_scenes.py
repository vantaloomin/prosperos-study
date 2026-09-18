import asyncio
import json
from contextlib import nullcontext
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

from server.database import decode, encode, one
from server.providers.events import ProviderEvent
from tests.prompt_fixtures import saved_prompt
from tests.test_history import append
from tests.test_profiles import make_profile

PLAN = {"summary": "Fixture plan, no model call.", "beats": [{"id": "beat-1", "title": "The letter",
        "development": "Wren shows the unopened envelope.", "decision": "Will the player inspect it?",
        "constraints": "Do not open it on the player's behalf."}], "ending": "Wait for the player's decision."}


class SceneProvider:
    def __init__(self):
        self.calls = []

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        context = decode(content)
        outputs = {
            "scene-options": {"summary": "Fixture options, no model call.", "options": [
                {"id": key, "title": f"Approach {key}", "direction": f"Proposed approach {key}.",
                 "opens": "A conversation", "closes": "Immediate departure"} for key in "ABCD"]},
            "scene-beats": deepcopy(PLAN),
            "scene-brief": {"summary": "Fixture continuity only.", "facts": [{"source_id": context["sources"][0]["id"],
                            "quote": context["sources"][0]["text"], "relevance": "Keep the letter sealed."}], "unknowns": ["Who sent it?"]},
        }
        yield ProviderEvent(text=encode(outputs[context["stage"]]), done=True)


class InvalidSceneProvider:
    async def generate(self, _profile, _prompt, _content):
        yield ProviderEvent(text='{"summary":"Invalid brief","facts":[{"source_id":"foreign:secret","quote":"invented",'
                                '"relevance":"unsupported"}],"unknowns":[]}', done=True)


class WaitingSceneProvider:
    async def generate(self, _profile, _prompt, _content):
        yield ProviderEvent(text="Partial fixture plan.")
        await asyncio.sleep(60)


def legacy_scene_creation():
    """Insert a pre-consolidation scene, without changing immutable saved records."""
    from server.scenes.service import create_snapshot
    def legacy_snapshot(*args):
        snapshot = create_snapshot(*args)
        snapshot.pop('workflow_version', None)
        return snapshot
    return patch('server.scenes.service.create_snapshot', legacy_snapshot)


def setup_plan(client, story, options=True, dialogue=False, *, legacy=True):
    make_profile(client, "Planner", primary=True)
    provider = SceneProvider()
    client.app.state.scene_runner.provider = provider
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    append(client, story["branch_id"], "Wren waits beside the sealed letter.", revision)
    body = {"operation_id": uuid4().hex, "expected_revision": revision + 1, "title": "The letter", "direction": "Consider the letter.",
            "propose_options": options, "dialogue_split": dialogue}
    route = f"/api/branches/{story['branch_id']}/scenes"
    with legacy_scene_creation() if legacy else nullcontext():
        response = client.post(route, json=body)
    assert response.status_code == 201, response.text
    assert client.post(route, json=body).json() == response.json()
    return response.json()["id"], provider


def get_plan(client, run_id):
    response = client.get(f"/api/scenes/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def finish_plan(client, run_id):
    with client.stream("GET", f"/api/scenes/{run_id}/events") as response:
        records = [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]
    return records[-1]


def run_stage(client, run_id, key, profiles=None, **targets):
    run = get_plan(client, run_id)
    body = {"expected_revision": run["revision"], "key": key, "profile_ids": profiles or [], **targets}
    preview = client.post(f"/api/scenes/{run_id}/preview", json=body)
    assert preview.status_code == 200, preview.text
    request = {**body, "preview_hash": preview.json()["preview_hash"], "operation_id": uuid4().hex}
    response = client.post(f"/api/scenes/{run_id}/stages", json=request)
    assert response.status_code == 201, response.text
    assert client.post(f"/api/scenes/{run_id}/stages", json=request).json() == response.json()
    run = finish_plan(client, run_id)
    return [job for job in run["jobs"] if job["id"] in response.json()["job_ids"]]


def decide(client, run_id, kind, payload=None):
    body = {"expected_revision": get_plan(client, run_id)["revision"], "operation_id": uuid4().hex, **(payload or {})}
    response = client.post(f"/api/scenes/{run_id}/{kind}", json=body)
    assert response.status_code == 200, response.text
    assert client.post(f"/api/scenes/{run_id}/{kind}", json=body).json() == response.json()
    return response.json()


def choose(client, run_id, job, option=None):
    return decide(client, run_id, "choose", {"job_id": job["id"], "option_id": option})


def ready_plan(client, story):
    run_id, provider = setup_plan(client, story)
    options = run_stage(client, run_id, "scene-options")[0]
    choose(client, run_id, options, "B")
    beats = run_stage(client, run_id, "scene-beats")[0]
    choose(client, run_id, beats)
    brief = run_stage(client, run_id, "scene-brief")[0]
    choose(client, run_id, brief)
    return run_id, provider


def test_plan_gates_preserve_story_and_require_deliberate_choices(client, story):
    run_id, provider = setup_plan(client, story)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    assert client.post(f"/api/scenes/{run_id}/preview", json={"expected_revision": 0, "key": "scene-brief"}).status_code == 409
    options = run_stage(client, run_id, "scene-options")[0]
    assert options["status"] == "done" and get_plan(client, run_id)["next_step"] == "scene-options"
    choose(client, run_id, options, "C")
    beats = run_stage(client, run_id, "scene-beats")[0]
    assert decode(beats["snapshot"]["content"])["chosen_option"]["id"] == "C"
    choose(client, run_id, beats)
    brief = run_stage(client, run_id, "scene-brief")[0]
    assert decode(brief["snapshot"]["content"])["proposed_beats"] == PLAN
    choose(client, run_id, brief)
    result = decide(client, run_id, "approve", {"note": "Leave the player's choice open."})
    assert result["state"]["gate_a"]["note"] == "Leave the player's choice open."
    assert len(provider.calls) == 3
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert client.get(f"/api/branches/{story['branch_id']}/generations").json() == []
    assert client.post(f"/api/scenes/{run_id}/preview", json={"expected_revision": result["revision"], "key": "scene-beats"}).status_code == 409
    assert [entry["kind"] for entry in get_plan(client, run_id)["decisions"]] == ["request", "choose", "request", "choose", "request", "choose", "approve"]


def test_comparisons_freeze_inputs_and_earlier_choices_invalidate_downstream(client, story):
    run_id, provider = setup_plan(client, story)
    profiles = [make_profile(client, name)["profile_id"] for name in ("First", "Second")]
    jobs = run_stage(client, run_id, "scene-options", profiles)
    assert provider.calls[0][1:] == provider.calls[1][1:]
    assert "credential_ref" not in jobs[0]["snapshot"]["profile"]
    choose(client, run_id, jobs[0], "A")
    beats = run_stage(client, run_id, "scene-beats")[0]
    choose(client, run_id, beats)
    old_brief = run_stage(client, run_id, "scene-brief")[0]
    choose(client, run_id, jobs[1], "D")
    run = get_plan(client, run_id)
    assert run["next_step"] == "scene-beats" and len(run["jobs"]) == 4
    stale = client.post(f"/api/scenes/{run_id}/choose", json={"operation_id": uuid4().hex, "expected_revision": run["revision"], "job_id": beats["id"]})
    assert stale.status_code == 409 and "earlier plan" in stale.json()["detail"]
    assert old_brief["result"] is not None


def test_director_edits_preserve_generated_plan_and_require_a_new_brief(client, story):
    run_id, _ = ready_plan(client, story)
    changed = deepcopy(PLAN)
    changed["beats"][0]["development"] = "Wren moves the unopened letter into the light."
    decide(client, run_id, "edit", {"plan": changed})
    run = get_plan(client, run_id)
    assert run["next_step"] == "scene-brief" and run["plan"] == changed
    original = next(job for job in run["jobs"] if job["step"] == "scene-beats")
    assert original["result"] == PLAN
    assert client.post(f"/api/scenes/{run_id}/approve", json={"operation_id": uuid4().hex, "expected_revision": run["revision"]}).status_code == 409
    brief = run_stage(client, run_id, "scene-brief")[0]
    assert decode(brief["snapshot"]["content"])["proposed_beats"] == changed
    choose(client, run_id, brief)
    decide(client, run_id, "approve")


def test_invalid_brief_keeps_output_and_retry_uses_frozen_prompt(client, story):
    run_id, provider = setup_plan(client, story, options=False)
    beats = run_stage(client, run_id, "scene-beats")[0]
    choose(client, run_id, beats)
    client.app.state.scene_runner.provider = InvalidSceneProvider()
    job = run_stage(client, run_id, "scene-brief")[0]
    assert job["status"] == "error" and "outside" in job["error"] and "foreign:secret" in job["output"]
    prompt = saved_prompt(client, "scene-brief")
    client.put("/api/prompts/scene-brief", json={"expected_version_id": prompt["id"], "template": "Changed after the error."})
    client.app.state.scene_runner.provider = provider
    assert client.post(f"/api/scene-jobs/{job['id']}/retry").status_code == 200
    result = finish_plan(client, run_id)["jobs"][-1]
    assert result["status"] == "done" and result["attempt"] == 2 and result["snapshot"] == job["snapshot"]
    attempts = client.get(f"/api/scene-jobs/{job['id']}/attempts").json()
    assert len(attempts) == 2 and attempts[1]["output"] == job["output"]


def test_story_changes_block_stale_approval_but_preserve_the_plan(client, story):
    run_id, _ = ready_plan(client, story)
    before = get_plan(client, run_id)
    append(client, story["branch_id"], "A later accepted event.", 1)
    assert get_plan(client, run_id)["stale"]
    response = client.post(f"/api/scenes/{run_id}/approve", json={"operation_id": uuid4().hex, "expected_revision": before["revision"]})
    assert response.status_code == 409
    assert get_plan(client, run_id)["state"] == before["state"]


def test_preview_changes_are_rejected_before_paid_calls_and_routing_is_per_step(client, story):
    run_id, provider = setup_plan(client, story, options=False)
    selected = make_profile(client, "Beat specialist")
    response = client.put(f"/api/stories/{story['story_id']}/workflow", json={
        "expected_revision": 0, "step_profiles": {"scene-beats": selected["profile_id"]}})
    assert response.status_code == 200
    body = {"expected_revision": 0, "key": "scene-beats"}
    preview = client.post(f"/api/scenes/{run_id}/preview", json=body).json()
    assert preview["jobs"][0]["profile_name"] == "Beat specialist"
    prompt = saved_prompt(client, "scene-beats")
    client.put("/api/prompts/scene-beats", json={"expected_version_id": prompt["id"], "template": "Changed before dispatch."})
    request = {**body, "preview_hash": preview["preview_hash"], "operation_id": uuid4().hex}
    assert client.post(f"/api/scenes/{run_id}/stages", json=request).status_code == 409
    assert provider.calls == [] and get_plan(client, run_id)["jobs"] == []


def test_cancel_restart_and_foreign_choices_preserve_boundaries(client, story):
    run_id, _ = setup_plan(client, story)
    client.app.state.scene_runner.provider = WaitingSceneProvider()
    body = {"expected_revision": 0, "key": "scene-options"}
    preview = client.post(f"/api/scenes/{run_id}/preview", json=body).json()
    started = client.post(f"/api/scenes/{run_id}/stages", json={**body, "operation_id": uuid4().hex, "preview_hash": preview["preview_hash"]}).json()
    job_id = started["job_ids"][0]
    assert client.post(f"/api/scene-jobs/{job_id}/cancel").status_code == 200
    stopped = finish_plan(client, run_id)["jobs"][0]
    assert stopped["status"] == "cancelled" and stopped["output"] == "Partial fixture plan."
    with client.app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE scene_jobs SET status='running' WHERE id=?", (job_id,))
    client.app.state.scene_runner.recover()
    assert get_plan(client, run_id)["jobs"][0]["status"] == "interrupted"
    other = client.post("/api/stories", json={"title": "Other"}).json()
    other_id, _ = setup_plan(client, other)
    foreign = run_stage(client, other_id, "scene-options")[0]
    response = client.post(f"/api/scenes/{run_id}/choose", json={"operation_id": uuid4().hex, "expected_revision": 1,
                            "job_id": foreign["id"], "option_id": "A"})
    assert response.status_code == 409
    with client.app.state.database.connect() as connection:
        assert one(connection, "SELECT output FROM scene_jobs WHERE id=?", (job_id,))["output"] == stopped["output"]
