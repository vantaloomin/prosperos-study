"""Compare source proposals, never use a display name as an update identity."""
import json
from hashlib import sha256

from server.database import decode


def proposal_hash(draft):
    # Names and unsupported source metadata can differ. This is proposal equality,
    # not a claim that previously edited/published resources are interchangeable.
    value = [draft['part'], draft['content']]
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def import_duplicates(connection, source):
    proposals = {draft['part']: proposal_hash(draft) for draft in decode(source['conversion'])['drafts']}
    cursor = connection.execute('SELECT o.part,v.id AS version_id,v.asset_id,v.name,i.source_sha256,'
                                "json_extract(i.conversion,'$.drafts') AS drafts FROM asset_import_origins o "
                                'JOIN asset_versions v ON v.id=o.version_id JOIN library_imports i ON i.id=o.import_id '
                                'ORDER BY i.created_at DESC,v.id')
    result = []
    counts = dict.fromkeys(proposals, 0)
    for row in cursor:
        part = row['part']
        match = match_import(row, proposals, source['source_sha256'])
        if match and counts[part] < 50:
            result.append({key: row[key] for key in ('part', 'version_id', 'asset_id', 'name')} |
                          {'match': match})
            counts[part] += 1
        if all(count >= 50 for count in counts.values()):
            break
    return result


def match_import(row, proposals, source_hash):
    if row['part'] not in proposals:
        return None
    if row['source_sha256'] == source_hash:
        return 'exact-source'
    original = next((draft for draft in decode(row['drafts']) if draft['part'] == row['part']), None)
    return 'proposal-content' if original is not None and proposal_hash(original) == proposals[row['part']] else None


def split_duplicates(connection, row, choices):
    matches = import_duplicates(connection, row)
    selected, skipped = [], []
    for choice in choices:
        duplicates = [item for item in matches if item['part'] == choice.part]
        if duplicates and choice.duplicate_action == 'skip' and not choice.target_asset_id:
            skipped.append({'part': choice.part, 'duplicates': duplicates})
        else:
            selected.append(choice)
    return selected, skipped


def publication_payload(import_id, body):
    payload = {'import_id': import_id, **body.model_dump(exclude={'operation_id'})}
    # Preserve operation fingerprints of requests made before duplicate review.
    for original, choice in zip(body.choices, payload['choices'], strict=True):
        if 'duplicate_action' not in original.model_fields_set:
            choice.pop('duplicate_action')
    return payload
