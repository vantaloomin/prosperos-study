from hashlib import sha256

from server.database import decode, encode, one
from server.errors import require
from server.lore.documents import normalize_lore
from server.text_edits.fields import changed_content
from server.text_edits.models import TextTarget
from server.text_edits.targets import snapshot_version
from server.text_edits.versioned import edition_snapshot, saved_version
from server.writing.resources import parse_content


def target_snapshots(data):
    for row in data.get('recipe_runs', []):
        yield decode(row['target'])
    for row in data.get('companion_edit_origins', []):
        yield decode(row['detail'])['target']
    for row in data.get('side_contexts', []):
        target = decode(row['snapshot'])['target']
        if target['kind'] == 'text':
            yield target['snapshot']
    for row in data['text_edit_proposals']:
        yield decode(row['target'])
    for row in data['text_edit_receipts']:
        yield decode(row['before_target'])
        yield decode(row['after_target'])


def version_references(data, kind):
    return {target['basis']['version_id'] for target in target_snapshots(data) if target['ref']['kind'] == kind}


def asset_references(data):
    return {target['ref']['asset_id'] for target in target_snapshots(data) if target['ref']['kind'] == 'library-field'}


def validate_edition_snapshot(connection, ref, value):
    edition = saved_version(connection, ref, value['basis'].get('version_id'))
    expected = edition_snapshot(ref, edition)
    require(all(value[key] == expected[key] for key in ('basis', 'text', 'limit')), 'A versioned text snapshot disagrees with its immutable edition.')


def validate_edition_result(connection, receipt):
    before, after = receipt['before_target'], receipt['after_target']
    require(before['ref'] == after['ref'], 'A versioned text edit changed its destination.')
    ref = TextTarget.model_validate(before['ref'])
    source = saved_version(connection, ref, before['basis']['version_id'])
    revised = saved_version(connection, ref, after['basis']['version_id'])
    require(revised['number'] > source['number'], 'A text edit must publish a newer edition.')
    if ref.kind == 'prompt':
        expected = {'prompt_version_id': revised['id'], 'prompt_key': ref.prompt_key, 'prompt_scope': ref.prompt_scope}
    else:
        require(revised['number'] == source['number'] + 1 and revised['name'] == source['name'], 'A field edit changed its resource name or version sequence.')
        expected_content = changed_content(source['kind'], ref, source['content'], after['text'])
        if ref.kind == 'writing-field':
            expected_content = parse_content(source['kind'], expected_content)
            require(source['description'] == revised['description'] and source['unsupported'] == revised['unsupported'], 'A text edit changed other writing-resource metadata.')
        elif source['kind'] == 'lorebook':
            expected_content = normalize_lore(expected_content)
        require(revised['content'] == expected_content, 'A field edit changed content outside its selected text target.')
        expected = {'asset_id': ref.asset_id, 'version_id': revised['id']}
    require(receipt['result'] == expected, 'A published text result disagrees with its edition.')


def restored_target(ref, mapping):
    # Imported workspace defaults must never acquire authority over the host's
    # global prompt head, including when restoring into the original workspace.
    if ref.get('workspace_id'):
        fingerprint = (mapping[ref['story_id']] + ':' + ref['workspace_id']).encode()
        return {**ref, 'workspace_id': 'restored:' + sha256(fingerprint).hexdigest()[:32]}
    return ref


def bind_restored_editions(connection, table, row):
    result = dict(row)
    for key in ('target',) if table == 'text_edit_proposals' else ('before_target', 'after_target'):
        target = decode(row[key])
        if target['ref']['kind'] == 'prompt':
            edition = one(connection, 'SELECT number FROM prompt_versions WHERE id=?', (target['basis']['version_id'],))
            target['basis']['revision'] = edition['number']
            target['version'] = snapshot_version(target)
            result[key] = encode(target)
    return result
