"""Bounded local image decoding; immutable originals and metadata-free previews."""
import base64
import warnings
from hashlib import sha256
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from server.errors import DomainError, require

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000
FORMATS = {'PNG', 'JPEG', 'WEBP'}


def decode_image(source):
    require(0 < len(source) <= MAX_IMAGE_BYTES, 'Artwork must be no larger than 10 MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(source), formats=list(FORMATS)) as image:
                require(image.width * image.height <= MAX_PIXELS, 'Use artwork of at most 16 million pixels.')
                image.verify()
            with Image.open(BytesIO(source), formats=list(FORMATS)) as image:
                image.seek(0)
                image.load()
                return ImageOps.exif_transpose(image).convert('RGBA')
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise DomainError('This image could not be decoded. Choose a valid PNG, JPEG or WebP file.', 400) from error


def png_preview(image, size):
    copy = image.copy()
    copy.thumbnail((size, size), Image.Resampling.LANCZOS)
    # A new image keeps card payloads, EXIF and other source metadata out of previews.
    clean = Image.new('RGBA', copy.size)
    clean.paste(copy)
    output = BytesIO()
    clean.save(output, format='PNG')
    return base64.b64encode(output.getvalue()).decode('ascii')


def prepare_artwork(source):
    image = decode_image(source)
    return {'sha256': sha256(source).hexdigest(), 'source_base64': base64.b64encode(source).decode('ascii'),
            'display_base64': png_preview(image, 1600), 'thumbnail_base64': png_preview(image, 256),
            'width': image.width, 'height': image.height}


def store_artwork(connection, row):
    connection.execute('INSERT OR IGNORE INTO library_media VALUES (?,?,?,?,?,?)', tuple(row[key] for key in
                       ('sha256', 'source_base64', 'display_base64', 'thumbnail_base64', 'width', 'height')))


def validate_artwork_ref(connection, content):
    digest = content.get('artwork_sha256')
    if digest is None:
        return
    require(isinstance(digest, str) and len(digest) == 64 and all(char in '0123456789abcdef' for char in digest),
            'Choose artwork uploaded to this Library.')
    require(connection.execute('SELECT 1 FROM library_media WHERE sha256=?', (digest,)).fetchone() is not None,
            'This artwork is unavailable. Upload it again before publishing.')
