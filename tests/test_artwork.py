import base64
import json
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from struct import pack
from zipfile import ZipFile
from zlib import crc32

import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

from server.archives.validate import parse_archive
from server.character_content import narrative_asset
from server.database import one
from server.errors import DomainError
from server.library_formats.import_conversion import convert_import
from server.main import create_app
from server.side_context import branch_sources
from tests.test_archives import backup, restore
from tests.test_card_markdown import card
from tests.test_library import with_book
from tests.test_library_imports import publish_body, stage


def png(version=None, legacy=False, color='steelblue'):
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('Comment', 'Preserved only in original')
    if version:
        key = 'ccv3' if version == 'v3' else 'chara'
        metadata.add_text(key, base64.b64encode(json.dumps(card(version), ensure_ascii=False).encode()).decode())
    if legacy:
        metadata.add_text('chara', base64.b64encode(json.dumps(card('v2')).encode()).decode())
    stream = BytesIO()
    Image.new('RGB', (360, 480), color).save(stream, format='PNG', pnginfo=metadata)
    return stream.getvalue()


def uploaded(client, source, **extra):
    return client.post('/api/library-artwork', json={'source_base64': base64.b64encode(source).decode(), **extra})


@pytest.mark.parametrize('version', ['v1', 'v2', 'v3'])
def test_png_card_review_preserves_original_json_markdown_and_artwork(client, version):
    original = png(version, legacy=version == 'v3')
    preview = stage(client, original, 'atlas.png')
    assert preview['format'] == 'png-card' and preview['card_version'] == version
    assert not client.get('/api/library').json()
    image_hash = sha256(original).hexdigest()
    assert preview['drafts'][0]['content']['artwork_sha256'] == image_hash
    display = client.get(f'/api/library-artwork/{image_hash}').content
    with Image.open(BytesIO(display)) as image:
        assert image.size == (360, 480) and image.info == {}
    package = client.get(f"/api/library-imports/{preview['id']}/package").content
    with ZipFile(BytesIO(package)) as archive:
        assert archive.read('source.png') == original
        assert json.loads(archive.read('source.json')) == card(version)
        assert 'converted/character.md' in archive.namelist()
    result = client.post(f"/api/library-imports/{preview['id']}/publish", json=publish_body(preview))
    assert result.status_code == 201, result.text
    character = next(item for item in result.json()['versions'] if item['kind'] == 'character')
    assert character['content']['artwork_sha256'] == image_hash
    assert 'artwork_sha256' not in narrative_asset({'kind': 'character', 'version': character})['version']['content']
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM generations').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM mechanic_opportunities').fetchone()[0] == 0


