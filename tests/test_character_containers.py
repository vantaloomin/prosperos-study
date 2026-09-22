import base64
import json
import stat
import warnings
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest
from fastapi.testclient import TestClient

from server.character_content import narrative_asset
from server.database import decode
from server.library_formats.containers import read_container
from server.main import create_app
from tests.test_archives import backup, restore
from tests.test_artwork import png
from tests.test_card_markdown import card
from tests.test_library import with_book
from tests.test_library_imports import publish_body, publish_import, stage

STAMP = '2026-09-22T12:00:00Z'


def zipped(members, compression=ZIP_DEFLATED):
    stream = BytesIO()
    with ZipFile(stream, 'w', compression=compression) as archive:
        for name, value in members.items():
            info = ZipInfo(name)
            info.filename = name  # Keep deliberately hostile names; Windows normalizes constructor input.
            info.compress_type = compression
            archive.writestr(info, json.dumps(value, ensure_ascii=False).encode('utf-8') if isinstance(value, dict) else value)
    return stream.getvalue()


def charx_members():
    value = card('v3')
    value['data']['assets'] = [
        {'type': 'icon', 'name': 'Portrait', 'uri': 'embeded://assets/icon/portrait.png', 'ext': 'png'},
        {'type': 'emotion', 'name': 'Joy', 'uri': 'embeded://assets/emotion/joy.png', 'ext': 'png'},
        {'type': 'other', 'name': 'Script', 'uri': 'embeded://assets/other/script.js', 'ext': 'js'},
        {'type': 'background', 'name': 'External', 'uri': 'https://example.invalid/never-fetch.png', 'ext': 'png'},
    ]
    return {'card.json': value, 'assets/icon/portrait.png': png(color='steelblue'),
            'assets/emotion/joy.png': png(color='coral'), 'assets/other/script.js': b'throw new Error("NEVER EXECUTE");',
            'unlisted.txt': b'Preserve this unknown attachment exactly.'}


def byaf_members():
    scenario = {'schemaVersion': 1, 'narrative': 'At the rainy harbor.', 'formattingInstructions': 'FOREIGN PROMPT',
                'minP': 0.1, 'minPEnabled': True, 'temperature': 0.7, 'repeatPenalty': 1.1,
                'repeatLastN': 64, 'topK': 40, 'topP': 0.9, 'canDeleteExampleMessages': False,
                'promptTemplate': 'ChatML', 'grammar': None, 'title': 'Arrival',
                'firstMessages': [{'characterID': 'iona', 'text': '“Come in.”'}],
                'exampleMessages': [{'characterID': 'iona', 'text': '{{literal}} example'}],
                'messages': [{'type': 'human', 'text': 'PRIOR CONVERSATION', 'createdAt': STAMP, 'updatedAt': STAMP},
                             {'type': 'ai', 'outputs': [{'text': 'An earlier alternate.', 'createdAt': STAMP,
                                                       'updatedAt': STAMP, 'activeTimestamp': STAMP}]}]}
    character = {'schemaVersion': 1, 'id': 'iona', 'name': 'Iona', 'displayName': 'Iona of the quay',
                 'isNSFW': False, 'persona': 'A patient cartographer. 🌧️', 'createdAt': STAMP, 'updatedAt': STAMP,
                 'images': [{'path': 'images/portrait.png', 'label': 'Portrait'}, {'path': 'images/other.png', 'label': 'Alternative'}],
                 'loreItems': [{'key': 'harbor', 'value': 'Ships shelter here.'}], 'future': {'unknown': 'KEEP ME'}}
    return {'manifest.json': {'schemaVersion': 1, 'createdAt': STAMP, 'characters': ['characters/iona/character.json'],
                              'scenarios': ['scenarios/arrival.json', 'scenarios/departure.json']},
            'characters/iona/character.json': character, 'characters/iona/images/portrait.png': png(),
            'characters/iona/images/other.png': png(color='coral'), 'scenarios/arrival.json': scenario,
            'scenarios/departure.json': {**scenario, 'title': 'Departure', 'narrative': 'UNSELECTED SCENARIO',
                                        'firstMessages': [{'characterID': 'iona', 'text': 'Farewell.'}]}}


def rejected(client, source, filename='invalid.charx'):
    response = client.post('/api/library-imports', json={'filename': filename, 'source_base64': base64.b64encode(source).decode()})
    assert response.status_code == 400, response.text
    assert client.get('/api/library').json() == []
    assert client.get('/api/stories').json() == []
    return response


