import json

import pytest

from server.archives.format import RECIPE_TABLES, STYLE_ANALYSIS_TABLES
from server.database import decode, encode
from tests.legacy_assessment import dispatch
from tests.test_archives import backup, restore
from tests.test_assessments import settled, setup_assessment
from tests.test_continuity_revision import RevisionProvider, revise
from tests.test_generations import finished, generate
from tests.test_profiles import make_profile
from tests.test_writing_resources import create, pins


def styled_assessment(client, story):
    from server.assessment.preparation import prepare_accepted
    setup_assessment(client, story)
    style = create(client, content={'prose': 'Understated sentences.', 'examples': [{'label': 'Example only', 'text': 'A dragon burned the envelope.'}]})
    pins(client, story, style['id'])
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    prepared = prepare_accepted(client.app.state.database, story['branch_id'], branch['head_id'])
    dispatch(client, prepared)
    return settled(client, prepared['assessment_id']), style


@pytest.mark.parametrize('legacy', [False, True])
def test_beat_assessment_omits_prose_guidance_but_preserves_historical_inputs(client, story, monkeypatch, legacy):
    if legacy:
        from server.assessment import context, preparation
        original_context, original_plan = context.assessment_writer_context, preparation.assessment_plan

        def legacy_plan(*args):
            result = original_plan(*args)
            result.pop('assessment_context_version', None)
            return result

        monkeypatch.setattr(context, 'assessment_writer_context', lambda writer: original_context(writer, 1))
        monkeypatch.setattr(preparation, 'assessment_plan', legacy_plan)
    run, style = styled_assessment(client, story)
    job = run['jobs'][0]
    assert job['status'] == 'done', job['error']
    assert run['snapshot'].get('assessment_context_version') == (None if legacy else 2)
    writer = decode(run['snapshot']['writer_snapshot']['content'])
    actual = decode(job['snapshot']['content'])['context']
    assert writer['writing_guidance']['style']['id'] == style['id']
    assert ('writing_guidance' in actual) == legacy
    assert actual['history'] == writer['history']
    assert len(client.app.state.assessment_runner.provider.calls) == 1
    assert not client.app.state.runner.provider.calls
    file, document = backup(client, story)
    if legacy:
        document['version'] = 48
        for table in STYLE_ANALYSIS_TABLES + RECIPE_TABLES:
            assert document['data'].pop(table) == []
        response = client.post('/api/archives/imports', json={'content': json.dumps(document)})
        assert response.status_code == 201, response.text
        file = response.json()
    _, mapping = restore(client, file)
    restored = client.get(f"/api/assessments/{mapping[run['id']]}").json()
    assert restored['jobs'][0]['snapshot']['content'] == job['snapshot']['content']
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)


@pytest.mark.parametrize('damage', ['context', 'version', 'legacy'])
def test_new_assessment_archive_enforces_its_recorded_prose_scope(client, story, damage):
    run, _ = styled_assessment(client, story)
    _, document = backup(client, story)
    if damage == 'legacy':
        document['version'] = 48
    elif damage == 'version':
        row = next(row for row in document['data']['assessment_runs'] if row['id'] == run['id'])
        snapshot = decode(row['snapshot'])
        snapshot['assessment_context_version'] = 3
        row['snapshot'] = encode(snapshot)
    else:
        row = next(row for row in document['data']['assessment_jobs'] if row['id'] == run['jobs'][0]['id'])
        snapshot = decode(row['snapshot'])
        content = decode(snapshot['content'])
        content['context']['writing_guidance'] = decode(run['snapshot']['writer_snapshot']['content'])['writing_guidance']
        snapshot['content'] = encode(content)
        row['snapshot'] = encode(snapshot)
    imported = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert imported.status_code == 400, imported.text


@pytest.mark.parametrize('mode', ['full', 'long'])
def test_continuity_revision_keeps_the_original_style_after_story_defaults_change(client, mode):
    story = client.post('/api/stories', json={'title': 'Frozen revision style', 'settings': {'memory': {'mode': mode}}}).json()
    old_style = create(client, content={'prose': 'Concrete verbs.', 'examples': [{'label': 'Sample only', 'text': 'The kettle cooled.'}]})
    pins(client, story, old_style['id'])
    make_profile(client, 'Writer', primary=True)
    provider = RevisionProvider()
    client.app.state.runner.provider = provider
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    run = generate(client, story, revision=branch['revision'])
    candidate = finished(client, run['id'])['candidates'][0]
    original_context = decode(provider.calls[0][2])
    later_style = create(client, name='Later voice', content={'prose': 'Flowing sentences.'})
    pins(client, story, later_style['id'])
    response = revise(client, candidate)
    assert response.status_code == 201, response.text
    result = finished(client, run['id'])
    assert result['candidates'][-1]['status'] == 'done'
    assert len(provider.calls) == 2
    context = decode(provider.calls[-1][2])['context']
    assert context == original_context and context['writing_guidance']['style']['id'] == old_style['id']
    assert client.get(f"/api/branches/{story['branch_id']}").json()['messages'] == []
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()
    assert restored['candidates'][-1]['usage']['continuity_revision']['content'] == provider.calls[-1][2]


def test_phrase_cleanup_receives_and_restores_the_original_writing_style(client, story):
    from tests.test_cleanup import setup, start
    style = create(client, content={'rhythm': 'Short, quiet sentences.', 'examples': [{'label': 'Sample only', 'text': 'Rain traced the glass.'}]})
    pins(client, story, style['id'])
    provider = setup(client, story)
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    run, _ = start(client, story, revision=branch['revision'])
    candidate = finished(client, run['id'])['candidates'][0]
    cleanup = candidate['cleanup']
    assert cleanup['status'] == 'done' and cleanup['snapshot']['protocol'] == 2
    assert len(provider.calls) == 2
    guidance = decode(provider.calls[-1][2])['writer_guidance']['writing_guidance']
    assert guidance == decode(provider.calls[0][2])['writing_guidance']
    file, document = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get(f"/api/generations/{mapping[run['id']]}").json()['candidates'][0]['cleanup']
    assert restored['snapshot']['content'] == cleanup['snapshot']['content']
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)
    row = next(row for row in document['data']['candidate_cleanups'] if row['id'] == cleanup['id'])
    snapshot = decode(row['snapshot'])
    snapshot['guidance']['writing_guidance']['style']['content']['rhythm'] = 'Changed after generation.'
    content = decode(snapshot['content'])
    content['writer_guidance'] = snapshot['guidance']
    snapshot['content'] = encode(content)
    row['snapshot'] = encode(snapshot)
    imported = client.post('/api/archives/imports', json={'content': json.dumps(document)})
    assert imported.status_code == 400 and 'original writer request' in imported.text