def test_artwork_versions_pins_archive_and_restore_keep_exact_images(client, tmp_path):
    originals = [png(color='steelblue'), png(color='coral')]
    digests = [uploaded(client, value).json()['sha256'] for value in originals]
    body = {'kind': 'character', 'name': 'Atlas keeper', 'content': {'text': 'A patient cartographer.', 'artwork_sha256': digests[0]}}
    first = client.post('/api/library', json=body).json()
    story = with_book(client, first, 'The atlas')
    second = client.post(f"/api/library/{first['asset_id']}/versions", json={'expected_version_id': first['id'],
        'name': first['name'], 'content': {**first['content'], 'artwork_sha256': digests[1]}})
    assert second.status_code == 201, second.text
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert branch['attachments'][0]['version_id'] == first['id']
    assert 'source_base64' not in json.dumps(branch)
    file, document = backup(client)
    assert document['version'] == 19 and len(document['data']['library_media']) == 2
    restore(client, file)  # Restoring into the source workspace deduplicates image bytes.
    with TestClient(create_app(tmp_path / 'fresh.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as target:
        staged = target.post('/api/archives/imports', json={'content': json.dumps(document)})
        assert staged.status_code == 201, staged.text
        restore(target, staged.json())
        for digest, original in zip(digests, originals, strict=True):
            response = target.get(f'/api/library-artwork/{digest}?size=original')
            assert response.content == original
            assert 'attachment' in response.headers['content-disposition']
        assert len(target.get('/api/library').json()) == 1
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM library_media').fetchone()[0] == 2


def test_png_provenance_restores_even_after_artwork_is_removed(client, tmp_path):
    preview = stage(client, png('v3'), 'person.png')
    body = publish_body(preview)
    body['choices'][0]['content']['artwork_sha256'] = None
    response = client.post(f"/api/library-imports/{preview['id']}/publish", json=body)
    assert response.status_code == 201
    _, document = backup(client)
    assert len(document['data']['library_media']) == 1
    assert parse_archive(json.dumps(document))['version'] == 19


@pytest.mark.parametrize('kind', ['character', 'lorebook', 'persona'])
def test_artwork_is_versioned_for_each_library_kind_and_excluded_from_narrative(client, kind):
    digest = uploaded(client, png()).json()['sha256']
    response = client.post('/api/library', json={'kind': kind, 'name': kind, 'content': {'text': 'Reference.', 'artwork_sha256': digest}})
    assert response.status_code == 201, response.text
    assert 'artwork_sha256' not in narrative_asset({'kind': kind, 'version': response.json()})['version']['content']
    bad = client.post('/api/library', json={'kind': kind, 'name': 'Missing', 'content': {'artwork_sha256': '0' * 64}})
    assert bad.status_code == 400


def test_editor_card_detection_stages_review_without_changing_existing_asset(client):
    response = uploaded(client, png('v3'), detect_card=True, filename='Iona.png')
    assert response.status_code == 201
    assert response.json()['import_preview']['card_version'] == 'v3'
    assert response.json()['import_preview']['filename'] == 'Iona.png'
    assert client.get('/api/library').json() == []
    assert uploaded(client, png(), detect_card=True).json()['sha256']


@pytest.mark.parametrize('format_name', ['PNG', 'JPEG', 'WEBP'])
def test_image_formats_preserve_original_and_make_bounded_previews(client, format_name):
    stream = BytesIO()
    Image.new('RGB', (1800, 400), 'teal').save(stream, format=format_name)
    original = stream.getvalue()
    response = uploaded(client, original)
    assert response.status_code == 201, response.text
    digest = response.json()['sha256']
    assert client.get(f'/api/library-artwork/{digest}?size=original').content == original
    for size, expected in [('display', (1600, 356)), ('thumbnail', (256, 57))]:
        result = client.get(f'/api/library-artwork/{digest}?size={size}')
        assert result.headers['content-type'] == 'image/png'
        assert result.headers['x-content-type-options'] == 'nosniff'
        with Image.open(BytesIO(result.content)) as image:
            assert image.size == expected and not image.info


def test_animated_png_card_uses_a_still_preview_and_preserves_all_original_frames(client):
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('ccv3', base64.b64encode(json.dumps(card('v3')).encode()).decode())
    output = BytesIO()
    Image.new('RGB', (80, 100), 'red').save(output, format='PNG', save_all=True,
        append_images=[Image.new('RGB', (80, 100), 'blue')], duration=100, loop=0, pnginfo=metadata)
    original = output.getvalue()
    preview = stage(client, original, 'animated.png')
    assert convert_import('animated.png', original)['png_animated'] is True
    assert client.get(f"/api/library-imports/{preview['id']}/original").content == original
    digest = preview['drafts'][0]['content']['artwork_sha256']
    with Image.open(BytesIO(client.get(f'/api/library-artwork/{digest}').content)) as image:
        assert image.n_frames == 1 and image.getpixel((20, 20)) == (255, 0, 0, 255)


@pytest.mark.parametrize('mutation', ['damaged', 'duplicate', 'trailing', 'no_card', 'wrong_v3', 'bad_base64'])
def test_bad_png_card_has_no_partial_stage_or_library_item(client, mutation):
    source = png('v3')
    if mutation == 'damaged':
        source = source[:-20] + b'bad' + source[-17:]
    elif mutation == 'duplicate':
        source = insert_text(source, b'ccv3\0' + base64.b64encode(json.dumps(card('v3')).encode()))
    elif mutation == 'trailing':
        source += b'other'
    elif mutation == 'no_card':
        source = png()
    elif mutation == 'wrong_v3':
        source = insert_text(png(), b'ccv3\0' + base64.b64encode(json.dumps(card('v2')).encode()))
    else:
        source = insert_text(png(), b'ccv3\0invalid!')
    response = client.post('/api/library-imports', json={'filename': 'bad.png', 'source_base64': base64.b64encode(source).decode()})
    assert response.status_code == 400, response.text
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM library_imports').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM library_media').fetchone()[0] == 0


def insert_text(source, payload):
    data = b'tEXt' + payload
    return source[:-12] + pack('>I', len(payload)) + data + pack('>I', crc32(data)) + source[-12:]


def test_corrupt_images_and_oversized_dimensions_are_rejected(client):
    assert uploaded(client, b'not an image').status_code == 400
    assert client.post('/api/library-artwork', json={'source_base64': '!!!'}).status_code == 400
    source = png()
    header = b'IHDR' + pack('>II', 8000, 8000) + source[24:29]
    large = source[:12] + header + pack('>I', crc32(header)) + source[33:]
    assert uploaded(client, large).status_code == 400


def test_damaged_ordinary_png_checksum_returns_an_actionable_error(client):
    source = bytearray(png())
    chunk = source.index(b'IDAT')
    length = int.from_bytes(source[chunk - 4:chunk], 'big')
    source[chunk + 4 + length] ^= 1
    response = uploaded(client, source)
    assert response.status_code == 400
    assert 'could not be decoded' in response.json()['detail']
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM library_media').fetchone()[0] == 0


def test_archive_rejects_tampered_image_bytes_missing_media_and_bad_previews(client):
    preview = stage(client, png('v1'), 'card.png')
    client.post(f"/api/library-imports/{preview['id']}/publish", json=publish_body(preview))
    _, original = backup(client)
    mutations = [('source_base64', base64.b64encode(png(color='red')).decode()),
                 ('thumbnail_base64', base64.b64encode(png()).decode()), ('width', 1)]
    for field, value in mutations:
        broken = deepcopy(original)
        broken['data']['library_media'][0][field] = value
        with pytest.raises(DomainError):
            parse_archive(json.dumps(broken))
    broken = deepcopy(original)
    broken['data']['library_media'] = []
    with pytest.raises(DomainError):
        parse_archive(json.dumps(broken))


def test_format_seventeen_upgrades_without_changing_prior_card_conversion(client):
    before = convert_import('card.json', json.dumps(card('v3')).encode())
    _, original = backup(client)
    original['data'].pop('library_media')
    original['version'] = 17
    assert parse_archive(json.dumps(original))['data']['library_media'] == []
    assert convert_import('card.json', json.dumps(card('v3')).encode()) == before


def test_collaborator_retrieves_exact_png_card_text_without_decoding_binary_as_utf8(client):
    preview = stage(client, png('v3', legacy=True), 'reference.png')
    result = client.post(f"/api/library-imports/{preview['id']}/publish", json=publish_body(preview)).json()
    character = next(item for item in result['versions'] if item['kind'] == 'character')
    story = with_book(client, character, 'Reference review')
    with client.app.state.database.connect() as connection:
        branch = one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],))
        docs = branch_sources(connection, branch)
        original = next(doc for doc in docs if doc['id'].startswith(f"import:{preview['id']}:source.json:"))
        assert original['text'] == json.dumps(card('v3'), ensure_ascii=False)
        assert 'exact embedded JSON' in original['title']
        assert any('Image pixels are not represented' in doc['text'] for doc in docs)
        assert any('@@dont_activate' in doc['text'] for doc in docs)
        assert one(connection, 'SELECT * FROM branches WHERE id=?', (story['branch_id'],)) == branch
        assert connection.execute('SELECT COUNT(*) FROM nodes').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM mechanic_opportunities').fetchone()[0] == 0