def test_charx_preview_assets_sources_and_author_choice(client):
    members = charx_members()
    raw = zipped(members)
    preview = stage(client, raw, 'reader.charx')
    assert preview['format'] == 'charx' and preview['source_format'] == 'charx-v3'
    assert [item['status'] for item in preview['assets']] == ['image', 'image', 'reference', 'reference']
    assert client.get('/api/library').json() == [] and client.get('/api/stories').json() == []
    assert client.get(f"/api/library-imports/{preview['id']}/original").content == raw
    assert client.get(f"/api/library-imports/{preview['id']}/assets/0").content == members['assets/icon/portrait.png']
    script = client.get(f"/api/library-imports/{preview['id']}/assets/2")
    assert script.content == members['assets/other/script.js'] and script.headers['x-content-type-options'] == 'nosniff'
    assert 'attachment' in script.headers['content-disposition']
    assert client.get(f"/api/library-imports/{preview['id']}/assets/3").status_code == 404
    assert client.get(f"/api/library-imports/{preview['id']}/assets/-1").status_code == 404
    body = publish_body(preview)
    choice = next(item for item in body['choices'] if item['part'] == 'character')
    choice['content']['artwork_sha256'] = preview['assets'][1]['sha256']
    result = publish_import(client, preview, body)
    assert result.status_code == 201, result.text
    version = next(item for item in result.json()['versions'] if item['kind'] == 'character')
    assert version['content']['artwork_sha256'] == sha256(members['assets/emotion/joy.png']).hexdigest()
    active = narrative_asset({'kind': 'character', 'version': version})
    assert 'artwork_sha256' not in str(active) and 'NEVER EXECUTE' not in str(active)
    assert 'never-fetch' not in str(active)
    assert publish_import(client, preview, body).json() == result.json()


def test_byaf_proposals_preserve_every_scenario_and_do_not_activate_history(client):
    raw = zipped(byaf_members(), ZIP_STORED)
    preview = stage(client, raw, 'reader.byaf')
    assert preview['source_format'] == 'byaf-v1' and preview['card_version'] is None
    character = preview['drafts'][0]['content']
    assert character['text'] == 'A patient cartographer. 🌧️'
    assert character['scenario'] == 'At the rainy harbor.'
    assert character['example_dialogue'] == 'iona: {{literal}} example'
    assert [item['text'] for item in character['greetings']] == ['“Come in.”', 'Farewell.']
    assert 'PRIOR CONVERSATION' not in str(preview['drafts'])
    reference = client.get(f"/api/library-imports/{preview['id']}/document", params={'path': 'byaf/scenarios/1.md'})
    assert reference.status_code == 404  # Only exact generated paths are readable.
    reference = client.get(f"/api/library-imports/{preview['id']}/document", params={'path': 'byaf/scenarios/01.md'}).json()['markdown']
    assert 'PRIOR CONVERSATION' in reference and 'FOREIGN PROMPT' in reference
    result = publish_import(client, preview)
    assert result.status_code == 201, result.text
    assert client.get('/api/stories').json() == []
    with client.app.state.database.connect() as connection:
        assert not connection.execute('SELECT id FROM generations').fetchall()
    assert any('first listed scenario' in issue['message'] for issue in preview['issues'])


@pytest.mark.parametrize('kind', ['charx', 'byaf'])
def test_container_restore_preserves_all_assets_even_when_portrait_removed(client, tmp_path, kind):
    raw = zipped(charx_members() if kind == 'charx' else byaf_members())
    preview = stage(client, raw, f'reader.{kind}')
    body = publish_body(preview)
    next(item for item in body['choices'] if item['part'] == 'character')['content'].pop('artwork_sha256')
    result = publish_import(client, preview, body).json()
    character = next(item for item in result['versions'] if item['kind'] == 'character')
    story = with_book(client, character, 'A container import')
    _, document = backup(client, story)
    assert len(document['data']['library_media']) == 2
    with TestClient(create_app(tmp_path / 'fresh.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as target:
        archived = target.post('/api/archives/imports', json={'content': json.dumps(document)})
        assert archived.status_code == 201, archived.text
        _, mapping = restore(target, archived.json())
        restored = target.get(f"/api/library-imports/{mapping[preview['id']]}").json()
        assert restored['assets'] == preview['assets']
        assert target.get(f"/api/library-imports/{mapping[preview['id']]}/original").content == raw
        for index in (0, 1):
            assert target.get(f"/api/library-imports/{mapping[preview['id']]}/assets/{index}").content == client.get(f"/api/library-imports/{preview['id']}/assets/{index}").content
            assert target.get('/api/library-artwork/' + preview['assets'][index]['sha256']).status_code == 200
        backup(target)


def test_container_detects_content_and_preserves_package_bytes(client):
    raw = zipped(charx_members())
    preview = stage(client, raw, 'mislabeled.json')
    assert preview['format'] == 'charx'
    with ZipFile(BytesIO(client.get(f"/api/library-imports/{preview['id']}/package").content)) as package:
        assert package.read('source.charx') == raw
        report = json.loads(package.read('conversion-report.json'))
        assert len(report['assets']) == 4
    with ZipFile(BytesIO(raw)) as original:
        assert original.read('unlisted.txt') == b'Preserve this unknown attachment exactly.'


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'C:/outside', 'a\\b', 'a/../b', 'a//b', 'a./b', 'a\x00b'])
def test_container_paths_cannot_escape_or_be_ambiguous(client, name):
    members = charx_members()
    members[name] = b'forbidden member'
    rejected(client, zipped(members))


