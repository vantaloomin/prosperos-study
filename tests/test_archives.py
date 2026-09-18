import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.database import decode, one
from server.providers.events import ProviderEvent
from tests.test_generations import DraftProvider, finished, generate
from tests.test_history import append
from tests.test_library import adoption_request, create_book, publish, with_book
from tests.test_mechanics import accept_manual, configure, prepare
from tests.test_profiles import MemoryVault, make_profile
from tests.test_reviews import ReviewProvider, finished_review, review_body, start
from tests.test_sidebar import CollaboratorProvider, ask, settle, thread


def backup(client, story=None, include_sidebar=False):
    body = {"scope": "story" if story else "workspace", "include_sidebar": include_sidebar}
    if story:
        body.update(story_id=story["story_id"], branch_id=story["branch_id"])
    response = client.post("/api/archives", json=body)
    assert response.status_code == 201, response.text
    file = response.json()
    download = client.get(file["download_url"])
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    return file, download.json()


def restore(client, file):
    body = {"operation_id": uuid4().hex, "sha256": file["sha256"]}
    response = client.post(f"/api/archives/{file['id']}/restore", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert client.post(f"/api/archives/{file['id']}/restore", json=body).json() == result
    with client.app.state.database.connect() as connection:
        mapping = decode(one(connection, "SELECT identity_map FROM archive_restores WHERE id=?", (result["receipt_id"],))["identity_map"])
    return result, mapping


def test_workspace_restore_preserves_shared_versions_adoptions_and_paths(client):
    book = create_book(client)
    a, b = with_book(client, book, "A"), with_book(client, book, "B")
    old = append(client, a["branch_id"], "A wet morning", 0)
    next_book = publish(client, book)
    endpoint = f"/api/versions/{next_book['id']}/adoption"
    client.post(endpoint, json=adoption_request(client.get(endpoint).json()))
    fork = client.post(f"/api/branches/{a['branch_id']}/forks", json={
        "operation_id": uuid4().hex, "expected_revision": 2, "node_id": old,
        "name": "An earlier version", "replacement": "Rain again",
    }).json()["branch_id"]
    file, document = backup(client)
    result, mapping = restore(client, file)
    assert len(result["story_ids"]) == 2 and len(client.get("/api/stories").json()) == 4
    restored_a = client.get(f"/api/stories/{mapping[a['story_id']]}").json()
    restored_b = client.get(f"/api/stories/{mapping[b['story_id']]}").json()
    assert restored_a["attachments"][0]["asset_id"] == restored_b["attachments"][0]["asset_id"] == mapping[book["asset_id"]]
    assert mapping[book["asset_id"]] != book["asset_id"]
    assert client.get(f"/api/branches/{mapping[fork]}").json()["attachments"][0]["version_id"] == mapping[book["id"]]
    assert len(client.get(f"/api/library/{mapping[book['asset_id']]}/versions").json()) == 2
    assert len(document["data"]["adoptions"]) == 2
    assert client.get(f"/api/branches/{a['branch_id']}").json()["messages"][0]["text"] == "A wet morning"


def test_story_archive_is_self_contained_and_leaves_other_stories_out(client):
    book = create_book(client)
    character = client.post("/api/library", json={"kind": "character", "name": "Reader",
                            "content": {"lorebook_versions": [book["id"]]}}).json()
    chosen = with_book(client, character, "Chosen")
    other = client.post("/api/stories", json={"title": "Outside"}).json()
    append(client, other["branch_id"], "PRIVATE OUTSIDE STORY", 0)
    file, document = backup(client, chosen)
    assert "PRIVATE OUTSIDE STORY" not in json.dumps(document)
    assert len(document["data"]["assets"]) == 2 and len(document["data"]["stories"]) == 1
    _, mapping = restore(client, file)
    imported = client.get(f"/api/stories/{mapping[chosen['story_id']]}").json()
    assert {item["version_id"] for item in imported["attachments"]} == {mapping[book["id"]], mapping[character["id"]]}


class ConfigurationReader:
    def __init__(self):
        self.calls = []

    async def generate(self, _profile, _prompt, content):
        context = json.loads(content)
        self.calls.append(context)
        if not any(source['id'].startswith('configuration:') for source in context['sources']):
            source = next(item for item in context['source_index'] if item['id'].startswith('configuration:'))
            yield ProviderEvent(text='READ_SOURCES: ' + json.dumps([source['id']]), done=True)
        else:
            yield ProviderEvent(text='Configuration is available as frozen reference material.', done=True)


def test_import_pins_configuration_without_changing_workspace_defaults(client, story):
    writer = next(row for row in client.get("/api/prompts").json() if row["key"] == "writer")
    client.put("/api/prompts/writer", json={"expected_version_id": writer["id"], "template": "Archived writer instructions."})
    make_profile(client, "Archive writer", primary=True)
    file, _ = backup(client, story)
    current = next(row for row in client.get("/api/prompts").json() if row["key"] == "writer")
    client.put("/api/prompts/writer", json={"expected_version_id": current["id"], "template": "New workspace instructions."})
    _, mapping = restore(client, file)
    imported_id = mapping[story["story_id"]]
    prompts = client.get(f"/api/prompts?story_id={imported_id}").json()
    pinned = next(row for row in prompts if row["key"] == "writer")
    assert pinned["template"] == "Archived writer instructions."
    client.put(f"/api/prompts/writer?story_id={imported_id}", json={"expected_version_id": pinned["id"], "template": "This story only."})
    assert next(row for row in client.get("/api/prompts").json() if row["key"] == "writer")["template"] == "New workspace instructions."
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    run = generate(client, {"branch_id": mapping[story["branch_id"]]})
    finished(client, run["id"])
    from server.prompt_sections import system_prompt
    saved = client.get(f"/api/generations/{run['id']}").json()['snapshot']
    assert saved['prompt']['template'] == 'This story only.'
    assert provider.calls[0][1] == system_prompt(saved)
    imported_story = {"story_id": imported_id, "branch_id": mapping[story["branch_id"]]}
    sidebar = ConfigurationReader()
    client.app.state.side_runner.provider = sidebar
    conversation = thread(client, imported_story)
    ask(client, conversation, imported_story)
    settle(client)
    configuration = "".join(source["text"] for source in sidebar.calls[-1]["sources"] if source["id"].startswith("configuration:"))
    assert "This story only." in configuration and "New workspace instructions." not in configuration


def test_restored_rolls_and_saved_results_do_not_make_calls(client, story):
    writer, reviewer = DraftProvider(), ReviewProvider()
    client.app.state.runner.provider = writer
    client.app.state.review_runner.provider = reviewer
    make_profile(client, "Writer", primary=True)
    configure(client, story, chance=100, cooldown=0)
    opportunity = prepare(client, story["branch_id"])
    accept_manual(client, story["branch_id"], opportunity["id"])
    run = generate(client, story, revision=1)
    candidate = finished(client, run["id"])["candidates"][0]
    review, _ = start(client, story, review_body())
    report = finished_review(client, review["id"])
    file, document = backup(client, story)
    _, mapping = restore(client, file)
    assert len(writer.calls) == len(reviewer.calls) == 1
    restored = client.get(f"/api/branches/{mapping[story['branch_id']]}").json()
    assert restored["mechanics"]["state"]["last_opportunity_id"] == mapping[opportunity["id"]]
    original = client.get(f"/api/generations/{run['id']}").json()
    imported = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert original["snapshot"]["content"] == imported["snapshot"]["content"]
    assert imported["candidates"][0]["output"] == candidate["output"]
    restored_review = client.get(f"/api/reviews/{mapping[review['id']]}").json()
    assert restored_review["jobs"][0]["result"] == report["jobs"][0]["result"]
    assert len(document["data"]["roll_table_versions"]) == 30


def test_optional_sidebar_and_credentials_are_preserved_or_excluded_explicitly(client, story):
    client.app.state.vault = MemoryVault()
    profile = client.post("/api/profiles", json={"name": "Private connection", "api_key": "TEST_SECRET_NEVER_EXPORT",
                         "make_primary": True, "config": {"provider": "openai", "model": "test"}}).json()
    provider = CollaboratorProvider()
    client.app.state.side_runner.provider = provider
    conversation = thread(client, story)
    ask(client, conversation, story)
    settle(client)
    _, plain = backup(client, story)
    assert plain["data"]["side_turns"] == []
    file, private = backup(client, story, include_sidebar=True)
    raw = json.dumps(private)
    assert "TEST_SECRET_NEVER_EXPORT" not in raw
    assert all(row["credential_ref"] is None for row in private["data"]["profile_versions"])
    _, mapping = restore(client, file)
    restored = client.get(f"/api/side-conversations/{mapping[conversation]}").json()
    assert restored["turns"][0]["replies"][0]["output"].startswith("Proposal only")
    assert len(provider.calls) == 1 and mapping[profile["profile_id"]] != profile["profile_id"]


@pytest.mark.parametrize("defect", ["format", "cycle", "dangling", "credentials", "unknown_group"])
def test_invalid_archives_fail_before_creating_stories(client, story, defect):
    make_profile(client, "Writer", primary=True)
    node = append(client, story["branch_id"], "A beginning", 0)
    _, document = backup(client, story)
    malformed = deepcopy(document)
    mutations = {
        "format": lambda: malformed.update(version=999),
        "cycle": lambda: malformed["data"]["nodes"][0].update(parent_id=node),
        "dangling": lambda: malformed["data"]["nodes"].clear(),
        "credentials": lambda: malformed["data"]["profile_versions"][0].update(credential_ref="unsafe-reference"),
        "unknown_group": lambda: malformed["data"].update(arbitrary_sql=[]),
    }
    mutations[defect]()
    response = client.post("/api/archives/imports", json={"content": json.dumps(malformed)})
    assert response.status_code in {400, 404}, response.text
    assert len(client.get("/api/stories").json()) == 1
