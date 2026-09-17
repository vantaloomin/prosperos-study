import base64
from pathlib import PureWindowsPath
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field

from server.database import one
from server.errors import DomainError
from server.library_formats.artwork import prepare_artwork, store_artwork
from server.library_formats.import_conversion import source_bytes
from server.library_formats.import_models import ImportUpload
from server.library_formats.imports import LibraryImports
from server.library_formats.png_cards import SIGNATURE, chunks
from server.models import Input

router = APIRouter(prefix='/api/library-artwork')


class ArtworkUpload(Input):
    source_base64: str = Field(max_length=14 * 1024 * 1024)
    filename: str = Field(default='artwork.png', max_length=255)
    detect_card: bool = False


@router.post('', status_code=201)
def upload(body: ArtworkUpload, request: Request):
    try:
        source = source_bytes(body.source_base64)
        card = body.detect_card and source.startswith(SIGNATURE) and any(
            kind == b'tEXt' and payload.partition(b'\0')[0] in {b'chara', b'ccv3'} for kind, payload in chunks(source))
    except ValueError as error:
        raise DomainError(str(error), 400) from error
    if card:
        filename = PureWindowsPath(body.filename).stem[:250] + '.png'
        preview = LibraryImports(request.app.state.database).stage(ImportUpload(filename=filename, source_base64=body.source_base64))
        return {'import_preview': preview}
    row = prepare_artwork(source)
    with request.app.state.database.connect(write=True) as connection:
        store_artwork(connection, row)
    return {key: row[key] for key in ('sha256', 'width', 'height')}


@router.get('/{digest}')
def image(digest: str, request: Request, size: Literal['display', 'thumbnail', 'original'] = 'display'):
    with request.app.state.database.connect() as connection:
        row = one(connection, 'SELECT * FROM library_media WHERE sha256=?', (digest,))
    field = 'source_base64' if size == 'original' else f'{size}_base64'
    content = base64.b64decode(row[field])
    headers = {'Cache-Control': 'private, max-age=31536000, immutable', 'X-Content-Type-Options': 'nosniff'}
    if size == 'original':
        suffix = 'png' if content.startswith(SIGNATURE) else 'jpg' if content.startswith(b'\xff\xd8') else 'webp'
        headers['Content-Disposition'] = f'attachment; filename="original-artwork.{suffix}"'
    return Response(content, media_type='application/octet-stream' if size == 'original' else 'image/png', headers=headers)
