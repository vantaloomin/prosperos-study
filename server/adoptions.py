from server.adoption_plan import build_preview
from server.database import Database, one
from server.errors import require
from server.manifests import adopt_manifest, create_manifest
from server.models import AdoptionApply
from server.operations import previous, remember


def target_signature(targets: list[dict]) -> set[tuple]:
    return {(t["story_id"], t["expected_revision"], t["manifest_id"]) for t in targets}


class Adoptions:
    def __init__(self, database: Database):
        self.database = database

    def preview(self, version_id: str, additional_ids=()) -> dict:
        with self.database.connect() as connection:
            return build_preview(connection, version_id, additional_ids)

    def apply(self, version_id: str, body: AdoptionApply) -> dict:
        payload = {"version_id": version_id, **body.model_dump(exclude_defaults=True)}
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, "adopt", payload)
            if cached is not None:
                return cached
            preview = build_preview(connection, version_id, body.additional_version_ids)
            current = preview['targets']
            expected = [t.model_dump() for t in body.targets]
            require(target_signature(current) == target_signature(expected),
                    "The affected stories have changed. Refresh the update preview.", 409)
            require(len(expected) == len(current), "Duplicate targets are not allowed.")
            require(preview['can_apply'], 'Linked versions conflict. Resolve every listed conflict before updating.')
            validate_preview(body, preview)
            changed = [t for t in current if t["changed"]]
            for target in changed:
                self._apply_story(connection, target, body.operation_id)
            return remember(connection, body.operation_id, "adopt", payload, {"updated": len(changed)})

    @staticmethod
    def _apply_story(connection, target, operation_id):
        story_id = target['story_id']
        story = one(connection, "SELECT * FROM stories WHERE id=?", (story_id,))
        manifest_id = create_manifest(connection, story_id, target['attachments'])
        adopt_manifest(connection, story, manifest_id, operation_id)


def validate_preview(body, preview):
    dependent = any(change['reason'] == 'dependency' for target in preview['targets'] for change in target['changes'])
    needs_review = bool(body.additional_version_ids) or dependent or body.preview_hash is not None
    require(not needs_review or body.preview_hash == preview['preview_hash'],
            'Review the linked changes again before applying this update.', 409)
