import re
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from server.branches import path_nodes
from server.database import decode, encode, identifier, now, one
from server.errors import require
from server.manuscript.exports import export_docx, export_epub
from server.manuscript.html_publication import export_html
from server.manuscript.models import ManuscriptUpdate, PublicationCreate
from server.manuscript.service import assemble, load_manuscript, save_manuscript, search_manuscript
from server.stories import check_revision

router = APIRouter(prefix='/api')


@router.get('/stories/{story_id}/manuscript')
def manuscript(story_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return load_manuscript(connection, story_id)


@router.put('/stories/{story_id}/manuscript')
def save(story_id: str, body: ManuscriptUpdate, request: Request):
    with request.app.state.database.connect(write=True) as connection:
        return save_manuscript(connection, story_id, body)


@router.get('/stories/{story_id}/manuscript/sources')
def sources(story_id: str, branch_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=? AND story_id=?', (branch_id, story_id))
        nodes = path_nodes(connection, branch['head_id'])
        return {'branch_id': branch_id, 'head_id': branch['head_id'], 'revision': branch['revision'],
                'passages': [{'id': node['id'], 'role': node['role'], 'excerpt': node['text'][:180],
                              'scene': node['metadata'].get('scene_id')} for node in nodes if node['role'] != 'ooc']}


@router.get('/stories/{story_id}/manuscript/preview')
def preview(story_id: str, request: Request):
    with request.app.state.database.connect() as connection:
        return assemble(connection, load_manuscript(connection, story_id))


@router.get('/stories/{story_id}/manuscript/search')
def search(story_id: str, request: Request, q: str = Query(min_length=1, max_length=200), offset: int = Query(default=0, ge=0)):
    with request.app.state.database.connect() as connection:
        return search_manuscript(assemble(connection, load_manuscript(connection, story_id)), q, offset)


@router.post('/stories/{story_id}/manuscript/exports', status_code=201)
def prepare(story_id: str, body: PublicationCreate, request: Request):
    with request.app.state.database.connect(write=True) as connection:
        manuscript = load_manuscript(connection, story_id)
        check_revision(manuscript, body.expected_revision)
        result = assemble(connection, manuscript)
        require(result['words'] > 0, 'Add accepted prose to the manuscript before exporting.', 409)
        require(all(chapter['scenes'] for chapter in result['chapters']), 'Add scenes to empty chapters or remove them before exporting.', 409)
        require(all(scene['passages'] for chapter in result['chapters'] for scene in chapter['scenes']),
                'Some scenes have no prose after excluding character contributions. Include contributions or remove those scenes before exporting.', 409)
        export_id = identifier()
        result.update(publication_id=export_id, created_at=now(), html_contents=body.html_contents)
        connection.execute('INSERT INTO prepared_publications VALUES (?,?,?,?)',
                           (export_id, manuscript['id'], encode(result), result['created_at']))
    return {'id': export_id, 'revision': result['revision'], 'words': result['words'],
            'docx_url': f'/api/publications/{export_id}/docx', 'epub_url': f'/api/publications/{export_id}/epub',
            'html_url': f'/api/publications/{export_id}/html'}


@router.get('/publications/{publication_id}/{format}')
def download(publication_id: str, format: Literal['docx', 'epub', 'html'], request: Request):
    with request.app.state.database.connect() as connection:
        row = one(connection, 'SELECT document FROM prepared_publications WHERE id=?', (publication_id,))
        document = decode(row['document'])
    exporters = {'docx': (export_docx, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                 'epub': (export_epub, 'application/epub+zip'), 'html': (export_html, 'text/html')}
    exporter, media = exporters[format]
    content = exporter(document)
    slug = re.sub(r'[^\w-]+', '-', document['title']).strip('-')[:80] or 'manuscript'
    return Response(content, media_type=media, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                    'Content-Disposition': f"attachment; filename*=UTF-8''{quote(slug + '.' + format, safe='')}"})
