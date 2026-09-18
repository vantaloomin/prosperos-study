import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.format import ARCHIVE_VERSION
from server.background.engine import guidance
from server.background.interpretation_models import InterpretationStart
from server.background.interpretations import Interpretations
from server.database import decode, one
from server.providers.events import ProviderEvent
from tests.prompt_fixtures import saved_prompt
from tests.test_archives import backup, restore
from tests.test_background import prepared, revealed, setup_story, update
from tests.test_profiles import make_profile


def interpretation_output(content, name):
    context = json.loads(content)
    basis = [{'source_id': context['sources'][0]['id'], 'quote': context['sources'][0]['text'][:30]}] if context['sources'] else []
    return {'drives': [{'target_id': item['id'], 'motive': f'{name}: privately recover the missing ledger.',
                       'concealment': 'Hide an unfulfilled promise.', 'expression': 'Watch the ledger when it is mentioned.', 'basis': basis}
                      for item in context['targets']['drives']],
            'hooks': [{'target_id': item['id'], 'event': f'{name}: a possible message about the ledger.',
                       'foreshadowing': 'A sealed envelope waits.', 'conditions': 'Only if the Story reaches the supplied day; leave player choices open.', 'basis': []}
                      for item in context['targets']['hooks']]}


class PrivateProvider:
    def __init__(self, invalid=False):
        self.calls, self.invalid = [], invalid

    async def generate(self, profile, prompt, content):
        self.calls.append((profile, prompt, content))
        output = interpretation_output(content, profile['name'])
        yield ProviderEvent(text='invalid test output' if self.invalid else json.dumps(output), done=True)


async def wait_jobs(client):
    await asyncio.gather(*list(client.app.state.background_runner.tasks.values()))


def start_private(client, story, profiles=None, **values):
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    body = {'expected_revision': revision, 'profile_ids': profiles or [], **values}
    prefix = f"/api/branches/{story['branch_id']}/background/interpretations"
    preview = client.post(prefix + '/preview', json=body)
    assert preview.status_code == 200, preview.text
    body.update(operation_id=uuid4().hex, preview_hash=preview.json()['preview_hash'])
    run = client.post(prefix, json=body)
    assert run.status_code == 201, run.text
    assert client.post(prefix, json=body).json() == run.json()
    client.portal.call(wait_jobs, client)
    return client.get(f"/api/background-interpretations/{run.json()['id']}?reveal=true").json()


def choose_private(client, job, **values):
    return client.post(f"/api/background-jobs/{job['id']}/choose", json={'operation_id': uuid4().hex, **values})


def setup_private(client):
    story, character = setup_story(client)
    receipt = prepared(client, story, character)
    profile = make_profile(client, 'Private writer', primary=True)
    client.app.state.background_runner.provider = PrivateProvider()
    return story, receipt, profile


def test_comparisons_conceal_outputs_and_selection_preserves_randomness_without_story_progress(client):
    story, receipt, first = setup_private(client)
    other = make_profile(client, 'Alternative')
    before = revealed(client, receipt)
    run = start_private(client, story, [first['profile_id'], other['profile_id']])
    assert all(job['status'] == 'done' for job in run['jobs'])
    calls = client.app.state.background_runner.provider.calls
    assert calls[0][1:] == calls[1][1:]
    summary = client.get(f"/api/background-interpretations/{run['id']}").json()
    assert not any(field in summary['jobs'][0] for field in ('snapshot', 'output', 'result', 'usage'))
    assert 'missing ledger' not in json.dumps(summary)
    selected = choose_private(client, run['jobs'][0])
    assert selected.status_code == 200, selected.text
    current = revealed(client, selected.json())
    assert current['result'] == before['result'] and current['recipe'] == before['recipe']
    assert current['interpretation']['content'] == run['jobs'][0]['result']
    assert guidance(current)['selected_private_interpretation']['drives'][0]['motive'].startswith('Private writer')
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []
    assert choose_private(client, run['jobs'][1]).status_code == 409
    alternate = choose_private(client, run['jobs'][1], as_new_branch=True)
    assert alternate.status_code == 200 and alternate.json()['branch_id'] != story['branch_id']
    assert revealed(client, selected.json()) == current


def test_profile_override_prompt_version_and_preview_staleness(client):
    story, _, _ = setup_private(client)
    other = make_profile(client, 'Private specialist')
    endpoint = f"/api/stories/{story['story_id']}/workflow"
    routing = client.get(endpoint).json()
    response = client.put(endpoint, json={'expected_revision': routing['story_revision'], 'step_profiles': {'background-interpretation': other['profile_id']}})
    assert response.status_code == 200, response.text
    run = start_private(client, story)
    assert run['jobs'][0]['snapshot']['profile']['profile_id'] == other['profile_id']
    prefix = f"/api/branches/{story['branch_id']}/background/interpretations"
    body = {'expected_revision': 1}
    preview = client.post(prefix + '/preview', json=body).json()
    prompt = saved_prompt(client, 'background-interpretation')
    changed = client.put('/api/prompts/background-interpretation', json={'expected_version_id': prompt['id'], 'template': prompt['template'] + '\nKeep the setting quiet.'})
    assert changed.status_code == 200
    response = client.post(prefix, json={**body, 'operation_id': uuid4().hex, 'preview_hash': preview['preview_hash']})
    assert response.status_code == 409
    assert client.get(f"/api/background-interpretations/{run['id']}?reveal=true").json()['jobs'][0]['snapshot']['prompt'] == run['jobs'][0]['snapshot']['prompt']


