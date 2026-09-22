import json

import pytest

from server.errors import DomainError
from server.structured_text import json_payload
from server.writing.recipe_output import parse_recipe_output
from tests.test_archives import backup, restore
from tests.test_recipe_planning import setup
from tests.test_recipe_runs import RecipeProvider, create_run, settled, start_step
from tests.test_side_edits import Provider, ask, reply
from tests.test_side_edits import setup as companion_setup
from tests.test_sidebar import settle
from tests.test_style_analysis import SAMPLES, AnalysisProvider, start
from tests.test_style_analysis import settled as analysis_settled


class FencedProvider:
    def __init__(self, provider):
        self.provider = provider

    async def generate(self, *args):
        async for event in self.provider.generate(*args):
            if event.text:
                event.text = '```json\n' + event.text + '\n```'
            yield event


@pytest.mark.parametrize('task', ['writer', 'review'])
def test_complete_fenced_recipe_outputs_keep_raw_text_and_fixed_authority(client, story, task):
    _, _, body = setup(client, story, {'purpose': 'review' if task == 'review' else 'draft',
                                     'steps': [{'task': task}]})
    client.app.state.recipe_runner.provider = FencedProvider(RecipeProvider())
    identity = create_run(client, story, body)
    start_step(client, identity)
    value = settled(client, identity)
    assert value['progress']['status'] == 'complete'
    assert all(job['output'].startswith('```json\n') and job['result'] for job in value['jobs'])
    assert all(proposal['status'] == 'pending' for proposal in value['proposals'])
    archive, _ = backup(client, story)
    _, mapping = restore(client, archive)
    restored = client.get('/api/recipe-runs/' + mapping[identity]).json()
    assert [job['output'] for job in restored['jobs']] == [job['output'] for job in value['jobs']]


def test_fenced_companion_and_sample_analysis_outputs_remain_reviewable(client, story):
    identity, source, selected = companion_setup(client, story, provider=FencedProvider(Provider()))
    ask(client, identity, selected)
    settle(client)
    response = reply(client, identity)
    assert response['status'] == 'done' and response['output'].startswith('```json\n')
    assert response['edit']['proposals'][0]['status'] == 'pending'
    client.app.state.style_analysis_runner.provider = FencedProvider(AnalysisProvider())
    job_id, _, _ = start(client, {'draft_id': 'fenced-analysis', 'samples': SAMPLES})
    analysis = analysis_settled(client, job_id)
    assert analysis['status'] == 'done' and analysis['output'].startswith('```json\n')
    assert analysis['result']['suggestions'][0]['evidence'][0]['quote'] == 'The kettle cooled.'
    assert client.post('/api/text-targets/read', json={'target': source['ref']}).json() == source
    archive, _ = backup(client, include_sidebar=True)
    _, mapping = restore(client, archive)
    assert reply(client, mapping[identity])['output'] == response['output']
    assert client.get('/api/writing-analyses/' + mapping[job_id]).json()['output'] == analysis['output']


@pytest.mark.parametrize('output', [
    'Here is the answer:\n```json\n{}\n```',
    '```json\n{}\n```\nMore instructions.',
    '```python\n{}\n```',
    '```json\n{}',
    '```json\n{}\n```\n```json\n{}\n```',
    '```json\n{}\n{}\n```',
])
def test_json_envelope_does_not_extract_partial_or_embedded_answers(output):
    with pytest.raises(ValueError):
        json.loads(json_payload(output))


@pytest.mark.parametrize('damage', [
    {'apply': True}, {'source_ids': ['foreign:source']}, {'source_ids': ['recipe:draft', 'recipe:draft']},
])
def test_json_envelope_cannot_grant_authority_or_widen_sources(damage):
    output = {'replacement': '  Preserved wording.\n', 'explanation': 'A proposal.', 'source_ids': ['recipe:draft'], **damage}
    snapshot = {'task': 'writer', 'content': json.dumps({'sources': [{'id': 'recipe:draft', 'text': 'Original.'}]})}
    with pytest.raises(DomainError):
        parse_recipe_output('```json\n' + json.dumps(output) + '\n```', snapshot)


def test_json_envelope_preserves_literal_whitespace_and_backticks_inside_replacement():
    value = {'replacement': '  Literal ```json\n{}\n``` example.\n'}
    assert json.loads(json_payload(' \r\n```JSON\r\n' + json.dumps(value) + '\r\n```\r\n')) == value
