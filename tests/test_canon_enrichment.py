import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.memory.enrichment import parse_enrichment
from server.providers.events import ProviderEvent
from tests.archive_legacy import remove_summaries
from tests.test_archives import backup, restore
from tests.test_authoring import settle
from tests.test_library import with_book
from tests.test_profiles import make_profile

TEXT = '# The gate\n雨 🔑\nThe iron door is called the Moon Gate. It may open at dusk; nobody knows why.\n\n# The witness\nElin claims the key was stolen. This is an allegation, not an established fact.'


class EnrichmentProvider:
    def __init__(self):
        self.calls = []

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        sources = decode(decode(content)['target']['text'])
        cues = [{'source_id': source['id'], 'summary': 'A qualified account of the gate or witness.',
                 'topics': ['testimony'], 'aliases': ['lunar doorway']} for source in sources]
        yield ProviderEvent(text=encode({'summary': 'Source-bound search suggestions.', 'cues': cues}), done=True)


def setup(client):
    first = make_profile(client, 'Enrichment primary', primary=True)
    book = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Gate records', 'content': {'text': TEXT}}).json()
    client.app.state.authoring_runner.provider = EnrichmentProvider()
    return book, first


def preview(client, book, **values):
    content = values.pop('content', book['content'])
    compiled = client.post('/api/canon/compile-preview', json={'name': book['name'], 'content': content}).json()
    body = {'name': book['name'], 'content': content, 'selected': [item['id'] for item in compiled['items']],
            'source_version_id': book['id'], 'draft_id': 'enrichment-fixture', **values}
    response = client.post('/api/canon/enrichment-preview', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def start(client, prepared):
    body = {**prepared['request'], 'preview_hash': prepared['preview_hash'], 'operation_id': uuid4().hex}
    response = client.post('/api/authoring', json=body)
    assert response.status_code == 201, response.text
    assert client.post('/api/authoring', json=body).json() == response.json()
    client.portal.call(settle, client)
    result = client.get('/api/authoring/' + response.json()['id']).json()
    assert all(job['status'] == 'done' for job in result['jobs']), result
    return result


def test_comparisons_and_reviewed_application_preserve_originals_and_story_pins(client):
    book, first = setup(client)
    second = make_profile(client, 'Enrichment alternate')
    story = with_book(client, book, 'Pinned original')
    before = client.get('/api/branches/' + story['branch_id']).json()
    prepared = preview(client, book, profile_ids=[first['profile_id'], second['profile_id']])
    assert prepared['request_count'] == 2 and not client.app.state.authoring_runner.provider.calls
    run = start(client, prepared)
    calls = client.app.state.authoring_runner.provider.calls
    assert len(calls) == 2 and calls[0][1:] == calls[1][1:]
    job = run['jobs'][0]
    edited = deepcopy(job['result']['enrichment'])
    edited[0]['summary'] = 'AUTHOR EDIT: opening at dusk remains uncertain.'
    applied = client.post('/api/canon/enrichment-apply', json={'job_id': job['id'], 'content': book['content'], 'cues': edited})
    assert applied.status_code == 200, applied.text
    content = {**book['content'], **applied.json()}
    assert content['text'] == TEXT and content['canon_recall']['cues'][0]['summary'] == edited[0]['summary']
    assert len(client.get(f"/api/library/{book['asset_id']}/versions").json()) == 1
    published = client.post(f"/api/library/{book['asset_id']}/versions", json={'expected_version_id': book['id'], 'name': book['name'], 'content': content}).json()
    assert published['number'] == 2
    after = client.get('/api/branches/' + story['branch_id']).json()
    assert after['revision'] == before['revision'] and after['head_id'] == before['head_id']
    assert after['attachments'][0]['version_id'] == book['id']
    assert after['attachments'][0]['version'] == before['attachments'][0]['version']
    matches = client.post('/api/canon/compile-preview', json={'name': book['name'], 'content': content, 'query': 'lunar doorway'}).json()
    assert matches['active_cues'] == 2 and matches['items'][0]['text'] in TEXT
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied = client.get('/api/authoring/' + mapping[run['id']]).json()
    assert copied['jobs'][0]['snapshot']['content'] == job['snapshot']['content']
    assert copied['jobs'][0]['result'] == job['result']
    assert client.get(f"/api/library/{mapping[book['asset_id']]}/versions").json()[0]['content']['text'] == TEXT
    second_file, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second_file)