def test_invalid_targets_and_fabricated_evidence_fail_without_mutation(client):
    from server.background.interpretation_context import parse_interpretation
    from server.errors import DomainError
    story, _, _ = setup_private(client)
    run = start_private(client, story)
    job = run['jobs'][0]
    for mutate in ('extra', 'quote', 'date', 'missing'):
        value = deepcopy(job['result'])
        if mutate == 'extra':
            value['drives'].append(value['drives'][0])
        elif mutate == 'quote':
            value['drives'][0]['basis'][0]['quote'] = 'UNSUPPLIED FACT'
        elif mutate == 'date':
            value['hooks'][0]['day'] = 999
        else:
            value['hooks'] = []
        with pytest.raises(DomainError):
            parse_interpretation(json.dumps(value), job['snapshot'])


def test_retry_preserves_inputs_and_disabling_blocks_new_interpretation(client):
    story, receipt, _ = setup_private(client)
    client.app.state.background_runner.provider = PrivateProvider(invalid=True)
    run = start_private(client, story)
    job = run['jobs'][0]
    assert job['status'] == 'error' and choose_private(client, job).status_code == 409
    client.app.state.background_runner.provider = PrivateProvider()
    assert client.post(f"/api/background-jobs/{job['id']}/retry").status_code == 200
    client.portal.call(wait_jobs, client)
    updated = client.get(f"/api/background-interpretations/{run['id']}?reveal=true").json()['jobs'][0]
    assert updated['status'] == 'done' and updated['attempt'] == 2 and updated['snapshot'] == job['snapshot']
    attempts = client.get(f"/api/background-jobs/{job['id']}/attempts/reveal").json()
    assert [attempt['status'] for attempt in attempts] == ['done', 'error']
    update(client, story)
    assert choose_private(client, updated).status_code == 409
    response = client.post(f"/api/branches/{story['branch_id']}/background/interpretations/preview", json={'expected_revision': 2})
    assert response.status_code == 409
    assert revealed(client, receipt)['result']['seed']


def test_selected_interpretations_recover_reexport_and_reroll_drops_old_details(client):
    story, _, _ = setup_private(client)
    run = start_private(client, story)
    selected = choose_private(client, run['jobs'][0]).json()
    update(client, story)
    file, document = backup(client, story)
    assert document['version'] == ARCHIVE_VERSION
    result, mapping = restore(client, file)
    recovered = client.get(f"/api/background-interpretations/{mapping[run['id']]}?reveal=true").json()
    assert recovered['jobs'][0]['snapshot']['content'] == run['jobs'][0]['snapshot']['content']
    restored = revealed(client, {'id': mapping[selected['id']]})
    assert restored['interpretation']['job_id'] == mapping[run['jobs'][0]['id']]
    again, _ = backup(client, {'story_id': result['selection']['storyId'], 'branch_id': result['selection']['branchId']})
    restore(client, again)
    rerolled = prepared(client, story, reroll_of=selected['id'])
    assert 'interpretation' not in revealed(client, rerolled)
    assert 'interpretation' in revealed(client, selected)


def test_unfinished_restore_is_explicit_and_selection_receipt_rolls_back(client, monkeypatch):
    story, _, _ = setup_private(client)
    service = Interpretations(client.app.state.database)
    from server.background.interpretation_models import InterpretationPreview
    preview = service.preview(story['branch_id'], InterpretationPreview(expected_revision=1))
    saved = service.create(story['branch_id'], InterpretationStart(expected_revision=1, operation_id=uuid4().hex, preview_hash=preview['preview_hash']))
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = service.detail(mapping[saved['id']])
    assert restored['jobs'][0]['status'] == 'interrupted'
    assert client.post(f"/api/background-jobs/{mapping[saved['job_ids'][0]]}/retry").status_code == 200
    client.portal.call(wait_jobs, client)
    assert service.detail(mapping[saved['id']])['jobs'][0]['status'] == 'done'
    run = start_private(client, story)
    from server.background.interpretation_models import InterpretationChoice
    def fail(*_args):
        raise RuntimeError('Injected receipt failure')
    monkeypatch.setattr('server.background.interpretations.remember', fail)
    with pytest.raises(RuntimeError, match='Injected'):
        service.choose(run['jobs'][0]['id'], InterpretationChoice(operation_id=uuid4().hex))
    with client.app.state.database.connect() as connection:
        assert one(connection, 'SELECT COUNT(*) AS n FROM background_states')['n'] == 2
        assert one(connection, 'SELECT selected_state_id FROM background_jobs WHERE id=?', (run['jobs'][0]['id'],))['selected_state_id'] is None
        assert decode(one(connection, 'SELECT snapshot FROM background_runs WHERE id=?', (run['id'],))['snapshot'])['branch']['revision'] == 1
