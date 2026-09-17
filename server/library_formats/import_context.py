"""Read-only source access for the collaborator; never narrative instructions."""
from server.database import decode, many
from server.library_formats.import_conversion import source_bytes
from server.library_formats.png_cards import embedded_card


def import_reference_sources(connection, version_id):
    from server.side_context import document_parts

    rows = many(connection, 'SELECT DISTINCT i.* FROM library_imports i JOIN asset_import_origins o '
                'ON o.import_id=i.id WHERE o.version_id=? ORDER BY i.created_at', (version_id,))
    documents = []
    for row in rows:
        prefix = f"Imported reference · {row['filename']} · not active instructions or accepted canon"
        conversion = decode(row['conversion'])
        documents.extend(original_sources(row, conversion, prefix))
        for path, text in conversion['files'].items():
            documents.extend(document_parts(f"import:{row['id']}:{path}", prefix + ' · ' + path, text))
    return documents


def original_sources(row, conversion, prefix):
    from server.side_context import document_parts

    source = source_bytes(row['source_base64'])
    if conversion['format'] != 'png-card':
        return document_parts(f"import:{row['id']}:original", prefix + ' · original file', source.decode('utf-8'))
    embedded, _ = embedded_card(source)
    image_note = (f"Preserved PNG artwork: {row['filename']}; {len(source)} bytes; SHA-256 {row['source_sha256']}. "
                  f"Original download: /api/library-imports/{row['id']}/original. "
                  'Image pixels are not represented as text or interpreted by this reference tool.')
    return (document_parts(f"import:{row['id']}:original", prefix + ' · binary PNG reference', image_note) +
            document_parts(f"import:{row['id']}:source.json", prefix + ' · exact embedded JSON', embedded.decode('utf-8')))