def test_stale_prose_existing_cues_and_foreign_cues_are_rejected(client):
    book, _ = setup(client)
    job = start(client, preview(client, book))['jobs'][0]
    body = {'job_id': job['id'], 'content': book['content'], 'cues': job['result']['enrichment']}
    changed = deepcopy(body)
    changed['content']['text'] += '\nA later edit.'
    assert client.post('/api/canon/enrichment-apply', json=changed).status_code == 409
    applied = client.post('/api/canon/enrichment-apply', json=body).json()
    repeated = {**body, 'content': {**book['content'], **applied}}
    assert client.post('/api/canon/enrichment-apply', json=repeated).status_code == 400
    bad = deepcopy(body)
    bad['cues'][0]['source_id'] = 'outside-the-reviewed-sources'
    assert client.post('/api/canon/enrichment-apply', json=bad).status_code == 400
    result = client.post('/api/canon/compile-preview', json={'content': repeated['content'], 'name': book['name']}).json()
    blocked = client.post('/api/canon/enrichment-preview', json={'content': repeated['content'], 'name': book['name'], 'draft_id': 'x', 'selected': [result['items'][0]['id']]})
    assert blocked.status_code == 409


@pytest.mark.parametrize('kind', ['foreign', 'duplicate', 'too-long', 'unknown-field'])
def test_output_validation_rejects_unscoped_or_malformed_aids(client, kind):
    book, _ = setup(client)
    job = start(client, preview(client, book))['jobs'][0]
    result = decode(job['output'])
    if kind == 'foreign':
        result['cues'][0]['source_id'] = 'other-branch'
    elif kind == 'duplicate':
        result['cues'].append(result['cues'][0])
    elif kind == 'too-long':
        result['cues'][0]['summary'] = 'x' * 1201
    else:
        result['publish'] = True
    with pytest.raises(DomainError):
        parse_enrichment(encode(result), job['snapshot'])


def test_defaults_disabling_and_changed_prompt_invalidate_preview(client):
    book, first = setup(client)
    prepared = preview(client, book)
    assert prepared['jobs'][0]['profile_name'] == first['name']
    second = make_profile(client, 'Canon specialist')
    assert client.put('/api/authoring/defaults', json={'step': 'authoring-enrich', 'profile_id': second['profile_id']}).status_code == 200
    stale = {**prepared['request'], 'preview_hash': prepared['preview_hash'], 'operation_id': uuid4().hex}
    assert client.post('/api/authoring', json=stale).status_code == 409
    assert preview(client, book)['jobs'][0]['profile_name'] == second['name']
    prompts = client.get('/api/prompts').json()
    prompt = next(item for item in prompts if item['key'] == 'authoring-enrich')
    response = client.put('/api/prompts/authoring-enrich/activation', json={'expected_revision': prompt['activation_revision'], 'enabled': False})
    assert response.status_code == 200, response.text
    assert client.post('/api/authoring/preview', json=prepared['request']).status_code == 409


def test_version_19_archives_gain_optional_enrichment_prompt_without_modifying_original(client):
    setup(client)
    _, document = backup(client)
    legacy = deepcopy(document)
    remove_summaries(legacy)
    legacy['version'] = 19
    legacy['prompt_heads'].pop('authoring-enrich')
    legacy['data']['prompt_versions'] = [row for row in legacy['data']['prompt_versions'] if row['key'] != 'authoring-enrich']
    original = deepcopy(legacy)
    upgraded = parse_archive(json.dumps(legacy))
    assert upgraded['version'] == ARCHIVE_VERSION and 'authoring-enrich' in upgraded['prompt_heads']
    assert legacy == original
