from copy import deepcopy

import pytest

from server.database import decode, encode
from server.errors import DomainError
from server.memory.summary_context import parse_summary
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_story_summaries import detail, publication, setup, started

SOURCE = {'id': 'message:one@0:100:abc', 'source_id': 'message:one', 'node_id': 'one',
          'text': 'Elin did not\nopen the gate. She waited.'}


def output(identifier=None, quote='did not open the gate.'):
    return {'items': [{'source_id': identifier or SOURCE['id'], 'summary': 'Elin waits; the gate is not opened.',
                       'quotes': [quote], 'topics': [], 'aliases': []}]}


def parse(value, sources=None):
    return parse_summary(value, {'content': encode({'sources': sources or [SOURCE]})})


@pytest.mark.parametrize('identifier', [SOURCE['id'], 'message:one', 'one'])
def test_fence_unique_source_id_and_reflow_restore_exact_original(identifier):
    raw = '```json\n' + encode(output(identifier)) + '\n```'
    before = deepcopy(SOURCE)
    result = parse(raw)
    assert result['items'][0]['source_id'] == SOURCE['id']
    assert result['items'][0]['quotes'] == ['did not\nopen the gate.']
    assert SOURCE == before


@pytest.mark.parametrize('quote', ['did open the gate.', 'Did not open the gate.', 'did not open the gate!', '   '])
def test_meaning_punctuation_case_and_empty_quotes_are_not_repaired(quote):
    with pytest.raises(DomainError):
        parse(encode(output(quote=quote)))


@pytest.mark.parametrize('wrapper', [lambda raw: 'Here it is: ' + raw,
    lambda raw: '```json\n' + raw + '\n```\nExtra explanation.',
    lambda raw: '```json\n' + raw + '\n```\n```json\n' + raw + '\n```'])
def test_unstructured_commentary_and_multiple_payloads_remain_errors(wrapper):
    with pytest.raises(DomainError):
        parse(wrapper(encode(output())))


def test_parent_identifier_is_ambiguous_across_chunks_even_when_quote_only_matches_one():
    second = {**SOURCE, 'id': 'message:one@100:200:def', 'text': 'An unrelated next paragraph.'}
    with pytest.raises(DomainError, match='multiple excerpts'):
        parse(encode(output('message:one')), [SOURCE, second])


def test_ambiguous_reflow_and_oversized_original_quote_remain_errors():
    for text in ['did not\nopen the gate. did not\topen the gate.', 'did not' + '\n' * 600 + 'open the gate.']:
        with pytest.raises(DomainError):
            parse(encode(output()), [{**SOURCE, 'text': text}])


def test_aliases_cannot_duplicate_a_chunk_or_escape_supplied_sources():
    duplicate = output()
    duplicate['items'].append(output('one')['items'][0])
    for value in [duplicate, output('message:elsewhere'), {**output(), 'extra': True}]:
        with pytest.raises(DomainError):
            parse(encode(value))


class FormattedProvider:
    async def generate(self, profile, prompt, content):
        source = decode(content)['sources'][0]
        value = output(source['node_id'], ' '.join(source['text'].split()))
        yield ProviderEvent(text='```json\n' + encode(value) + '\n```', done=True)


def test_formatting_recovery_still_requires_review_and_preserves_raw_output_on_restore(client):
    story, _ = setup(client)
    client.app.state.summary_runner.provider = FormattedProvider()
    before = client.get('/api/branches/' + story['branch_id']).json()
    run = started(client, story['branch_id'])
    job = run['jobs'][0]
    assert job['status'] == 'done', job
    assert job['output'].startswith('```json') and job['result']['items'][0]['source_id'].startswith('message:')
    assert run['current_version'] is None
    assert client.get('/api/branches/' + story['branch_id']).json() == before
    response = client.post('/api/summaries/' + run['id'] + '/versions', json=publication(client, run, story['branch_id']))
    assert response.status_code == 201, response.text
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied = detail(client, mapping[run['id']], mapping[story['branch_id']])
    assert copied['jobs'][0]['output'] == job['output']
    assert copied['jobs'][0]['result'] == job['result']
    assert copied['current_version']['result'] == job['result']
