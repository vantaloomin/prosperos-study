from copy import deepcopy

from server.archives.cleanup import restore_cleanup
from server.archives.continuity_revision import remap_revision_usage
from server.archives.lore import remap_lore, remap_state
from server.archives.memory_controls import remap_controls
from server.archives.v07 import remap_manuscript
from server.database import decode, encode, identifier
from server.library_formats.sources import source_record
from server.mechanics.config import parse_settings
from server.prompts import builtin_prompt
from server.roles import ROLE_LABELS
from server.section_prompts import SECTION_LABELS

REFERENCES = {
    'source_branch_id', 'source_node_id', 'replacement_node_id', 'original_node_id',
    "id", "story_id", "asset_id", "latest_version_id", "manifest_id", "head_id", "parent_id", "forked_from",
    "fork_node_id", "operation_id", "old_manifest_id", "new_manifest_id", "profile_id", "generation_id",
    "accepted_branch_id", "accepted_node_id", "candidate_id", "branch_id", "node_id", "run_id", "job_id",
    "thread_id", "turn_id", "selected_reply_id", "head_key", "prompt_version_id", "version_id", "opportunity_id", "replaces",
    "from_node_id", "through_node_id", "reroll_of", "last_opportunity_id", 'triage_job_id',
    'scene_id', 'commit_id', 'proposal_job_id',
    'selected_job_id', 'assessment_id', 'assessment_job_id',
    'assessment_profile_id', 'assessment_prompt_version_id',
    'background_state_id', 'previous_id',
    'selected_state_id',
    'continuity_version_id', 'import_id', 'source_version_id', 'batch_id', 'memory_controls_version_id', 'knowledge_character_id',
}


def identities(data):
    ids = {row["id"] for table, rows in data.items() if table != "roll_tables" for row in rows if "id" in row}
    ids.update(row["operation_id"] for row in data["adoptions"])
    return {old: identifier() for old in ids}


def fields(value, mapping):
    return {key: mapping.get(item, item) if key in REFERENCES and isinstance(item, str) else item
            for key, item in value.items()}


def pins(values, mapping):
    return {key: mapping.get(value, value) for key, value in values.items()}


def settings(value, mapping):
    updated = fields(value, mapping)
    for key in ("step_profiles", "prompt_versions"):
        if key in value:
            updated[key] = pins(value[key], mapping)
    if value.get("primary_profile_id"):
        updated["primary_profile_id"] = mapping[value["primary_profile_id"]]
    if isinstance(value.get("randomness"), dict):
        updated["randomness"] = {**value["randomness"], "table_versions": pins(value["randomness"].get("table_versions", {}), mapping)}
    return updated


def story_settings(value, document, mapping):
    source = deepcopy(value)
    source["primary_profile_id"] = source.get("primary_profile_id") or document["primary_profile_id"]
    versions = {item['id']: item for item in document['data']['prompt_versions']}
    heads = {key: value for key, value in document['prompt_heads'].items()
             if key in ROLE_LABELS or key in SECTION_LABELS or not builtin_prompt(versions[value])}
    source["prompt_versions"] = {**heads, **source.get("prompt_versions", {})}
    randomness = parse_settings(source.get("randomness", {})).model_dump()
    heads = {row["id"]: row["version_id"] for row in document["data"]["roll_tables"]}
    randomness["table_versions"] = {**heads, **randomness["table_versions"]}
    source["randomness"] = randomness
    return settings(source, mapping)


def snapshot(value, mapping):
    updated = fields(value, mapping)
    updated.update({key: [fields(item, mapping) for item in value[key]] for key in ('prompt_sections',) if key in value})
    for key in ("branch", "prompt", "profile", 'cleanup'):
        if key in value:
            updated[key] = fields(value[key], mapping)
    updated.update(remap_snapshot_lore(value, mapping))
    if 'source_links' in value:
        updated['source_links'] = [remap_source_link(item, mapping) for item in value['source_links']]
    updated.update(remap_summary_links(value, mapping))
    if "settings" in value:
        updated["settings"] = settings({"randomness": value["settings"]}, mapping)["randomness"]
    if "tables" in value:
        updated["tables"] = {key: fields(table, mapping) for key, table in value["tables"].items()}
    if "upstream" in value:
        updated["upstream"] = scene_state(value["upstream"], mapping)
    if value.get("scene"):
        updated["scene"] = {**fields(value["scene"], mapping), "state": scene_state(value["scene"]["state"], mapping)}
    if 'review_job_ids' in value:
        updated['review_job_ids'] = [mapping[item] for item in value['review_job_ids']]
    if 'dialogue_actors' in value:
        updated['dialogue_actors'] = [snapshot(actor, mapping) for actor in value['dialogue_actors']]
    # Serialized provider inputs, cited source IDs, quotes, prose and source archives stay byte-for-byte intact.
    return updated


def remap_source_link(item, mapping):
    # id and frozen_* are receipts of the original provider bytes, not live references.
    keys = ('node_id',) if 'node_id' in item else ('asset_id', 'version_id')
    return {**item, **{key: mapping[item[key]] for key in keys}}


def remap_snapshot_lore(value, mapping):
    result = {key: remap_state(value[key], mapping) for key in ('before', 'after') if key in value}
    result.update({key: remap_lore(value[key], mapping) for key in ('lore', 'lore_context') if key in value})
    return result


