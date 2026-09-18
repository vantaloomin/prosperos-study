import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.database import decode, encode
from server.providers.events import ProviderEvent
from server.scenes.catalog import DRAFT_KEYS
from server.scenes.continuity_catalog import CONTINUITY_KEYS
from server.scenes.patch_catalog import PATCH_KEYS
from server.scenes.revision_catalog import REVISION_KEYS
from tests.archive_legacy import remove_assessments
from tests.test_archives import backup, restore
from tests.test_profiles import make_profile
from tests.test_scenes import (
    PLAN,
    SceneProvider,
    choose,
    decide,
    get_plan,
    ready_plan,
    run_stage,
    setup_plan,
)

PROSE = "Wren slides the sealed letter into the light and waits for a reply."
LINE = "'Would you like to inspect the seal?' Wren asks."


class DraftProvider(SceneProvider):
    """Labeled test-only outputs; the production runner still uses real adapters."""
    def __init__(self):
        super().__init__()
        self.coverage_status = "rendered"
        self.corrupt = None

    async def generate(self, profile, prompt, content):
        context = decode(content)
        if context["stage"] not in DRAFT_KEYS:
            async for event in super().generate(profile, prompt, content):
                yield event
            return
        self.calls.append((profile, prompt, content))
        result = fixture_result(context, self.coverage_status)
        if self.corrupt:
            self.corrupt(result)
        yield ProviderEvent(text=encode(result), done=True)


def fixture_result(context, coverage_status="rendered"):
    if context["stage"] == "scene-draft":
        blocks = [{"id": "p1", "kind": "prose", "text": PROSE}]
        if context["dialogue_split"]:
            blocks.append({"id": "s1", "kind": "dialogue", "speaker": "Wren", "instruction": "Invite inspection; do not decide for the player."})
        return {"summary": "UI/test fixture only; no model call.", "blocks": blocks, "proposed_facts": ["Light falls across the seal."]}
    if context["stage"] == "scene-dialogue":
        return {"summary": "Fixture dialogue only.", "lines": [{"slot_id": "s1", "text": LINE}]}
    return {"summary": "Fixture coverage only.", "beats": [{"beat_id": beat["id"], "status": coverage_status,
            "quotes": [PROSE], "explanation": "The letter remains sealed and the decision is open."}
            for beat in context["proposed_beats"]["beats"]], "issues": []}


def approved_plan(client, story, dialogue=False):
    run_id, _ = setup_plan(client, story, options=False, dialogue=dialogue)
    provider = DraftProvider()
    client.app.state.scene_runner.provider = provider
    for key in ["scene-beats", "scene-brief"]:
        choose(client, run_id, run_stage(client, run_id, key)[0])
    decide(client, run_id, "approve", {"note": "Draft without deciding for the player."})
    return run_id, provider


def test_full_draft_and_coverage_require_approval_and_never_accept_story_text(client, story):
    run_id, _ = setup_plan(client, story, options=False)
    request = {"expected_revision": 0, "key": "scene-draft"}
    assert client.post(f"/api/scenes/{run_id}/preview", json=request).status_code == 409
    client.app.state.scene_runner.provider = DraftProvider()
    for key in ["scene-beats", "scene-brief"]:
        choose(client, run_id, run_stage(client, run_id, key)[0])
    decide(client, run_id, "approve")
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    assert get_plan(client, run_id)["next_step"] == "scene-draft"
    draft = run_stage(client, run_id, "scene-draft")[0]
    choose(client, run_id, draft)
    run = get_plan(client, run_id)
    assert run["draft"]["complete"] and run["draft"]["text"] == PROSE
    assert run["next_step"] == "scene-coverage"
    assert client.post(f"/api/scenes/{run_id}/preview", json={"expected_revision": run["revision"], "key": "scene-dialogue"}).status_code == 400
    coverage = run_stage(client, run_id, "scene-coverage")[0]
    choose(client, run_id, coverage)
    assert get_plan(client, run_id)["coverage_passes"]
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert get_plan(client, run_id)["draft"]["proposed_facts"] == ["Light falls across the seal."]


