from server.database import one
from server.errors import require
from server.library import get_version, publish_asset
from server.models import AssetPublish
from server.prompts import ALL_PROMPT_LABELS, AUTHORING_KEYS, original_prompt, publish_prompt
from server.text_edits.fields import changed_content, field_options, field_text
from server.text_edits.models import TextTarget
from server.writing.models import ResourceCreate
from server.writing.resources import insert_version as insert_writing_version
from server.writing.resources import version as writing_version

VERSIONED_KINDS = {'library-field', 'writing-field', 'prompt'}


def workspace_id(connection):
    return one(connection, "SELECT value FROM preferences WHERE key='text_edit_workspace_id'")['value']


def validate_prompt_target(ref):
    require(ref.prompt_key in ALL_PROMPT_LABELS, 'Unknown prompt role.', 404)
    require(ref.prompt_scope != 'story' or ref.prompt_key not in AUTHORING_KEYS | {'library-assist'}, 'Library assistant instructions belong to the workspace.')


def current_version(connection, ref):
    if ref.kind == 'prompt':
        validate_prompt_target(ref)
        if ref.prompt_scope == 'workspace':
            require(ref.workspace_id == workspace_id(connection), 'This workspace prompt target was restored from an archive. Start a new edit in the current prompt editor to choose its scope.', 409)
        story = one(connection, 'SELECT * FROM stories WHERE id=?', (ref.story_id,)) if ref.prompt_scope == 'story' else None
        return {**original_prompt(connection, ref.prompt_key, story), 'kind': 'prompt'}
    table = 'assets' if ref.kind == 'library-field' else 'writing_assets'
    asset = one(connection, f'SELECT * FROM {table} WHERE id=?', (ref.asset_id,))
    return saved_version(connection, ref, asset['latest_version_id'])


def saved_version(connection, ref, identity):
    if ref.kind == 'prompt':
        validate_prompt_target(ref)
        row = one(connection, 'SELECT * FROM prompt_versions WHERE id=?', (identity,))
        require(row['key'] == ref.prompt_key, 'A text target names another prompt role.')
        return {**row, 'kind': 'prompt'}
    if ref.kind == 'library-field':
        row = get_version(connection, identity)
        row['kind'] = one(connection, 'SELECT kind FROM assets WHERE id=?', (ref.asset_id,))['kind']
    else:
        row = writing_version(connection, identity)
    require(row['asset_id'] == ref.asset_id, 'A text target points to another Library resource.')
    return row


def edition_snapshot(ref, edition):
    from server.text_edits.targets import snapshot
    if ref.kind == 'prompt':
        text, limit = edition['template'], 100000
        label = f"{ALL_PROMPT_LABELS.get(ref.prompt_key, ref.prompt_key)} · {ref.prompt_scope} instructions"
    else:
        text, limit = field_text(edition['kind'], ref, edition['content'])
        label = f"{edition['name']} · {ref.field}" + (f' · {ref.item_id}' if ref.item_id else '')
    return snapshot(ref, {'revision': edition['number'], 'version_id': edition['id'], 'asset_kind': edition['kind']}, text, label, limit)


def publish_field(connection, database, ref, text):
    current = current_version(connection, ref)
    if ref.kind == 'prompt':
        saved = publish_prompt(connection, ref.prompt_key, current['id'], text, ref.story_id if ref.prompt_scope == 'story' else None)
        return ref, {'prompt_version_id': saved['id'], 'prompt_key': ref.prompt_key, 'prompt_scope': ref.prompt_scope}
    content = changed_content(current['kind'], ref, current['content'], text)
    if ref.kind == 'library-field':
        require(database is not None, 'The Library publisher is unavailable.', 503)
        saved = publish_asset(connection, database, ref.asset_id, AssetPublish(expected_version_id=current['id'],
            name=current['name'], content=content, note='Scoped text edit.'))
    else:
        body = ResourceCreate(operation_id='text-edit-publication', kind=current['kind'], name=current['name'],
            description=current['description'], content=content, note='Scoped text edit.', unsupported=current['unsupported'])
        saved = insert_writing_version(connection, ref.asset_id, body, current['number'] + 1)
    return ref, {'asset_id': ref.asset_id, 'version_id': saved['id']}


def target_catalog(connection, body):
    one(connection, 'SELECT id FROM stories WHERE id=?', (body.story_id,))
    base = {'kind': body.kind, 'story_id': body.story_id}
    if body.kind == 'prompt':
        require(body.asset_id is None and body.prompt_key and body.prompt_scope, 'Choose an explicit prompt scope and role.')
        base.update(prompt_key=body.prompt_key, prompt_scope=body.prompt_scope)
        if body.prompt_scope == 'workspace':
            base['workspace_id'] = workspace_id(connection)
        ref = TextTarget.model_validate(base)
        current = current_version(connection, ref)
        options = [{'ref': ref.model_dump(exclude_none=True), 'label': 'Role instructions'}]
        name = ALL_PROMPT_LABELS[body.prompt_key]
    else:
        require(body.asset_id and body.prompt_key is None and body.prompt_scope is None, 'Choose a Library resource.')
        base.update(asset_id=body.asset_id)
        current = current_version(connection, TextTarget.model_validate({**base, 'field': 'text'}))
        options = [{'ref': {**base, 'field': field, **({'item_id': item} if item else {})}, 'label': label}
                   for field, item, label in field_options(current['kind'], current['content'])]
        name = current['name']
    return {'version_id': current['id'], 'number': current['number'], 'name': name, 'options': options}
