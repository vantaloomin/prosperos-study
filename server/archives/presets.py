from server.archives.format import PRESET_TABLES, V52_TABLES
from server.archives.records import related_rows
from server.database import decode, one
from server.errors import require
from server.migration.preset_conversion import literal_instructions
from server.migration.preset_models import PresetUpload
from server.migration.presets import retained_proposals, validated_preset
from server.writing.extras import read_extras
from server.writing.resources import parse_content


def collect_presets(connection, data):
    data['preset_origins'] = related_rows(connection, 'preset_origins', 'version_id', {row['id'] for row in data['writing_versions']})
    data['preset_imports'] = related_rows(connection, 'preset_imports', 'id', {row['import_id'] for row in data['preset_origins']})


def preset_profiles(data):
    return {row[key] for row in data['preset_origins'] for key in ('profile_id', 'base_profile_id') if row[key]}


def validate_presets(connection, data):
    for row in data['preset_imports']:
        upload = PresetUpload(filename=row['filename'], source_base64=row['source_base64'])
        conversion = validated_preset(upload.filename, upload.source_base64)
        require(decode(row['conversion']) == conversion and all(row[key] == conversion[key] for key in ('source_sha256', 'content_sha256')),
                'An imported preset report does not match the exact source.')
    for row in data['preset_origins']:
        validate_origin(connection, row)


def validate_origin(connection, row):
    source = one(connection, 'SELECT * FROM preset_imports WHERE id=?', (row['import_id'],))
    version = one(connection, 'SELECT v.*,a.kind FROM writing_versions v JOIN writing_assets a ON a.id=v.asset_id WHERE v.id=?', (row['version_id'],))
    conversion, receipt = decode(source['conversion']), decode(row['receipt'])
    require(set(receipt) == {'version', 'source_sha256', 'name', 'instructions', 'instruction_keys', 'sampling_keys', 'configuration_changes', 'base_profile_name'}
            and receipt['version'] == 1 and receipt['source_sha256'] == source['source_sha256'], 'A preset receipt has an invalid source or shape.')
    keys = receipt['instruction_keys']
    require(isinstance(keys, list) and len(keys) == len(set(keys)) and set(keys) <= {item['key'] for item in conversion['instructions'] if item['supported']},
            'A preset receipt names unavailable instruction fragments.')
    require(version['kind'] == 'recipe' and version['name'] == receipt['name']
            and decode(version['content']) == parse_content('recipe', {'instructions': literal_instructions(receipt['instructions'])})
            and read_extras(connection, row['version_id']) == retained_proposals(conversion), 'An imported recipe does not match its reviewed preset receipt.')
    validate_configuration(connection, row, receipt, conversion)


def validate_configuration(connection, row, receipt, conversion):
    keys = receipt['sampling_keys']
    available = {item['target']: item['value'] for item in conversion['sampling'] if item['supported']}
    require(isinstance(keys, list) and len(keys) == len(set(keys)) and set(keys) <= set(available), 'Invalid preset sampling selections.')
    links = ('profile_id', 'profile_version_id', 'base_profile_id', 'base_profile_version_id')
    if not keys:
        require(all(row[key] is None for key in links) and decode(row['configuration']) is None
                and receipt['configuration_changes'] == [] and receipt['base_profile_name'] == '', 'An unapplied sampling proposal has live configuration links.')
        return
    require(all(row[key] for key in links) and row['profile_id'] != row['base_profile_id'], 'Preset sampling must create a separate model profile.')
    base = one(connection, 'SELECT * FROM profile_versions WHERE id=?', (row['base_profile_version_id'],))
    copied = one(connection, 'SELECT * FROM profile_versions WHERE id=?', (row['profile_version_id'],))
    old, config = decode(base['config']), decode(copied['config'])
    changes = [{'field': key, 'before': old.get(key), 'after': available[key]} for key in keys]
    require(base['profile_id'] == row['base_profile_id'] and copied['profile_id'] == row['profile_id']
            and copied['credential_ref'] is None and config == decode(row['configuration'])
            and config == {**old, **{key: available[key] for key in keys}}
            and receipt['configuration_changes'] == changes and receipt['base_profile_name'] == base['name'],
            'Preset configuration does not match the chosen local profile version and reviewed changes.')


def upgrade_presets(document):
    if document['version'] == 52:
        require(set(document['data']) == set(V52_TABLES), 'Version 52 needs its original record groups.')
        document['data'].update({table: [] for table in PRESET_TABLES})
        document['version'] = 53
    return document
