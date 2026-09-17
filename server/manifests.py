from server.database import decode, encode, identifier, now, one
from server.errors import require
from server.library import get_version


def attachments_at(connection, manifest_id: str) -> list[dict]:
    manifest = one(connection, "SELECT * FROM manifests WHERE id=?", (manifest_id,))
    return decode(manifest["attachments"])


def expand_dependencies(connection, attachments: list[dict]) -> list[dict]:
    resolved = {item["asset_id"]: item for item in attachments}
    require(len(resolved) == len(attachments), "Attach each library item only once.")
    pending = list(attachments)
    visited = set()
    while pending:
        item = pending.pop()
        if item["version_id"] in visited:
            continue
        visited.add(item["version_id"])
        dependencies = dependencies_for(connection, item)
        for dependency in dependencies:
            merge_dependency(resolved, dependency)
            pending.append(dependency)
    return sorted(resolved.values(), key=lambda item: (-item["priority"], item["asset_id"]))


def dependencies_for(connection, item: dict) -> list[dict]:
    version = get_version(connection, item["version_id"])
    require(version["asset_id"] == item["asset_id"], "A library version belongs to a different item.")
    if not item["enabled"]:
        return []
    versions = [get_version(connection, ref) for ref in version["content"].get("lorebook_versions", [])]
    return [{"asset_id": version["asset_id"], "version_id": version["id"],
             "enabled": True, "priority": item["priority"]} for version in versions]


def merge_dependency(resolved: dict, dependency: dict):
    old = resolved.get(dependency["asset_id"])
    if old is not None:
        require(old["version_id"] == dependency["version_id"] and old["enabled"],
                "Attached character and lorebooks require conflicting versions. Resolve them first.")
        return
    resolved[dependency["asset_id"]] = dependency


def create_manifest(connection, story_id: str, attachments: list[dict]) -> str:
    resolved = expand_dependencies(connection, attachments)
    manifest_id = identifier()
    connection.execute("INSERT INTO manifests VALUES (?,?,?,?)",
                       (manifest_id, story_id, encode(resolved), now()))
    return manifest_id


def manifest_view(connection, manifest_id: str) -> list[dict]:
    attachments = attachments_at(connection, manifest_id)
    result = []
    for item in attachments:
        version = get_version(connection, item["version_id"])
        asset = one(connection, "SELECT * FROM assets WHERE id=?", (item["asset_id"],))
        result.append({**item, "version": version, "kind": asset["kind"],
                       "update_available": asset["latest_version_id"] != item["version_id"]})
    return result


def adopt_manifest(connection, story: dict, manifest_id: str, operation_id: str):
    connection.execute("UPDATE stories SET manifest_id=?,revision=revision+1,updated_at=? WHERE id=?",
                       (manifest_id, now(), story["id"]))
    connection.execute("UPDATE branches SET manifest_id=?,revision=revision+1 WHERE story_id=?",
                       (manifest_id, story["id"]))
    connection.execute("INSERT INTO adoptions VALUES (?,?,?,?,?,?)",
                       (identifier(), operation_id, story["id"], story["manifest_id"], manifest_id, now()))
