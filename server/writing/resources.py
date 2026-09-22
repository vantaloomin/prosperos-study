from pydantic import ValidationError

from server.database import decode, encode, identifier, many, now, one
from server.errors import DomainError, require
from server.operations import previous, remember
from server.writing.extras import read_extras, save_extras
from server.writing.models import RecipeContent, StyleContent
from server.writing.variables import names_in, value_for


def parse_content(kind, content):
    try:
        model = StyleContent if kind == 'style' else RecipeContent
        value = model.model_validate(content)
    except ValidationError as error:
        raise DomainError('; '.join(item['msg'] for item in error.errors()), 400) from None
    if kind == 'recipe':
        validate_recipe(value)
    return value.model_dump()


def validate_recipe(value):
    from server.mechanics.config import parse_settings
    from server.prompts import ALL_PROMPT_LABELS
    from server.roles import BLIND_LENSES, INFORMED_LENSES
    names = {item.name for item in value.variables}
    for text in [value.instructions, *(step.instructions for step in value.steps)]:
        require(names_in(text) <= names, 'The recipe references an undeclared variable.')
    for item in value.variables:
        if item.default is not None:
            value_for(item, item.default)
    require(set(value.disabled_tasks) <= set(ALL_PROMPT_LABELS), 'Unknown recipe task switch.')
    for step in value.steps:
        require(set(step.lenses) <= set(BLIND_LENSES) | set(INFORMED_LENSES), 'Unknown review lens.')
        require(step.task == 'review' or not step.lenses, 'Review lenses apply only to review steps.')
    if value.randomness is not None:
        parse_settings(value.randomness)


def version(connection, version_id, kind=None):
    row = one(connection, 'SELECT v.*,a.kind,a.archived,a.revision FROM writing_versions v '
              'JOIN writing_assets a ON a.id=v.asset_id WHERE v.id=?', (version_id,))
    require(kind is None or row['kind'] == kind, f'Choose a {kind} version.')
    return {**row, 'content': decode(row['content']), 'unsupported': read_extras(connection, version_id)}


def validate_links(connection, kind, content):
    if kind != 'recipe':
        return
    if content['style'] not in {'inherit', 'none'}:
        version(connection, content['style'], 'style')
    for step in content['steps']:
        if step['profile_id']:
            one(connection, 'SELECT id FROM profiles WHERE id=?', (step['profile_id'],))
    if content['randomness'] is not None:
        from server.mechanics.config import configured_tables, parse_settings
        configured_tables(connection, parse_settings(content['randomness']))


def insert_version(connection, asset_id, body, number):
    content = parse_content(body.kind, body.content)
    validate_links(connection, body.kind, content)
    identity = identifier()
    connection.execute('INSERT INTO writing_versions VALUES (?,?,?,?,?,?,?,?)',
                       (identity, asset_id, number, body.name, body.description,
                        encode(content), body.note, now()))
    connection.execute('UPDATE writing_assets SET latest_version_id=? WHERE id=?', (identity, asset_id))
    save_extras(connection, identity, body.unsupported)
    return version(connection, identity)


def create_in(connection, body):
    identity = identifier()
    connection.execute('INSERT INTO writing_assets VALUES (?,?,NULL,0,0,?)', (identity, body.kind, now()))
    return insert_version(connection, identity, body, 1)


def resource_payload(body):
    value = body.model_dump()
    if 'unsupported' not in body.model_fields_set:
        value.pop('unsupported')
    return value


class Resources:
    def __init__(self, database):
        self.database = database

    def list(self, include_archived=False):
        with self.database.connect() as connection:
            rows = many(connection, 'SELECT latest_version_id FROM writing_assets '
                        'WHERE archived=0 OR ? ORDER BY created_at,id', (include_archived,))
            return [version(connection, row['latest_version_id']) for row in rows]

    def create(self, body):
        payload = resource_payload(body)
        with self.database.connect(write=True) as connection:
            saved = previous(connection, body.operation_id, 'writing-resource-create', payload)
            if saved is not None:
                return saved
            result = create_in(connection, body)
            return remember(connection, body.operation_id, 'writing-resource-create', payload, result)

    def publish(self, asset_id, body):
        payload = {'asset_id': asset_id, **resource_payload(body)}
        with self.database.connect(write=True) as connection:
            saved = previous(connection, body.operation_id, 'writing-resource-publish', payload)
            if saved is not None:
                return saved
            asset = one(connection, 'SELECT * FROM writing_assets WHERE id=?', (asset_id,))
            require(asset['latest_version_id'] == body.expected_version_id,
                    'A newer version exists. Reopen the editor before publishing.', 409)
            require(asset['kind'] == body.kind, 'A resource cannot change its kind.')
            current = version(connection, asset['latest_version_id'])
            if 'unsupported' not in body.model_fields_set:
                body = body.model_copy(update={'unsupported': current['unsupported']})
            result = insert_version(connection, asset_id, body, current['number'] + 1)
            return remember(connection, body.operation_id, 'writing-resource-publish', payload, result)

    def history(self, asset_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM writing_assets WHERE id=?', (asset_id,))
            return [version(connection, row['id']) for row in many(connection,
                    'SELECT id FROM writing_versions WHERE asset_id=? ORDER BY number DESC', (asset_id,))]

    def archive(self, asset_id, body):
        payload = {'asset_id': asset_id, **body.model_dump()}
        with self.database.connect(write=True) as connection:
            saved = previous(connection, body.operation_id, 'writing-resource-archive', payload)
            if saved is not None:
                return saved
            asset = one(connection, 'SELECT * FROM writing_assets WHERE id=?', (asset_id,))
            require(asset['revision'] == body.expected_revision, 'This resource changed. Refresh first.', 409)
            connection.execute('UPDATE writing_assets SET archived=?,revision=revision+1 WHERE id=?',
                               (body.archived, asset_id))
            result = version(connection, asset['latest_version_id'])
            return remember(connection, body.operation_id, 'writing-resource-archive', payload, result)
