"""Read embedded Character Card JSON without executing or resolving its assets."""
import base64
import binascii
from hashlib import sha256
from struct import unpack
from zlib import crc32

from server.library_formats.cards import MAX_SOURCE_BYTES

SIGNATURE = b'\x89PNG\r\n\x1a\n'


def chunks(source):
    if not source.startswith(SIGNATURE) or len(source) > MAX_SOURCE_BYTES:
        raise ValueError('Choose a PNG Character Card no larger than 10 MiB.')
    offset = 8
    count = 0
    while offset + 12 <= len(source):
        length = unpack('>I', source[offset:offset + 4])[0]
        kind = source[offset + 4:offset + 8]
        end = offset + length + 12
        if end > len(source) or count >= 10000:
            raise ValueError('This PNG has incomplete or too many chunks.')
        payload = source[offset + 8:end - 4]
        expected = unpack('>I', source[end - 4:end])[0]
        if crc32(kind + payload) & 0xffffffff != expected:
            raise ValueError('This PNG has a damaged chunk checksum.')
        yield kind, payload
        offset = end
        count += 1
        if kind == b'IEND':
            if length or offset != len(source):
                raise ValueError('This PNG has unexpected data after its image.')
            return
    raise ValueError('This PNG has no complete image ending.')


def embedded_card(source):
    payloads = {}
    animated = False
    for kind, payload in chunks(source):
        animated = animated or kind == b'acTL'
        if kind == b'tEXt':
            key, separator, value = payload.partition(b'\0')
            if separator and key in {b'ccv3', b'chara'}:
                if key in payloads:
                    raise ValueError('This PNG has duplicate card payloads. Export a card with one payload per format.')
                payloads[key] = value
    key = b'ccv3' if b'ccv3' in payloads else b'chara'
    if key not in payloads:
        raise ValueError('No embedded Character Card was found. Use the Artwork field for an ordinary image.')
    try:
        data = base64.b64decode(payloads[key], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('The embedded Character Card is not valid base64.') from error
    return data, {'png_payload': key.decode('ascii'), 'embedded_sha256': sha256(data).hexdigest(),
                  'png_animated': animated, 'png_legacy_copy': len(payloads) > 1}
