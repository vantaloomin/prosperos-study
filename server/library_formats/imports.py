from hashlib import sha256

from server.character_content import canonical_kind
from server.database import decode, encode, identifier, many, now, one
from server.errors import DomainError, require
from server.library import create_asset, publish_asset
from server.library_formats.artwork import store_artwork
from server.library_formats.container_assets import imported_artwork
from server.library_formats.import_conversion import convert_import, source_bytes
from server.library_formats.import_duplicates import (
    import_duplicates,
    publication_payload,
    split_duplicates,
)
from server.library_formats.import_files import materialize_import
from server.models import AssetCreate, AssetPublish
from server.operations import previous, remember


def preview(row):
    conversion = decode(row['conversion'])
    return {key: row[key] for key in ('id', 'filename', 'source_sha256', 'created_at')} | {
        **{key: conversion[key] for key in ('format', 'card_version', 'issues', 'drafts')},
        **{key: conversion[key] for key in ('source_format', 'format_label', 'mapping', 'assets') if key in conversion},
        'files': [{'path': path, 'characters': len(text)} for path, text in conversion['files'].items()]}


def validated_conversion(filename, encoded):
    try:
        return convert_import(filename, source_bytes(encoded))
    except (ValueError, UnicodeError) as error:
        raise DomainError(str(error), 400) from error


class LibraryImports:
    def __init__(self, database):
        self.database = database

    def stage(self, body):
        conversion = validated_conversion(body.filename, body.source_base64)
        artwork = imported_artwork(source_bytes(body.source_base64), conversion)
        row = {'id': identifier(), 'filename': body.filename, 'source_base64': body.source_base64,
               'source_sha256': conversion['source_sha256'], 'conversion': encode(conversion), 'created_at': now()}
        materialize_import(self.database, row, conversion)
        with self.database.connect(write=True) as connection:
            for image in artwork:
                store_artwork(connection, image)
            connection.execute('INSERT INTO library_imports VALUES (?,?,?,?,?,?)', tuple(row.values()))
        return self.view(row['id'])

    def row(self, import_id):
        with self.database.connect() as connection:
            return one(connection, 'SELECT * FROM library_imports WHERE id=?', (import_id,))

    def view(self, import_id):
        with self.database.connect() as connection:
            row = one(connection, 'SELECT * FROM library_imports WHERE id=?', (import_id,))
            return {**preview(row), 'duplicates': import_duplicates(connection, row)}

    def origins(self, version_id):
        with self.database.connect() as connection:
            one(connection, 'SELECT id FROM asset_versions WHERE id=?', (version_id,))
            return many(connection, 'SELECT i.id,i.filename,i.source_sha256,i.created_at,o.part '
                        'FROM asset_import_origins o JOIN library_imports i ON i.id=o.import_id WHERE o.version_id=? ORDER BY i.created_at', (version_id,))

    def publish(self, import_id, body):
        payload = publication_payload(import_id, body)
        with self.database.connect(write=True) as connection:
            cached = previous(connection, body.operation_id, 'library-import', payload)
            if cached is not None:
                return cached
            row = one(connection, 'SELECT * FROM library_imports WHERE id=?', (import_id,))
            conversion = decode(row['conversion'])
            validate_choices(row, conversion, body)
            materialize_import(self.database, row, conversion)
            selected, skipped = split_duplicates(connection, row, body.choices)
            versions = publish_choices(connection, self.database, row, selected)
            return remember(connection, body.operation_id, 'library-import', payload, {'versions': versions, 'skipped': skipped})


def validate_choices(row, conversion, body):
    require(body.reviewed_compatibility, 'Review the compatibility notes before publishing.')
    require(row['source_sha256'] == body.source_sha256 == sha256(source_bytes(row['source_base64'])).hexdigest(),
            'The source does not match this preview. Choose the file again.', 409)
    parts = [choice.part for choice in body.choices]
    require(len(set(parts)) == len(parts), 'Choose each imported item once.')
    require(set(parts) <= {item['part'] for item in conversion['drafts']}, 'This item is not present in the imported file.')
    targets = [choice.target_asset_id for choice in body.choices if choice.target_asset_id]
    require(len(set(targets)) == len(targets), 'Choose a separate Library item for each import part.')


def publish_choices(connection, database, row, choices):
    versions = []
    for choice in sorted(choices, key=lambda item: item.part != 'lorebook'):
        content = dict(choice.content)
        if choice.part == 'character' and versions:
            content = link_imported_book(connection, content, versions[0])
        version = publish_choice(connection, database, choice, content)
        connection.execute('INSERT OR IGNORE INTO asset_import_origins VALUES (?,?,?)', (version['id'], row['id'], choice.part))
        versions.append(version)
    return versions


def link_imported_book(connection, content, book):
    links = content.get('lorebook_versions', [])
    require(isinstance(links, list) and len(links) <= 100 and all(isinstance(link, str) for link in links),
            'Use at most 100 lorebook version references.')
    retained = [link for link in links if one(connection, 'SELECT asset_id FROM asset_versions WHERE id=?', (link,))['asset_id'] != book['asset_id']]
    return {**content, 'lorebook_versions': list(dict.fromkeys([*retained, book['id']]))}


def publish_choice(connection, database, choice, content):
    fields = {'name': choice.name, 'content': content, 'note': 'Published from a reviewed Library import'}
    if not choice.target_asset_id:
        return create_asset(connection, database, AssetCreate(kind=choice.part, **fields))
    target = one(connection, 'SELECT kind FROM assets WHERE id=?', (choice.target_asset_id,))
    require(canonical_kind(target['kind']) == choice.part, 'The imported item and target must have the same type.')
    require(choice.expected_version_id is not None, 'Select the current target version before publishing.')
    body = AssetPublish(**fields, expected_version_id=choice.expected_version_id, expected_source_hash=choice.expected_source_hash)
    return publish_asset(connection, database, choice.target_asset_id, body)
