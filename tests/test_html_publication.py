import io
import json
import zipfile
from copy import deepcopy
from html.parser import HTMLParser
from uuid import uuid4
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from server.database import encode
from server.main import create_app
from server.manuscript.html_publication import export_html
from tests.test_archives import backup, restore
from tests.test_v07_manuscript import append, book_fixture


class PublicationParser(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.elements = []
        self.prose = []
        self.current = None
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == 'p' and attrs.get('class') == 'passage':
            self.current = ''
        elif tag == 'br' and self.current is not None:
            self.current += '\n'

    def handle_data(self, text):
        if self.current is not None:
            self.current += text

    def handle_endtag(self, tag):
        if tag == 'p' and self.current is not None:
            self.prose.append(self.current)
            self.current = None


def prepared(client, story, **options):
    response = client.post(f"/api/stories/{story['story_id']}/manuscript/exports", json={'expected_revision': 1, **options})
    assert response.status_code == 201, response.text
    return response.json()


def test_html_matches_selected_historical_tellings_and_other_publications(client, story):
    document, head = book_fixture(client, story)
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={
        'operation_id': uuid4().hex, 'expected_revision': 4, 'node_id': head,
        'name': 'PRIVATE alternate diagnosis', 'replacement': 'The lantern stayed beside 雨の川. 🌙'}).json()
    branch = client.get(f"/api/branches/{fork['branch_id']}").json()
    scene = document['chapters'][1]['scenes'][0]
    scene.update(branch_id=branch['id'], head_id=branch['head_id'], from_node_id=branch['head_id'], through_node_id=branch['head_id'])
    endpoint = f"/api/stories/{story['story_id']}/manuscript"
    assert client.put(endpoint, json={'expected_revision': 1, 'document': document}).status_code == 200
    append(client, branch['id'], branch['revision'], 'UNSELECTED later telling.')
    file = prepared(client, story, expected_revision=2)
    response = client.get(file['html_url'])
    assert response.status_code == 200 and response.headers['content-type'] == 'text/html; charset=utf-8'
    assert '.html' in response.headers['content-disposition']
    parsed = PublicationParser(response.text)
    expected = ['Rain & lanterns.', 'Mara opened the gate.', '“Wait,” said Mara. <script>literal text</script>', 'The lantern stayed beside 雨の川. 🌙']
    assert parsed.prose == expected
    for format in ['docx', 'epub']:
        archive = zipfile.ZipFile(io.BytesIO(client.get(file[f'{format}_url']).content))
        paths = ['word/document.xml'] if format == 'docx' else ['EPUB/chapter-1.xhtml', 'EPUB/chapter-2.xhtml']
        prose = '\n'.join(''.join(ET.fromstring(archive.read(path)).itertext()) for path in paths)
        positions = [prose.index(part) for part in expected]
        assert positions == sorted(positions)
    for private in ['SECRET', 'UNSELECTED', 'PRIVATE', story['story_id'], branch['id'], head, 'bookmark-a', 'node_id', 'model_inputs']:
        assert private not in response.text
    assert not any(tag in {'script', 'iframe', 'img', 'link', 'object'} for tag, _ in parsed.elements)
    assert [attrs['href'] for tag, attrs in parsed.elements if tag == 'a'] == ['#chapter-1', '#chapter-2']