def scene_state(value, mapping):
    updated = {**value, "selections": pins(value["selections"], mapping)}
    if value.get("gate_a"):
        updated["gate_a"] = scene_state(value["gate_a"], mapping)
    if 'verifications' in value:
        updated['verifications'] = pins(value['verifications'], mapping)
    if 'repair_selections' in value:
        updated['repair_selections'] = pins(value['repair_selections'], mapping)
    if value.get('gate_b'):
        updated['gate_b'] = fields(value['gate_b'], mapping)
    if value.get('accepted'):
        updated['accepted'] = fields(value['accepted'], mapping)
    if value.get('mechanics'):
        updated['mechanics'] = scene_chance(value['mechanics'], mapping)
    return updated


def scene_chance(value, mapping):
    updated = {**value, 'before': remap_state(value['before'], mapping), 'after': remap_state(value['after'], mapping)}
    updated['entries'] = [{**item, 'result': snapshot(item['result'], mapping)} for item in value['entries']]
    if value['inherited']:
        updated['inherited'] = {**fields(value['inherited'], mapping), 'result': snapshot(value['inherited']['result'], mapping)}
    return updated


def scene_decision(value, mapping):
    updated = fields(value, mapping)
    if "job_ids" in value:
        updated["job_ids"] = [mapping[item] for item in value["job_ids"]]
    return updated


def remap_json(table, row, document, mapping):
    converters = {
        'manuscripts': {'document': lambda value: remap_manuscript(value, mapping)},
        'memory_control_versions': {'payload': lambda value: remap_controls(value, mapping)},
        "stories": {"settings": lambda value: story_settings(value, document, mapping)},
        "asset_versions": {"content": lambda value: remap_dependencies(value, mapping)},
        "manifests": {"attachments": lambda value: [fields(item, mapping) for item in value]},
        "nodes": {"metadata": lambda value: fields(value, mapping)},
        "node_mechanics": {"state": lambda value: remap_state(value, mapping)},
        "candidates": {"profile": lambda value: fields(value, mapping), 'usage': lambda value: remap_revision_usage(value, mapping)},
        'generation_attempts': {'usage': lambda value: remap_revision_usage(value, mapping)},
        "side_replies": {"profile": lambda value: fields(value, mapping)},
        "review_runs": {"selections": lambda value: pins(value, mapping)},
        "scene_runs": {"state": lambda value: scene_state(value, mapping)},
        "scene_decisions": {"payload": lambda value: scene_decision(value, mapping)},
    }
    updated = dict(row)
    for field, convert in converters.get(table, {}).items():
        updated[field] = encode(convert(decode(row[field])))
    if "snapshot" in row:
        updated["snapshot"] = encode(snapshot(decode(row["snapshot"]), mapping))
    if table == 'assessment_runs':
        updated['snapshot'] = encode(assessment_snapshot(decode(row['snapshot']), mapping))
    if table == 'background_states':
        updated['snapshot'] = encode(background_snapshot(decode(row['snapshot']), mapping))
    return updated


def remap_dependencies(value, mapping):
    if "lorebook_versions" not in value:
        return value
    return {**value, "lorebook_versions": [mapping[item] for item in value["lorebook_versions"]]}


def remap_record(table, row, document, mapping):
    if table == 'archive_identities':
        return {**row, 'record_id': mapping[row['record_id']]}
    if table == 'asset_sources' and row['format'] == 'legacy-metadata':
        version = next(item for item in document['data']['asset_versions'] if item['id'] == row['version_id'])
        return source_record({**version, 'id': mapping[version['id']], 'content': remap_dependencies(decode(version['content']), mapping)})
    updated = fields(row, mapping)
    updated = remap_json(table, updated, document, mapping)
    if table in {"candidates", "review_jobs", "side_replies", "scene_jobs", 'assessment_jobs', 'background_jobs', 'authoring_jobs', 'summary_jobs', 'relationship_jobs'} and row["status"] in {"running", "queued"}:
        updated["status"] = "interrupted"
        updated["error"] = "Restored from an archive. Partial output is preserved; retry is explicit."
    if table == 'summary_batches' and row['status'] in {'queued', 'running'}:
        updated.update(status='interrupted', error='Restored maintenance waits for explicit resume.')
    if table == 'summary_wakeups' and row['status'] == 'pending':
        updated.update(status='interrupted', error='Restored automatic maintenance waits for explicit resume.')
    return restore_cleanup(table, row, updated)


def assessment_snapshot(value, mapping):
    updated = snapshot(value, mapping)
    updated['writer_snapshot'] = snapshot(value['writer_snapshot'], mapping)
    updated['writer_profiles'] = [fields(profile, mapping) for profile in value['writer_profiles']]
    updated['request'] = {**value['request'],
                          'profile_ids': [mapping[item] for item in value['request']['profile_ids']],
                          'assessment_profile_ids': [mapping[item] for item in value['request']['assessment_profile_ids']]}
    return updated


def background_snapshot(value, mapping):
    updated = snapshot(value, mapping)
    updated['recipe'] = {**value['recipe'], 'characters': [fields(item, mapping) for item in value['recipe']['characters']]}
    result = snapshot(value['result'], mapping)
    result['drives'] = [{**item, 'character': fields(item['character'], mapping)} for item in result['drives']]
    updated['result'] = result
    if value.get('interpretation'):
        updated['interpretation'] = fields(value['interpretation'], mapping)
    return updated


def remap_summary_links(value, mapping):
    return {key: [{**link, 'version_id': mapping[link['version_id']], 'node_id': mapping[link['node_id']]}
                  for link in value[key]] for key in ('summary_links', 'summary_aid_links') if key in value}
