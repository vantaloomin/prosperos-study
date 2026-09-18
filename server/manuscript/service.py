"""Selections capture a telling's head; later branch changes are visible, never automatic."""
import re

from server.branches import path_nodes
from server.database import decode, encode, identifier, now, one
from server.errors import require
from server.manuscript.models import ManuscriptDocument
from server.stories import check_revision
from server.transcripts import selected_passage


def load_manuscript(connection, story_id):
    story = one(connection, 'SELECT title FROM stories WHERE id=?', (story_id,))
    row = connection.execute('SELECT * FROM manuscripts WHERE story_id=?', (story_id,)).fetchone()
    if row:
        return {**dict(row), 'document': decode(row['document'])}
    return {'id': None, 'story_id': story_id, 'revision': 0,
            'document': ManuscriptDocument(title=story['title']).model_dump()}


def scene_passage(connection, story_id, scene, paths):
    branch = one(connection, 'SELECT * FROM branches WHERE id=? AND story_id=?', (scene.branch_id, story_id))
    head = one(connection, 'SELECT id FROM nodes WHERE id=? AND story_id=?', (scene.head_id, story_id))
    if branch['head_id'] not in paths:
        paths[branch['head_id']] = path_nodes(connection, branch['head_id'], include_removed=True)
    require(any(node['id'] == head['id'] for node in paths[branch['head_id']]),
            'The selected head does not belong to this telling.', 409)
    if head['id'] not in paths:
        paths[head['id']] = path_nodes(connection, head['id'], include_removed=True)
    path = [node for node in paths[head['id']] if not node['metadata'].get('removed')]
    require(all(node['story_id'] == story_id for node in path), 'A scene contains another Story’s passages.')
    passage = selected_passage(path, scene)
    prose = [node for node in passage if node['role'] != 'ooc']
    require(bool(prose), 'Choose a scene containing accepted prose, not only author notes.', 409)
    return branch, prose


def validate_document(connection, story_id, document):
    ids = [chapter.id for chapter in document.chapters]
    ids += [scene.id for chapter in document.chapters for scene in chapter.scenes]
    ids += [mark.id for mark in document.bookmarks]
    require(len(ids) == len(set(ids)), 'Each chapter, scene and bookmark needs its own identity.')
    require(sum(len(chapter.scenes) for chapter in document.chapters) <= 2000, 'A manuscript supports up to 2,000 scenes.')
    paths, scenes = {}, {}
    for chapter in document.chapters:
        for scene in chapter.scenes:
            _, prose = scene_passage(connection, story_id, scene, paths)
            scenes[scene.id] = {node['id'] for node in prose}
    for mark in document.bookmarks:
        require(mark.node_id in scenes.get(mark.scene_id, set()), 'A bookmark must point into a selected scene.')


def save_manuscript(connection, story_id, body):
    current = load_manuscript(connection, story_id)
    check_revision(current, body.expected_revision)
    validate_document(connection, story_id, body.document)
    connection.execute('INSERT INTO manuscripts VALUES (?,?,?,?,?,?) ON CONFLICT(story_id) DO UPDATE SET '
                       'document=excluded.document,revision=excluded.revision,updated_at=excluded.updated_at',
                       (current['id'] or identifier(), story_id, current['revision'] + 1,
                        encode(body.document.model_dump()), now(), now()))
    return load_manuscript(connection, story_id)


def assemble(connection, manuscript):
    document = ManuscriptDocument.model_validate(manuscript['document'])
    paths, chapters = {}, []
    count = 0
    for chapter in document.chapters:
        scenes = []
        for scene in chapter.scenes:
            branch, prose = scene_passage(connection, manuscript['story_id'], scene, paths)
            included = [node for node in prose if document.include_contributions or node['role'] != 'user']
            passages = [{'node_id': node['id'], 'text': node['text']} for node in included]
            words = sum(len(node['text'].split()) for node in included)
            count += words
            scenes.append({'id': scene.id, 'title': scene.title, 'branch_id': branch['id'],
                           'telling': branch['name'], 'changed': branch['head_id'] != scene.head_id,
                           'passages': passages, 'words': words})
        chapters.append({'id': chapter.id, 'title': chapter.title, 'scenes': scenes})
    return {'title': document.title, 'author': document.author, 'language': document.language,
            'scene_headings': document.scene_headings, 'chapters': chapters, 'words': count,
            'revision': manuscript['revision']}


def search_manuscript(publication, query, offset=0, limit=50):
    hits = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    for chapter in publication['chapters']:
        for scene in chapter['scenes']:
            for passage in scene['passages']:
                match = pattern.search(passage['text'])
                if match:
                    start, end = max(0, match.start() - 80), min(len(passage['text']), match.end() + 140)
                    hits.append({'chapter_id': chapter['id'], 'chapter': chapter['title'],
                                 'scene_id': scene['id'], 'scene': scene['title'], 'node_id': passage['node_id'],
                                 'excerpt': passage['text'][start:end]})
    return {'matches': hits[offset:offset + limit], 'total': len(hits), 'offset': offset,
            'has_more': len(hits) > offset + limit, 'revision': publication['revision']}
