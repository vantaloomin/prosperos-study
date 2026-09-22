import io
import json
import zipfile
from uuid import uuid4
from xml.etree import ElementTree as ET

from server.archives.format import ARCHIVE_VERSION
from server.manuscript.models import ManuscriptDocument
from tests.test_archives import backup, restore


def append(client, branch_id, revision, text, role='narrator'):
    response = client.post(f'/api/branches/{branch_id}/messages', json={
        'operation_id': uuid4().hex, 'expected_revision': revision, 'text': text, 'role': role})
    assert response.status_code == 201, response.text
    return response.json()['node_id']


def book_fixture(client, story):
    branch = story['branch_id']
    a = append(client, branch, 0, 'Rain & lanterns.\n\nMara opened the gate.')
    append(client, branch, 1, 'SECRET author note', 'ooc')
    b = append(client, branch, 2, '“Wait,” said Mara. <script>literal text</script>', 'user')
    c = append(client, branch, 3, 'The river carried the lantern home.')
    document = ManuscriptDocument(title='The Lantern & the River', author='M. Author').model_dump()
    document['chapters'] = [
        {'id': 'chapter-a', 'title': 'Arrival', 'scenes': [{'id': 'scene-a', 'title': 'The gate', 'branch_id': branch,
            'head_id': c, 'from_node_id': a, 'through_node_id': b}]},
        {'id': 'chapter-b', 'title': 'Departure', 'scenes': [{'id': 'scene-b', 'title': 'The river', 'branch_id': branch,
            'head_id': c, 'from_node_id': c, 'through_node_id': c}]},
    ]
    document['bookmarks'] = [{'id': 'bookmark-a', 'scene_id': 'scene-a', 'node_id': a, 'label': 'Opening'}]
    response = client.put(f"/api/stories/{story['story_id']}/manuscript", json={'expected_revision': 0, 'document': document})
    assert response.status_code == 200, response.text
    return document, c


def test_organization_search_export_and_download_snapshot(client, story):
    document, _ = book_fixture(client, story)
    endpoint = f"/api/stories/{story['story_id']}/manuscript"
    preview = client.get(endpoint + '/preview').json()
    assert [chapter['title'] for chapter in preview['chapters']] == ['Arrival', 'Departure']
    assert 'SECRET' not in json.dumps(preview)
    hits = client.get(endpoint + '/search?q=lantern').json()
    assert hits['total'] == 2
    assert [hit['chapter'] for hit in hits['matches']] == ['Arrival', 'Departure']
    response = client.post(endpoint + '/exports', json={'expected_revision': 1})
    assert response.status_code == 201, response.text
    prepared = response.json()
    original = client.get(prepared['docx_url']).content
    for format in ['docx', 'epub']:
        archive = zipfile.ZipFile(io.BytesIO(client.get(prepared[f'{format}_url']).content))
        text = '\n'.join(archive.read(name).decode() for name in archive.namelist())
        assert 'SECRET' not in text and 'bookmark-a' not in text and 'node_id' not in text
        for name in archive.namelist():
            if name.endswith(('.xml', '.xhtml', '.opf', '.rels')):
                ET.fromstring(archive.read(name))
        if format == 'epub':
            assert archive.infolist()[0].filename == 'mimetype'
            assert archive.infolist()[0].compress_type == zipfile.ZIP_STORED
            assert archive.read('mimetype') == b'application/epub+zip'
            assert b'&lt;script&gt;' in archive.read('EPUB/chapter-1.xhtml')
        else:
            prose = ''.join(ET.fromstring(archive.read('word/document.xml')).itertext())
            assert prose.index('Arrival') < prose.index('Departure')
            assert 'Rain & lanterns.' in prose
    append(client, story['branch_id'], 4, 'Later prose stays outside the selection.')
    assert client.get(prepared['docx_url']).content == original
    assert 'Later prose' not in client.get(endpoint + '/preview').text
    document['chapters'].reverse()
    result = client.put(endpoint, json={'expected_revision': 1, 'document': document})
    assert result.status_code == 200
    assert client.put(endpoint, json={'expected_revision': 1, 'document': document}).status_code == 409
    assert client.get(endpoint + '/preview').json()['chapters'][0]['title'] == 'Departure'