def test_container_rejects_duplicate_paths_symlinks_and_unsupported_compression(client):
    stream = BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with ZipFile(stream, 'w') as archive:
            archive.writestr('card.json', '{}')
            archive.writestr('CARD.JSON', '{}')
    rejected(client, stream.getvalue())
    stream = BytesIO()
    with ZipFile(stream, 'w') as archive:
        link = ZipInfo('linked')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, '/outside')
    rejected(client, stream.getvalue())
    rejected(client, zipped({'card.json': {}}, ZIP_BZIP2))


@pytest.mark.parametrize('members, message', [
    ({f'file-{index}': b'' for index in range(257)}, '256 entries'),
    ({'big': b'x' * (10 * 1024 * 1024 + 1)}, '32 MiB'),
    ({f'file-{index}': b'x' * (9 * 1024 * 1024) for index in range(4)}, '32 MiB'),
])
def test_container_bounds_apply_before_expansion(members, message):
    with pytest.raises(ValueError, match=message):
        read_container(zipped(members))


def test_missing_and_invalid_images_are_explicit_reference_only(client):
    members = charx_members()
    del members['assets/icon/portrait.png']
    members['assets/emotion/joy.png'] = b'not a PNG'
    preview = stage(client, zipped(members), 'broken-images.charx')
    assert [item['status'] for item in preview['assets'][:2]] == ['missing', 'reference']
    assert 'artwork_sha256' not in preview['drafts'][0]['content']
    assert any('missing' in issue['message'].lower() or 'absent' in issue['message'].lower() for issue in preview['issues'])


@pytest.mark.parametrize('mutation', ['new-root-version', 'new-character-version', 'new-scenario-version', 'missing-scenario', 'two-characters', 'bad-identity', 'bad-date', 'bad-template', 'bad-message-type'])
def test_byaf_invalid_variants_reject_before_publication(client, mutation):
    members = deepcopy(byaf_members())
    root, character, scenario = members['manifest.json'], members['characters/iona/character.json'], members['scenarios/arrival.json']
    mutate_byaf(members, root, character, scenario, mutation)
    rejected(client, zipped(members), 'invalid.byaf')


def mutate_byaf(members, root, character, scenario, mutation):
    updates = {'new-root-version': (root, 'schemaVersion', 2), 'new-character-version': (character, 'schemaVersion', 2),
               'new-scenario-version': (scenario, 'schemaVersion', 2), 'two-characters': (root, 'characters', ['a', 'b']),
               'bad-identity': (character, 'id', 'wrong'), 'bad-date': (root, 'createdAt', 'yesterday'),
               'bad-template': (scenario, 'promptTemplate', {}), 'bad-message-type': (scenario, 'messages', [{'type': {}}])}
    if mutation == 'missing-scenario':
        del members['scenarios/arrival.json']
    else:
        target, key, value = updates[mutation]
        target[key] = value


def test_ambiguous_roots_wrong_card_version_and_asset_traversal_reject(client):
    members = charx_members()
    members['manifest.json'] = {}
    rejected(client, zipped(members))
    del members['manifest.json']
    members['card.json']['spec_version'] = '4.0'
    rejected(client, zipped(members))
    members['card.json']['spec_version'] = '3.0'
    members['card.json']['data']['assets'][0]['uri'] = 'embeded://../outside.png'
    rejected(client, zipped(members))


def test_archive_rejects_missing_unselected_container_artwork(client):
    preview = stage(client, zipped(charx_members()), 'protected.charx')
    assert publish_import(client, preview).status_code == 201
    _, document = backup(client)
    document['data']['library_media'] = [row for row in document['data']['library_media'] if row['sha256'] != preview['assets'][1]['sha256']]
    response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert response.status_code == 400 and 'missing its preserved artwork' in response.text
    with client.app.state.database.connect() as connection:
        saved = connection.execute('SELECT conversion FROM library_imports WHERE id=?', (preview['id'],)).fetchone()
        assert len(decode(saved['conversion'])['assets']) == 4


def test_damaged_deflate_is_a_reviewable_import_error(client):
    raw = bytearray(zipped(charx_members()))
    with ZipFile(BytesIO(raw)) as archive:
        entry = archive.infolist()[0]
        offset = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
    raw[offset] = 7  # Invalid DEFLATE block type, inside an otherwise valid ZIP directory.
    response = client.post('/api/library-imports', json={
        'filename': 'damaged.charx', 'source_base64': base64.b64encode(raw).decode()})
    assert response.status_code == 400 and 'damaged' in response.text
    assert client.get('/api/library').json() == []
