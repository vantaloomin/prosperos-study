from server.database import decode, encode, identifier, many, now, one
from server.errors import DomainError, require
from server.library_formats.import_conversion import source_bytes
from server.migration.preset_configuration import configuration_proposal, copy_configuration
from server.migration.preset_conversion import convert_preset, literal_instructions
from server.operations import previous, remember
from server.writing.models import ResourceCreate
from server.writing.resources import create_in, insert_version, parse_content, version


def validated_preset(filename, encoded):
    try:
        return convert_preset(filename, source_bytes(encoded))
    except (ValueError, UnicodeError) as error:
        raise DomainError(str(error), 400) from error


def preset_duplicates(connection, source):
    rows = many(connection, 'SELECT v.id AS version_id,v.asset_id,v.name,i.source_sha256 FROM preset_origins o '
                'JOIN writing_versions v ON v.id=o.version_id JOIN preset_imports i ON i.id=o.import_id '
                'WHERE i.source_sha256=? OR i.content_sha256=? ORDER BY o.created_at DESC,v.id LIMIT 100',
                (source['source_sha256'], source['content_sha256']))
    return [{**row, 'match': 'exact-source' if row['source_sha256'] == source['source_sha256'] else 'proposal-content'} for row in rows]


def retained_proposals(conversion):
    return {'foreign_preset': {'format': conversion['format'], 'sampling_proposals': conversion['sampling'],
                              'source_fields': conversion['source_fields'], 'parameter_fields': conversion['parameter_fields'],
                              'handling': 'Reference only. Sampling and foreign runtime settings do not run with this recipe.'}}


def validate_publication(connection, row, body):
    conversion = decode(row['conversion'])
    require(row['source_sha256'] == body.source_sha256, 'The preset source changed. Reopen its preview.', 409)
    keys = body.instruction_keys
    candidates = {item['key'] for item in conversion['instructions'] if item['supported']}
    require(len(keys) == len(set(keys)) and set(keys) <= candidates, 'Choose supported instruction fragments once each.')
    content = parse_content('recipe', {'instructions': literal_instructions(body.instructions)})
    configuration = configuration_proposal(connection, conversion, body)
    if body.target_asset_id:
        asset = one(connection, 'SELECT * FROM writing_assets WHERE id=?', (body.target_asset_id,))
        require(asset['kind'] == 'recipe', 'A preset can publish only a recipe version.')
        require(body.expected_version_id is not None and asset['latest_version_id'] == body.expected_version_id,
                'The target recipe changed. Choose its current version.', 409)
    else:
        require(body.expected_version_id is None, 'Choose a recipe identity before requesting a version update.')
    return conversion, content, configuration


def publish_preset(connection, database, row, body):
    conversion, content, proposal = validate_publication(connection, row, body)
    matches = preset_duplicates(connection, row)
    if matches and body.duplicate_action == 'skip' and not body.target_asset_id:
        return {'status': 'skipped', 'duplicates': matches}
    profile = copy_configuration(connection, database, proposal, body.name)
    resource = ResourceCreate(operation_id=body.operation_id, kind='recipe', name=body.name, content=content,
                              description='Reviewed foreign preset; retained sampling proposals are separate from recipe instructions.',
                              note='Published from a reviewed foreign preset', unsupported=retained_proposals(conversion))
    if body.target_asset_id:
        current = version(connection, body.expected_version_id, 'recipe')
        saved = insert_version(connection, body.target_asset_id, resource, current['number'] + 1)
    else:
        saved = create_in(connection, resource)
    receipt = {'version': 1, 'source_sha256': row['source_sha256'], 'name': body.name,
               'instructions': body.instructions, 'instruction_keys': body.instruction_keys,
               'sampling_keys': body.sampling_keys, 'configuration_changes': proposal['changes'], 'base_profile_name': proposal['base_name']}
    connection.execute('INSERT INTO preset_origins VALUES (?,?,?,?,?,?,?,?,?)',
                       (saved['id'], row['id'], profile['profile_id'] if profile else None, profile['id'] if profile else None,
                        body.base_profile_id, body.expected_profile_version_id, encode(receipt), encode(profile['config']) if profile else 'null', now()))
    return {'status': 'imported', 'resource': saved, 'profile': profile,
            'activation': 'The recipe and any model-profile copy are saved only. Choose them explicitly when writing. Model credentials were not copied.'}


class PresetImports:
    def __init__(self, database):
        self.database = database

    def list(self):
        with self.database.connect() as connection:
            return many(connection, 'SELECT i.id,i.filename,i.created_at,COUNT(o.version_id) AS published_versions '
                        'FROM preset_imports i LEFT JOIN preset_origins o ON o.import_id=i.id GROUP BY i.id ORDER BY i.created_at DESC LIMIT 100')

    def stage(self, body):
        conversion = validated_preset(body.filename, body.source_base64)
        row = {'id': identifier(), 'filename': body.filename, 'source_base64': body.source_base64,
               'source_sha256': conversion['source_sha256'], 'content_sha256': conversion['content_sha256'],
               'conversion': encode(conversion), 'created_at': now()}
        with self.database.connect(write=True) as connection:
            connection.execute('INSERT INTO preset_imports VALUES (?,?,?,?,?,?,?)', tuple(row.values()))
        return self.view(row['id'])

    def row(self, import_id):
        with self.database.connect() as connection:
            return one(connection, 'SELECT * FROM preset_imports WHERE id=?', (import_id,))

    def view(self, import_id):
        with self.database.connect() as connection:
            row = one(connection, 'SELECT * FROM preset_imports WHERE id=?', (import_id,))
            return {**{key: row[key] for key in ('id', 'filename', 'created_at')}, **decode(row['conversion']),
                    'duplicates': preset_duplicates(connection, row)}

    def configure(self, import_id, body):
        with self.database.connect() as connection:
            row = one(connection, 'SELECT * FROM preset_imports WHERE id=?', (import_id,))
            return configuration_proposal(connection, decode(row['conversion']), body)

    def origins(self, version_id):
        with self.database.connect() as connection:
            return [{**row, 'receipt': decode(row['receipt'])} for row in many(connection,
                    'SELECT o.version_id,o.import_id,o.profile_id,o.profile_version_id,o.receipt,i.filename FROM preset_origins o '
                    'JOIN preset_imports i ON i.id=o.import_id WHERE o.version_id=?', (version_id,))]

    def publish(self, import_id, body):
        payload = {'import_id': import_id, **body.model_dump(exclude={'operation_id'})}
        with self.database.connect(write=True) as connection:
            saved = previous(connection, body.operation_id, 'preset-import', payload)
            if saved is not None:
                return saved
            row = one(connection, 'SELECT * FROM preset_imports WHERE id=?', (import_id,))
            result = publish_preset(connection, self.database, row, body)
            return remember(connection, body.operation_id, 'preset-import', payload, result)