def test_html_is_frozen_across_later_book_changes_restart_and_archive_restore(client, story, tmp_path):
    document, _ = book_fixture(client, story)
    file = prepared(client, story, html_contents=False)
    original = client.get(file['html_url']).content
    assert not any(tag == 'nav' for tag, _ in PublicationParser(original.decode()).elements)
    document['chapters'].reverse()
    endpoint = f"/api/stories/{story['story_id']}/manuscript"
    assert client.put(endpoint, json={'expected_revision': 1, 'document': document}).status_code == 200
    assert client.get(file['html_url']).content == original
    with TestClient(create_app(tmp_path / 'test.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as restarted:
        assert restarted.get(file['html_url']).content == original
    _, archive = backup(client, story)
    with TestClient(create_app(tmp_path / 'fresh.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as fresh:
        stage = fresh.post('/api/archives/imports', json={'content': encode(archive)}).json()
        _, mapping = restore(fresh, stage)
        imported = prepared(fresh, {'story_id': mapping[story['story_id']]}, expected_revision=2)
        original_new = prepared(client, story, expected_revision=2)
        assert fresh.get(imported['html_url']).content == client.get(original_new['html_url']).content


def test_markup_unicode_and_prose_layout_are_literal_and_metadata_is_allowlisted():
    text = '  Rain & fog.\r\nA second line.\n\n<script src="https://host.invalid/steal">bad()</script>\n\n' + 'longword' * 1500
    document = {'title': '雨 </title><script>bad()</script>', 'author': 'A. "Writer" & Co.', 'language': 'ja',
                'scene_headings': True, 'private': 'PRIVATE sentinel', 'publication_id': 'PRIVATE identity',
                'chapters': [{'title': '<img onerror="bad()">', 'id': 'PRIVATE chapter', 'scenes': [
                    {'title': '夜 & 舟', 'passages': [{'text': text, 'private': 'PRIVATE passage'}]}]}]}
    before = deepcopy(document)
    html = export_html(document).decode()
    assert document == before
    parser = PublicationParser(html)
    assert parser.prose == ['  Rain & fog.\nA second line.', '<script src="https://host.invalid/steal">bad()</script>', 'longword' * 1500]
    assert not any(tag in {'script', 'img', 'iframe', 'link', 'object'} for tag, _ in parser.elements)
    assert all(not any(key.startswith('on') for key in attrs) for _, attrs in parser.elements)
    assert 'PRIVATE' not in html
    assert ('html', {'lang': 'ja'}) in parser.elements
    assert ('meta', {'name': 'author', 'content': 'A. "Writer" & Co.'}) in parser.elements
    assert any(tag == 'h3' for tag, _ in parser.elements)
    assert '@media print' in html and 'break-before: page' in html and 'overflow-wrap: anywhere' in html
    assert any(attrs.get('http-equiv') == 'Content-Security-Policy' for _, attrs in parser.elements)


def test_contents_and_scene_headings_are_deliberate_independent_options(client, story):
    document, _ = book_fixture(client, story)
    second_scene = document['chapters'].pop()['scenes'][0]
    document['chapters'][0]['scenes'].append(second_scene)
    endpoint = f"/api/stories/{story['story_id']}/manuscript"
    assert client.put(endpoint, json={'expected_revision': 1, 'document': document}).status_code == 200
    without = client.get(prepared(client, story, expected_revision=2, html_contents=False)['html_url']).text
    parser = PublicationParser(without)
    assert not any(tag in {'nav', 'h3'} for tag, _ in parser.elements)
    assert ('p', {'class': 'scene-break', 'aria-label': 'Scene break'}) in parser.elements
    document['scene_headings'] = True
    assert client.put(endpoint, json={'expected_revision': 2, 'document': document}).status_code == 200
    with_headings = client.get(prepared(client, story, expected_revision=3)['html_url']).text
    parser = PublicationParser(with_headings)
    assert sum(tag == 'h3' for tag, _ in parser.elements) == 2
    assert any(tag == 'nav' for tag, _ in parser.elements) and 'class="scene-break"' not in with_headings


def test_older_prepared_publication_without_html_option_is_readable(client, story):
    book_fixture(client, story)
    file = prepared(client, story)
    with client.app.state.database.connect(write=True) as connection:
        row = connection.execute('SELECT * FROM prepared_publications WHERE id=?', (file['id'],)).fetchone()
        document = json.loads(row['document'])
        document.pop('html_contents')
        old_id = uuid4().hex
        document['publication_id'] = old_id
        connection.execute('INSERT INTO prepared_publications VALUES (?,?,?,?)',
                           (old_id, row['manuscript_id'], encode(document), row['created_at']))
    response = client.get(f'/api/publications/{old_id}/html')
    assert response.status_code == 200 and '<nav ' in response.text
    assert client.get('/api/publications/missing/html').status_code == 404
