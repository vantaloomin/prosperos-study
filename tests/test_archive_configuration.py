from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, encode
from server.prompts import ALL_PROMPT_LABELS
from tests.prompt_fixtures import saved_prompt
from tests.test_archive_recovery import saved_work
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished, generate
from tests.test_mechanics import configure, prepare
from tests.test_profiles import make_profile
from tests.test_scenes import ready_plan


def edit_prompt(client, key, story=None, template=None):
    query = f"?story_id={story['story_id']}" if story else ""
    old = saved_prompt(client, key, story["story_id"] if story else None)
    response = client.put(f"/api/prompts/{key}{query}", json={
        "expected_version_id": old["id"], "template": template or old["template"] + "\nFuture version."})
    assert response.status_code == 200, response.text
    return response.json()


def unrelated_history(client, count=100):
    # Valid, unreferenced immutable versions imitate a mature workspace, without provider calls.
    with client.app.state.database.connect(write=True) as connection:
        connection.executemany("INSERT INTO prompt_versions SELECT ?,key,?,template,created_at "
                               "FROM prompt_versions WHERE id='writer-default-v1'",
                               [(uuid4().hex, 10000 + index) for index in range(count)])
        table = connection.execute("SELECT version_id FROM roll_tables WHERE id='momentum'").fetchone()[0]
        start = connection.execute("SELECT MAX(number)+1 FROM roll_table_versions WHERE table_id='momentum'").fetchone()[0]
        connection.executemany("INSERT INTO roll_table_versions SELECT ?,table_id,?,definition,hash,created_at "
                               "FROM roll_table_versions WHERE id=?",
                               [(uuid4().hex, start + index, table) for index in range(count)])


def config_counts(document):
    return {key: len(document["data"][key]) for key in ("profiles", "profile_versions", "prompt_versions", "roll_table_versions")}


def test_repeated_story_recovery_does_not_accumulate_workspace_history(client, story):
    make_profile(client, "Workspace writer", primary=True)
    configure(client, story)
    edit_prompt(client, "writer", story)
    unrelated_history(client)
    before = client.get(f"/api/branches/{story['branch_id']}").json()
    defaults = client.get("/api/prompts").json()
    file, document = backup(client, story)
    expected = {"profiles": 1, "profile_versions": 1, "prompt_versions": len(ALL_PROMPT_LABELS), "roll_table_versions": 30}
    assert config_counts(document) == expected
    first_size = file["byte_count"]
    current = story
    for _ in range(4):
        _, mapping = restore(client, file)
        current = {key: mapping[value] for key, value in current.items()}
        file, document = backup(client, current)
        assert config_counts(document) == expected
        assert file["byte_count"] < first_size + 4096
    assert client.get(f"/api/branches/{story['branch_id']}").json() == before
    assert client.get("/api/prompts").json() == defaults
    _, workspace = backup(client)
    assert len(workspace["data"]["prompt_versions"]) > len(ALL_PROMPT_LABELS) * 5
    assert len(workspace["data"]["roll_table_versions"]) == 250


def change_table(client):
    table = next(row for row in client.get("/api/roll-tables").json() if row["table_id"] == "momentum")
    response = client.put("/api/roll-tables/momentum", json={"operation_id": uuid4().hex,
                          "expected_version_id": table["id"], "definition": table["definition"]})
    assert response.status_code == 200, response.text
    return table["id"], response.json()["id"]


def historical_work(client, story):
    saved_work(client, story)
    ready_plan(client, story)
    configure(client, story, chance=100, cooldown=0)
    prepare(client, story["branch_id"], revision=2)
    _, original = backup(client, story, include_sidebar=True)
    keys = {decode(row["snapshot"])["prompt"]["key"] for table in
            ("generations", "review_jobs", "scene_jobs", "side_turns") for row in original["data"][table]}
    for key in keys:
        edit_prompt(client, key)
    old_table, new_table = change_table(client)
    configure(client, story)
    return original, old_table, new_table


def assert_frozen_inputs(before, after, mapping):
    for table in ("generations", "review_jobs", "scene_jobs", "side_turns"):
        restored = {row["id"]: decode(row["snapshot"]) for row in after["data"][table]}
        for row in before["data"][table]:
            old = decode(row["snapshot"])
            new = restored[mapping[row["id"]]]
            assert new["prompt"]["id"] == mapping[old["prompt"]["id"]]
            assert new["prompt"]["template"] == old["prompt"]["template"]
            assert new.get("content") == old.get("content")
            assert new.get("sources") == old.get("sources")


def test_story_scope_retains_used_historical_prompts_and_table_catalogs(client, story):
    original, old_table, new_table = historical_work(client, story)
    file, document = backup(client, story, include_sidebar=True)
    assert {old_table, new_table} <= {row["id"] for row in document["data"]["roll_table_versions"]}
    _, mapping = restore(client, file)
    restored_story = {key: mapping[value] for key, value in story.items()}
    _, restored = backup(client, restored_story, include_sidebar=True)
    assert config_counts(restored) == config_counts(document)
    assert_frozen_inputs(original, restored, mapping)
    old_roll = decode(document["data"]["mechanic_opportunities"][0]["snapshot"])
    new_roll = decode(restored["data"]["mechanic_opportunities"][0]["snapshot"])
    assert new_roll["draws"] == old_roll["draws"] and new_roll["seed"] == old_roll["seed"]
    assert new_roll["settings"]["table_versions"]["momentum"] == mapping[old_table]
    collaborator = decode(original["data"]["side_turns"][0]["snapshot"])["prompt"]["id"]
    _, plain = backup(client, story)
    assert collaborator not in {row["id"] for row in plain["data"]["prompt_versions"]}


def test_distinct_used_versions_with_identical_text_keep_their_identity(client, story):
    make_profile(client, "Writer", primary=True)
    client.app.state.runner.provider = DraftProvider()
    first = generate(client, story)
    finished(client, first["id"])
    first_prompt = client.get(f"/api/generations/{first['id']}").json()["snapshot"]["prompt"]
    template = first_prompt['template']
    second_prompt = edit_prompt(client, "writer", template=template)
    second = generate(client, story)
    finished(client, second["id"])
    edit_prompt(client, "writer")
    file, document = backup(client, story)
    used = [row for row in document["data"]["prompt_versions"] if row["key"] == "writer"]
    assert len(used) == 3 and used[0]["template"] == used[1]["template"]
    _, mapping = restore(client, file)
    assert mapping[first_prompt['id']] != mapping[second_prompt["id"]]
    restored = client.get(f"/api/generations/{mapping[second['id']]}").json()
    assert restored["snapshot"]["prompt"]["id"] == mapping[second_prompt["id"]]


@pytest.mark.parametrize("target", ["prompt_versions", "roll_table_versions"])
def test_missing_historical_configuration_is_rejected_before_restore(client, story, target):
    _, old_table, _ = historical_work(client, story)
    _, document = backup(client, story, include_sidebar=True)
    broken = deepcopy(document)
    old_prompt = decode(document["data"]["generations"][0]["snapshot"])["prompt"]["id"]
    missing = old_prompt if target == "prompt_versions" else old_table
    broken["data"][target] = [row for row in broken["data"][target] if row["id"] != missing]
    before = client.get("/api/stories").json()
    response = client.post("/api/archives/imports", json={"content": encode(broken)})
    assert response.status_code == 400 and "configuration versions" in response.json()["detail"]
    assert client.get("/api/stories").json() == before