def test_split_dialogue_comparison_invalidates_dependents_but_preserves_approval(client, story):
    run_id, provider = approved_plan(client, story, dialogue=True)
    approved = deepcopy(get_plan(client, run_id)["state"]["gate_a"])
    profiles = [make_profile(client, name)["profile_id"] for name in ["Drafter A", "Drafter B"]]
    drafts = run_stage(client, run_id, "scene-draft", profiles)
    assert provider.calls[-1][1:] == provider.calls[-2][1:]
    choose(client, run_id, drafts[0])
    run = get_plan(client, run_id)
    assert run["draft"]["text"] is None and not run["draft"]["complete"]
    assert client.post(f"/api/scenes/{run_id}/preview", json={"expected_revision": run["revision"], "key": "scene-coverage"}).status_code == 409
    dialogue = run_stage(client, run_id, "scene-dialogue")[0]
    choose(client, run_id, dialogue)
    assert get_plan(client, run_id)["draft"]["text"] == PROSE + "\n\n" + LINE
    coverage = run_stage(client, run_id, "scene-coverage")[0]
    choose(client, run_id, coverage)
    choose(client, run_id, drafts[1])
    run = get_plan(client, run_id)
    assert run["state"]["gate_a"] == approved
    assert run["next_step"] == "scene-dialogue" and not run["coverage_passes"]
    assert not next(job for job in run["jobs"] if job["id"] == dialogue["id"])["current_inputs"]
    assert not next(job for job in run["jobs"] if job["id"] == coverage["id"])["current_inputs"]
    body = {"operation_id": uuid4().hex, "expected_revision": run["revision"], "job_id": dialogue["id"]}
    assert client.post(f"/api/scenes/{run_id}/choose", json=body).status_code == 409


def test_incomplete_coverage_is_a_preserved_redraft_assessment(client, story):
    run_id, provider = approved_plan(client, story)
    choose(client, run_id, run_stage(client, run_id, "scene-draft")[0])
    provider.coverage_status = "compressed"
    review = run_stage(client, run_id, "scene-coverage")[0]
    assert review["status"] == "done"
    choose(client, run_id, review)
    assert not get_plan(client, run_id)["coverage_passes"]
    replacement = run_stage(client, run_id, "scene-draft")[0]
    assert decode(replacement["snapshot"]["content"])["revision_context"]["coverage"] == review["result"]
    choose(client, run_id, replacement)
    run = get_plan(client, run_id)
    assert "scene-coverage" not in run["state"]["selections"]
    assert next(job for job in run["jobs"] if job["id"] == review["id"])["result"]["beats"][0]["status"] == "compressed"


@pytest.mark.parametrize("failure", ["quote", "beat", "slot", "draft"])
def test_invalid_stage_outputs_keep_raw_text_without_becoming_selected(client, story, failure):
    run_id, provider = approved_plan(client, story, dialogue=True)
    if failure != "draft":
        choose(client, run_id, run_stage(client, run_id, "scene-draft")[0])
    if failure in {"quote", "beat"}:
        choose(client, run_id, run_stage(client, run_id, "scene-dialogue")[0])
    mutations = {"quote": lambda result: result["beats"][0].update(quotes=["Invented evidence"]),
                 "beat": lambda result: result["beats"][0].update(beat_id="unapproved-beat"),
                 "slot": lambda result: result["lines"][0].update(slot_id="foreign-slot"),
                 "draft": lambda result: result["blocks"].append(deepcopy(result["blocks"][0]))}
    provider.corrupt = mutations[failure]
    key = {"slot": "scene-dialogue", "draft": "scene-draft"}.get(failure, "scene-coverage")
    job = run_stage(client, run_id, key)[0]
    assert job["status"] == "error" and job["output"] and job["error"]
    assert key not in get_plan(client, run_id)["state"]["selections"]


