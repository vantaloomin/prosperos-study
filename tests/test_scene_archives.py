import json
from copy import deepcopy

from server.archives.format import ARCHIVE_VERSION, SCENE_TABLES
from server.database import decode
from server.prompts import PROMPT_LABELS, original_prompt
from server.providers.events import ProviderEvent
from server.scenes.catalog import SCENE_PROMPTS
from tests.archive_legacy import remove_assessments
from tests.test_archives import backup, restore
from tests.test_scenes import PLAN, choose, decide, get_plan, ready_plan, run_stage, setup_plan
from tests.test_sidebar import ask, settle, thread


def test_scene_archive_roundtrip_keeps_edited_approval_sources_and_old_results(client, story):
    run_id, provider = ready_plan(client, story)
    edited = deepcopy(PLAN)
    edited["ending"] = "Leave both the letter and the player's decision unresolved."
    decide(client, run_id, "edit", {"plan": edited})
    job = run_stage(client, run_id, "scene-brief")[0]
    choose(client, run_id, job)
    decide(client, run_id, "approve", {"note": "Ready to draft later."})
    old = get_plan(client, run_id)
    calls = len(provider.calls)
    file, document = backup(client, story)
    assert document["version"] == ARCHIVE_VERSION and len(document["data"]["scene_jobs"]) == 4
    result, mapping = restore(client, file)
    new = get_plan(client, mapping[run_id])
    assert not new["stale"] and new["plan"] == edited and new["revision"] == old["revision"]
    assert new["state"]["gate_a"]["selections"] == {key: mapping[value] for key, value in old["state"]["selections"].items()}
    assert [item["snapshot"]["content"] for item in new["jobs"]] == [item["snapshot"]["content"] for item in old["jobs"]]
    assert [item["result"] for item in new["jobs"]] == [item["result"] for item in old["jobs"]]
    assert all(item["current_inputs"] for item in new["jobs"] if item["id"] in new["state"]["selections"].values())
    assert len(provider.calls) == calls
    restored_file, _ = backup(client, {"story_id": result["story_ids"][0], "branch_id": mapping[story["branch_id"]]})
    assert restored_file["summary"]["counts"]["scene_decisions"] == len(old["decisions"])


def test_old_v1_archives_upgrade_without_changing_existing_prompt_defaults(client, story):
    _, document = backup(client, story)
    remove_assessments(document)
    document["version"] = 1
    document['data'].pop('library_imports', None)
    document['data'].pop('asset_import_origins', None)
    document['data'].pop('asset_sources', None)
    document.pop('library_drafts', None)
    del document["data"]["continuity_commits"]
    for table in SCENE_TABLES:
        del document["data"][table]
    document["data"]["prompt_versions"] = [row for row in document["data"]["prompt_versions"] if row["key"] not in SCENE_PROMPTS]
    document["prompt_heads"] = {key: value for key, value in document["prompt_heads"].items() if key not in SCENE_PROMPTS}
    original = json.dumps(document)
    response = client.post("/api/archives/imports", json={"content": original})
    assert response.status_code == 201, response.text
    result, _ = restore(client, response.json())
    assert json.dumps(document) == original
    restored = client.get(f"/api/prompts?story_id={result['story_ids'][0]}").json()
    assert {item['key'] for item in restored} == set(PROMPT_LABELS) - {'library-assist'}
    with client.app.state.database.connect() as connection:
        # Migration retains every historical task head even though the UI shows roles.
        for key, template in SCENE_PROMPTS.items():
            assert original_prompt(connection, key)['key'] == key
            assert connection.execute('SELECT id FROM prompt_versions WHERE key=? AND template=?', (key, template)).fetchone()
    assert response.json()["summary"]["version"] == ARCHIVE_VERSION


def test_archive_rejects_missing_decisions_and_fabricated_brief_evidence(client, story):
    run_id, _ = ready_plan(client, story)
    _, document = backup(client, story)
    missing = deepcopy(document)
    missing["data"]["scene_decisions"].pop()
    assert client.post("/api/archives/imports", json={"content": json.dumps(missing)}).status_code == 400
    fabricated = deepcopy(document)
    brief = next(row for row in fabricated["data"]["scene_jobs"] if row["step"] == "scene-brief")
    value = decode(brief["result"])
    value["facts"][0]["quote"] = "An unsupported invented fact."
    brief["result"] = json.dumps(value)
    response = client.post("/api/archives/imports", json={"content": json.dumps(fabricated)})
    assert response.status_code == 502 and "quotation" in response.json()["detail"]
    assert get_plan(client, run_id)["state"]["gate_a"] is None


def test_restored_unapproved_plan_can_continue_with_mapped_dependencies(client, story):
    run_id, provider = setup_plan(client, story, options=False)
    beats = run_stage(client, run_id, "scene-beats")[0]
    choose(client, run_id, beats)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored_id = mapping[run_id]
    brief = run_stage(client, restored_id, "scene-brief")[0]
    choose(client, restored_id, brief)
    decide(client, restored_id, "approve")
    assert len(provider.calls) == 2 and not get_plan(client, run_id)["state"]["gate_a"]


class SceneRetrievalProvider:
    def __init__(self, prefix):
        self.prefix, self.calls = prefix, []

    async def generate(self, _profile, _prompt, content):
        context = json.loads(content)
        self.calls.append(context)
        if not any(source["id"].startswith(self.prefix) for source in context["sources"]):
            source = next(item for item in context["source_index"] if item["id"].startswith(self.prefix))
            yield ProviderEvent(text="READ_SOURCES: " + json.dumps([source["id"]]), done=True)
        else:
            yield ProviderEvent(text="The scene plan is a proposal, not accepted Story canon.", done=True)


def test_collaborator_receives_frozen_plans_without_story_mutation_permissions(client, story):
    run_id, _ = ready_plan(client, story)
    provider = SceneRetrievalProvider(f"scene:{run_id}:")
    client.app.state.side_runner.provider = provider
    conversation = thread(client, story)
    turn = ask(client, conversation, story, revision=1)
    settle(client)
    frozen = client.get(f"/api/side-turns/{turn['id']}/sources").json()
    sources = [source for source in frozen if source["id"].startswith(f"scene:{run_id}:")]
    content = "".join(source["text"] for source in sources)
    assert "Proposals stay separate" in content and "credential_ref" not in content
    assert PLAN["ending"] in content and '"gate_a":null' in content
    retrieved = next(source for source in provider.calls[-1]["sources"] if source["id"].startswith(f"scene:{run_id}:"))
    assert retrieved in sources
    decide(client, run_id, "approve")
    assert client.get(f"/api/side-turns/{turn['id']}/sources").json() == frozen
