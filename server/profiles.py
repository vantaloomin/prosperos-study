from server.agent_switches import require_agent
from server.database import Database, decode, encode, identifier, many, now, one
from server.errors import require
from server.providers.config import ProfileCreate, ProfileUpdate, profile_ready
from server.providers.vault import CredentialVault, credential_for


def same_connection(first, second):
    return first['provider'] == second['provider'] and (first['base_url'] == second['base_url'] or not first['base_url'])


def probe_key(database, vault, body):
    if body.api_key and body.api_key.get_secret_value():
        return body.api_key.get_secret_value()
    reference = None
    if body.profile_id:
        with database.connect() as connection:
            profile = profile_snapshot(connection, body.profile_id)
        require(profile['id'] == body.expected_version_id, 'This profile changed. Reopen it before testing.', 409)
        if same_connection(profile['config'], body.config.model_dump()):
            reference = profile['credential_ref']
    return credential_for(vault, body.config.provider, reference)


def profile_view(row: dict) -> dict:
    visible = {key: value for key, value in row.items() if key != "credential_ref"}
    label = row["name"]
    if row.get("restored_at"):
        label += f" · restored {row['restored_at'][:16].replace('T', ' ')} UTC"
    return {**visible, "display_name": label, "config": decode(row["config"]), "has_saved_key": bool(row["credential_ref"]), "ready": profile_ready(decode(row["config"]))}


def primary_id(connection) -> str | None:
    row = connection.execute("SELECT value FROM preferences WHERE key='primary_profile_id'").fetchone()
    return decode(row["value"]) if row else None


def set_primary(connection, profile_id: str):
    profile = profile_snapshot(connection, profile_id)
    require(profile_ready(profile["config"]), "Finish this connection in Settings > Models before choosing it as Primary Writer.", 409)
    connection.execute("INSERT INTO preferences VALUES ('primary_profile_id',?) "
                       "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (encode(profile_id),))


def profile_snapshot(connection, profile_id: str) -> dict:
    row = one(connection, "SELECT v.* FROM profiles p JOIN profile_versions v "
              "ON p.latest_version_id=v.id WHERE p.id=?", (profile_id,))
    return {**row, "config": decode(row["config"])}


def resolve_profile(connection, story: dict, step: str, override: str | None = None) -> dict:
    require_agent(connection, step, story)
    settings = decode(story["settings"])
    step_profile = settings.get("step_profiles", {}).get(step)
    default = settings.get("primary_profile_id") or primary_id(connection)
    resolved = override or step_profile or default
    require(bool(resolved), "Choose a Primary Writer in Settings before generating.", 409)
    profile = profile_snapshot(connection, resolved)
    require(profile_ready(profile["config"]), "Finish this connection in Settings > Models: choose a model and API address before generating.", 409)
    return profile


class Profiles:
    def __init__(self, database: Database, vault: CredentialVault):
        self.database = database
        self.vault = vault

    def list(self) -> dict:
        with self.database.connect() as connection:
            rows = many(connection, "SELECT v.*, o.created_at AS restored_at FROM profiles p JOIN profile_versions v "
                        "ON p.latest_version_id=v.id LEFT JOIN archive_origins o ON o.id=p.id ORDER BY v.name COLLATE NOCASE")
            return {"profiles": [profile_view(row) for row in rows], "primary_profile_id": primary_id(connection)}

    def create(self, body: ProfileCreate) -> dict:
        with self.database.connect(write=True) as connection:
            profile_id = identifier()
            connection.execute("INSERT INTO profiles VALUES (?,NULL,?)", (profile_id, now()))
            return self._publish(connection, profile_id, 1, body, None)

    def update(self, profile_id: str, body: ProfileUpdate) -> dict:
        with self.database.connect(write=True) as connection:
            current = profile_snapshot(connection, profile_id)
            require(current["id"] == body.expected_version_id, "This model profile has changed. Reopen it.", 409)
            credential = current["credential_ref"] if same_connection(current["config"], body.config.model_dump()) else None
            return self._publish(connection, profile_id, current["number"] + 1, body, credential)

    def _publish(self, connection, profile_id, number, body, previous_credential):
        version_id = identifier()
        credential_ref = previous_credential
        if body.api_key and body.api_key.get_secret_value():
            require(body.config.provider != "codex", "Use Codex CLI login; do not enter a plan credential here.")
            credential_ref = identifier()
            self.vault.put(credential_ref, body.api_key.get_secret_value())
        connection.execute("INSERT INTO profile_versions VALUES (?,?,?,?,?,?,?)",
                           (version_id, profile_id, number, body.name.strip() or f"{body.config.provider.title()} connection", encode(body.config.model_dump()),
                            credential_ref, now()))
        connection.execute("UPDATE profiles SET latest_version_id=? WHERE id=?", (version_id, profile_id))
        ready = profile_ready(body.config.model_dump())
        if body.make_primary and ready:
            set_primary(connection, profile_id)
        elif not ready and primary_id(connection) == profile_id:
            connection.execute("DELETE FROM preferences WHERE key='primary_profile_id'")
        return profile_view(one(connection, "SELECT * FROM profile_versions WHERE id=?", (version_id,)))

    def primary(self, profile_id: str):
        with self.database.connect(write=True) as connection:
            set_primary(connection, profile_id)
        return {"primary_profile_id": profile_id}