def test_completed_draft_archive_restores_gate_and_can_redraft_without_mutating_story(client, story):
    run_id, provider = approved_plan(client, story, dialogue=True)
    for key in DRAFT_KEYS:
        choose(client, run_id, run_stage(client, run_id, key)[0])
    old = get_plan(client, run_id)
    file, document = backup(client, story)
    assert document["version"] == ARCHIVE_VERSION
    result, mapping = restore(client, file)
    restored = get_plan(client, mapping[run_id])
    assert restored["draft"] == old["draft"] and restored["coverage_passes"]
    assert all(job["current_inputs"] for job in restored["jobs"])
    branch = client.get(f"/api/branches/{mapping[story['branch_id']]}").json()
    assert len(branch["messages"]) == 1
    new = run_stage(client, mapping[run_id], "scene-draft")[0]
    choose(client, mapping[run_id], new)
    assert client.get(f"/api/branches/{mapping[story['branch_id']]}").json() == branch
    backup(client, {"story_id": result["story_ids"][0], "branch_id": branch["id"]})
    assert len(provider.calls) == 6


def test_version_two_approved_plans_upgrade_and_continue_with_default_whole_prose(client, story):
    run_id, _ = approved_plan(client, story)
    _, document = backup(client, story)
    remove_assessments(document)
    document["version"] = 2
    document['data'].pop('library_imports', None)
    document['data'].pop('asset_import_origins', None)
    document['data'].pop('asset_sources', None)
    document.pop('library_drafts', None)
    del document["data"]["continuity_commits"]
    new_keys = DRAFT_KEYS + REVISION_KEYS + PATCH_KEYS + CONTINUITY_KEYS
    document["prompt_heads"] = {key: value for key, value in document["prompt_heads"].items() if key not in new_keys}
    document["data"]["prompt_versions"] = [row for row in document["data"]["prompt_versions"] if row["key"] not in new_keys]
    for row in document["data"]["scene_runs"]:
        snapshot = decode(row["snapshot"])
        snapshot.pop("dialogue_split")
        row["snapshot"] = encode(snapshot)
    content = json.dumps(document)
    staged = client.post("/api/archives/imports", json={"content": content})
    assert staged.status_code == 201, staged.text
    assert staged.json()["summary"]["version"] == ARCHIVE_VERSION
    _, mapping = restore(client, staged.json())
    assert json.dumps(document) == content
    job = run_stage(client, mapping[run_id], "scene-draft")[0]
    assert not decode(job["snapshot"]["content"])["dialogue_split"]
    choose(client, mapping[run_id], job)
    assert get_plan(client, mapping[run_id])["draft"]["text"] == PROSE


def test_drafting_preserves_director_edits_and_approval_cannot_be_reopened(client, story):
    run_id, _ = ready_plan(client, story)
    edited = deepcopy(PLAN)
    edited["ending"] = "Pause for the player; no forced relocation."
    decide(client, run_id, "edit", {"plan": edited})
    choose(client, run_id, run_stage(client, run_id, "scene-brief")[0])
    decide(client, run_id, "approve")
    client.app.state.scene_runner.provider = DraftProvider()
    draft = run_stage(client, run_id, "scene-draft")[0]
    assert decode(draft["snapshot"]["content"])["proposed_beats"] == edited
    choose(client, run_id, draft)
    run = get_plan(client, run_id)
    assert run["plan"] == edited and run["state"]["gate_a"]["beat_edit"] == edited
    body = {"expected_revision": run["revision"], "operation_id": uuid4().hex, "plan": PLAN}
    assert client.post(f"/api/scenes/{run_id}/edit", json=body).status_code == 409
    _, document = backup(client, story)
    latest = document["data"]["scene_decisions"][-1]
    latest["kind"] = "edit"
    assert client.post("/api/archives/imports", json={"content": json.dumps(document)}).status_code == 400
