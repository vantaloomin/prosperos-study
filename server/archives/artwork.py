import base64
from hashlib import sha256
from io import BytesIO

from PIL import Image

from server.archives.records import related_rows
from server.database import decode
from server.errors import require
from server.library_formats.artwork import decode_image
from server.library_formats.container_assets import artwork_references


def collect_artwork(connection, data):
    refs = {decode(row['content']).get('artwork_sha256') for row in data['asset_versions']} - {None}
    for row in data['library_imports']:
        refs.update(artwork_references(row, decode(row['conversion'])))
    data['library_media'] = related_rows(connection, 'library_media', 'sha256', refs)


def validate_artwork(data):
    for row in data['library_media']:
        original = base64.b64decode(row['source_base64'], validate=True)
        require(sha256(original).hexdigest() == row['sha256'], 'Artwork does not match its preserved original.')
        image = decode_image(original)
        require(image.size == (row['width'], row['height']), 'Artwork dimensions do not match the original.')
        for field, bound in (('display_base64', 1600), ('thumbnail_base64', 256)):
            source = base64.b64decode(row[field], validate=True)
            preview = decode_image(source)
            require(max(preview.size) <= bound, 'An artwork preview exceeds its size limit.')
            with Image.open(BytesIO(source)) as parsed:
                require(parsed.format == 'PNG' and not parsed.info, 'Artwork previews must be metadata-free PNG images.')
    available = {row['sha256'] for row in data['library_media']}
    for row in data['library_imports']:
        require(artwork_references(row, decode(row['conversion'])) <= available,
                'An image or character-container import is missing its preserved artwork.')
