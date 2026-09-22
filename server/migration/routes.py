from pathlib import PureWindowsPath
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response

from server.database import decode, encode
from server.library_formats.import_conversion import source_bytes
from server.migration.models import TranscriptPublish, TranscriptUpload
from server.migration.transcripts import TranscriptImports

router = APIRouter(prefix='/api')


@router.get('/migration/transcripts')
def list_transcripts(request: Request):
    return TranscriptImports(request.app.state.database).list()


@router.post('/migration/transcripts', status_code=201)
def stage_transcript(body: TranscriptUpload, request: Request):
    return TranscriptImports(request.app.state.database).stage(body)


@router.get('/migration/transcripts/{import_id}')
def preview_transcript(import_id: str, request: Request):
    return TranscriptImports(request.app.state.database).view(import_id)


@router.post('/migration/transcripts/{import_id}/publish', status_code=201)
def publish_transcript(import_id: str, body: TranscriptPublish, request: Request):
    return TranscriptImports(request.app.state.database).publish(import_id, body)


@router.get('/migration/transcripts/{import_id}/original')
def original(import_id: str, request: Request):
    row = TranscriptImports(request.app.state.database).row(import_id)
    return attachment(source_bytes(row['source_base64']), PureWindowsPath(row['filename']).name)


@router.get('/migration/transcripts/{import_id}/report')
def report(import_id: str, request: Request):
    row = TranscriptImports(request.app.state.database).row(import_id)
    return attachment(encode(decode(row['conversion'])), 'transcript-conversion.json')


@router.get('/stories/{story_id}/imports')
def origins(story_id: str, request: Request):
    return TranscriptImports(request.app.state.database).origins(story_id)


def attachment(content, filename):
    return Response(content, media_type='application/octet-stream', headers={
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