def test_manuscript_rejects_foreign_sources_and_bad_bookmarks(client, story):
    document, head = book_fixture(client, story)
    endpoint = f"/api/stories/{story['story_id']}/manuscript"
    document['bookmarks'][0]['node_id'] = head
    response = client.put(endpoint, json={'expected_revision': 1, 'document': document})
    assert response.status_code == 400
    document['bookmarks'] = []
    other = client.post('/api/stories', json={'title': 'Other'}).json()
    document['chapters'][0]['scenes'][0]['branch_id'] = other['branch_id']
    assert client.put(endpoint, json={'expected_revision': 1, 'document': document}).status_code == 404


def test_contributions_optional_and_empty_book_export_rejected(client, story):
    endpoint = f"/api/stories/{story['story_id']}/manuscript"
    assert client.post(endpoint + '/exports', json={'expected_revision': 0}).status_code == 409
    document, _ = book_fixture(client, story)
    document['include_contributions'] = False
    assert client.put(endpoint, json={'expected_revision': 1, 'document': document}).status_code == 200
    assert 'Wait' not in client.get(endpoint + '/preview').text
    scene = document['chapters'][0]['scenes'][0]
    scene['from_node_id'] = scene['through_node_id']
    document['bookmarks'] = []
    assert client.put(endpoint, json={'expected_revision': 2, 'document': document}).status_code == 200
    assert client.post(endpoint + '/exports', json={'expected_revision': 3}).status_code == 409


def test_archive_restores_manuscript_links_bookmarks_and_order(client, story):
    document, head = book_fixture(client, story)
    file, archive = backup(client, story)
    assert archive['version'] == ARCHIVE_VERSION
    _, mapping = restore(client, file)
    restored = client.get(f"/api/stories/{mapping[story['story_id']]}/manuscript").json()
    assert restored['revision'] == 1
    scene = restored['document']['chapters'][0]['scenes'][0]
    assert scene['branch_id'] == mapping[story['branch_id']] and scene['head_id'] == mapping[head]
    assert restored['document']['bookmarks'][0]['node_id'] == mapping[document['bookmarks'][0]['node_id']]
    original = client.get(f"/api/stories/{story['story_id']}/manuscript/preview").json()
    imported = client.get(f"/api/stories/{mapping[story['story_id']]}/manuscript/preview").json()
    assert [part['text'] for chapter in original['chapters'] for scene in chapter['scenes'] for part in scene['passages']] == [part['text'] for chapter in imported['chapters'] for scene in chapter['scenes'] for part in scene['passages']]


def test_same_story_different_telling_head_is_rejected(client, story):
    document, head = book_fixture(client, story)
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': 4, 'node_id': head, 'name': 'Alternate river',
        'replacement': 'The lantern remained on the shore.'}).json()
    document['chapters'][0]['scenes'][0]['branch_id'] = fork['branch_id']
    assert client.put(f"/api/stories/{story['story_id']}/manuscript", json={'expected_revision': 1, 'document': document}).status_code == 409


def test_telling_ending_in_removal_marker_can_supply_remaining_prose(client, story):
    from tests.test_passage_revisions import revise

    first = append(client, story['branch_id'], 0, 'The preserved opening.')
    last = append(client, story['branch_id'], 1, 'The removed ending.')
    revised = revise(client, story['branch_id'], last)
    endpoint = f"/api/stories/{story['story_id']}/manuscript"
    sources = client.get(endpoint + '/sources', params={'branch_id': revised['branch_id']}).json()
    assert [passage['id'] for passage in sources['passages']] == [first]
    document = ManuscriptDocument(title='Edited telling').model_dump()
    document['chapters'] = [{'id': 'chapter', 'title': 'Opening', 'scenes': [
        {'id': 'scene', 'title': 'Gate', 'branch_id': revised['branch_id'], 'head_id': sources['head_id'],
         'from_node_id': first, 'through_node_id': first}]}]
    saved = client.put(endpoint, json={'expected_revision': 0, 'document': document})
    assert saved.status_code == 200, saved.text
    preview = client.get(endpoint + '/preview')
    assert preview.status_code == 200 and 'removed ending' not in preview.text
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    assert client.get(f"/api/stories/{mapping[story['story_id']]}/manuscript/preview").status_code == 200
