from server.database import decode
from server.errors import require


def credential_reference(database, profile):
    reference = profile.get("credential_ref")
    if reference or database is None:
        return reference
    with database.connect() as connection:
        row = connection.execute("SELECT v.config,v.credential_ref FROM archive_origins o "
                                 "JOIN profiles p ON p.id=o.id JOIN profile_versions v ON v.id=p.latest_version_id "
                                 "WHERE o.id=? AND o.kind='profiles'", (profile["profile_id"],)).fetchone()
    if row is None:
        return None
    current = decode(row["config"])
    frozen = profile["config"]
    require((current["provider"], current["base_url"]) == (frozen["provider"], frozen["base_url"]),
            "This restored request uses its original provider and address. Reconnect that same address in its model profile before retrying.", 409)
    # Only reconnect the credential. The saved model, sampling settings and input remain frozen.
    return row["credential_ref"]
