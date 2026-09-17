from server.database import decode, one
from server.profiles import resolve_profile


class MemoryVault:
    def __init__(self):
        self.values = {}

    def get(self, reference):
        return self.values.get(reference)

    def put(self, reference, secret):
        self.values[reference] = secret


def make_profile(client, name, primary=False):
    response = client.post("/api/profiles", json={"name": name, "make_primary": primary,
                           "config": {"provider": "local", "model": "test-model"}})
    assert response.status_code == 201
    return response.json()


def test_credentials_never_enter_profile_json_or_database(client):
    client.app.state.vault = MemoryVault()
    secret = "test-only-not-a-real-key"
    response = client.post("/api/profiles", json={"name": "Writer", "api_key": secret,
                           "config": {"provider": "openai", "model": "chosen-model"}})
    assert response.status_code == 201
    assert response.json()["has_saved_key"]
    assert secret not in response.text
    assert secret not in client.get("/api/profiles").text
    with client.app.state.database.connect() as connection:
        dump = '\n'.join(connection.iterdump())
    assert secret not in dump
    assert secret in client.app.state.vault.values.values()


def test_profile_routing_and_old_versions_survive_updates(client, story):
    primary = make_profile(client, "Primary", primary=True)
    reviewer = make_profile(client, "Reviewer")
    explicit = make_profile(client, "Explicit")
    with client.app.state.database.connect(write=True) as connection:
        original = one(connection, "SELECT * FROM stories WHERE id=?", (story["story_id"],))
        assert resolve_profile(connection, original, "writer")["id"] == primary["id"]
        configured = {**original, "settings": '{"step_profiles":{"review":"' + reviewer["profile_id"] + '"}}'}
        assert resolve_profile(connection, configured, "review")["id"] == reviewer["id"]
        assert resolve_profile(connection, configured, "review", explicit["profile_id"])["id"] == explicit["id"]
    response = client.put(f"/api/profiles/{primary['profile_id']}", json={
        "name": "Primary revised", "expected_version_id": primary["id"],
        "config": {"provider": "local", "model": "new-model"},
    })
    assert response.status_code == 200
    assert response.json()["number"] == 2
    with client.app.state.database.connect() as connection:
        old = one(connection, "SELECT * FROM profile_versions WHERE id=?", (primary["id"],))
    assert decode(old["config"])["model"] == "test-model"


def test_connection_urls_and_unsupported_settings_are_validated(client):
    response = client.post("/api/profiles", json={"name": "Bad", "config": {
        "provider": "openai", "model": "model", "base_url": "https://example.com",
    }})
    assert response.status_code == 422
    local = client.post("/api/profiles", json={"name": "Bad local", "config": {
        "provider": "local", "model": "model", "base_url": "http://localhost@public.example/v1",
    }})
    assert local.status_code == 422
    codex = client.post("/api/profiles", json={"name": "Bad CLI", "config": {
        "provider": "codex", "model": "chosen-model", "temperature": 0.7,
    }})
    assert codex.status_code == 422


def test_provider_change_does_not_reuse_another_providers_key(client):
    client.app.state.vault = MemoryVault()
    original = client.post("/api/profiles", json={"name": "Writer", "api_key": "test-secret",
                           "config": {"provider": "openai", "model": "model"}}).json()
    updated = client.put(f"/api/profiles/{original['profile_id']}", json={
        "name": "Now local", "expected_version_id": original["id"],
        "config": {"provider": "local", "model": "local-model"},
    }).json()
    assert not updated["has_saved_key"]


def test_validation_errors_do_not_echo_secret_inputs(client):
    response = client.post("/api/profiles", json={"name": "Writer", "api_key": {"raw": "secret-value"},
                           "config": {"provider": "local", "model": "model"}})
    assert response.status_code == 422
    assert "secret-value" not in response.text
