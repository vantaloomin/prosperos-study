"""Derived context must be opt-in, smaller, explicitly labeled and replayable."""
import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.generation_context import generation_snapshot
from server.generation_models import GenerateRequest
from server.memory.budget import token_estimate
from server.memory.chunks import compile_chunks
from server.memory.packet import assemble_memory
from server.memory.source_packet import assemble_sources
from server.memory.source_replay import replay_sources
from server.memory.summary_excerpt import AUTHORITY, smaller_summary, summary_items
from tests.test_archives import backup, restore
from tests.test_context_inspector import preview, read_section
from tests.test_generations import DraftProvider, finished
from tests.test_history import append
from tests.test_memory import fixture_context, profiles, small_profile
from tests.test_reviews import ReviewProvider, finished_review, start
from tests.test_scenes import choose, get_plan, legacy_scene_creation, run_stage
from tests.test_story_summaries import SummaryProvider, fork, publication, started

OPENING = 'Mara promised to return the brass observatory key to Ivo before the eclipse. '
OLD = OPENING + 'Mara considered the observatory key and her promise to Ivo before the eclipse. ' * 23
POLICY = {'mode': 'long', 'summary_context': True, 'summary_recall': False}


def fixture():
    context = fixture_context()
    context['history'][0]['text'] = OLD
    context['story']['settings']['memory'] = dict(POLICY)
    chunk = compile_chunks('message:n0', 'narrator contribution', OLD)[0]
    aid = {'source_id': chunk.id, 'summary': 'Mara promises Ivo the key before the eclipse; fulfillment is unknown.',
           'quotes': [OPENING.strip()], 'topics': [], 'aliases': ['lunar doorway'],
           'version_id': 'reviewed-1', 'source_sha256': chunk.digest}
    return context, {chunk.id: aid}


def specialist(context):
    return {'stage': 'scene-beats', 'director_direction': context['direction'],
            'sources': [{'id': 'message:' + row['id'], 'title': row['role'] + ' contribution',
                         'kind': 'accepted', 'text': row['text']} for row in context['history']]}


def test_bounded_summary_packets_separate_interpretation_from_exact_evidence():
    context, aids = fixture()
    original = deepcopy(context)
    packet, receipt = assemble_memory(context, 'Write.', profiles(4096, 8192), summary_aids=aids)
    summaries = packet['reviewed_summaries']
    assert len(summaries) == 1 and summaries[0]['text'] == next(iter(aids.values()))['summary']
    assert summaries[0]['grounding_quotes'] == [OPENING.strip()] and summaries[0]['authority'] == AUTHORITY
    assert summaries[0]['sha256'] == hashlib.sha256(OLD.encode()).hexdigest()
    assert context == original and packet['history'][-1] == context['history'][-1]
    assert not any(row['source_id'] == 'message:n0' for row in packet['recalled_passages'])
    assert receipt['coverage']['summarized_messages'] == 1 and receipt['receipt_version'] == 4
    assert token_estimate('Write.', packet) + receipt['overhead_margin'] <= 3584
    assert (packet, receipt) == assemble_memory(context, 'Write.', profiles(8192, 4096), summary_aids=aids)
    source = specialist(context)
    prepared, memory = assemble_sources(source, 'Write.', profiles(4096), POLICY, aids)
    assert len(summary_items(prepared)) == 1 and memory['coverage']['summarized_passages'] == 1
    saved = {'content': encode(prepared), 'source_memory': memory}
    assert replay_sources(source, saved, aids) == prepared
    assert token_estimate('Write.', prepared) + memory['overhead_margin'] <= 3584


@pytest.mark.parametrize('mode,flag,limit', [('full', True, 4096), ('long', False, 4096), ('long', True, 65536)])
def test_disabled_full_or_fitting_context_keeps_originals(mode, flag, limit):
    context, aids = fixture()
    context['story']['settings']['memory'].update(mode=mode, summary_context=flag)
    packet, _ = assemble_memory(context, 'Write.', profiles(limit), summary_aids=aids)
    assert not summary_items(packet)
    source = specialist(context)
    prepared, _ = assemble_sources(source, 'Write.', profiles(limit), context['story']['settings']['memory'], aids)
    assert not summary_items(prepared)


def test_no_automatic_alias_ranking_or_enlarged_summary_and_blind_scope():
    context, aids = fixture()
    context['direction'] = 'lunar doorway'
    context['history'][-1]['text'] = 'They sit down.'
    packet, _ = assemble_memory(context, 'Write.', profiles(4096), summary_aids=aids)
    assert not summary_items(packet)
    context['story']['settings']['memory']['summary_recall'] = True
    packet, _ = assemble_memory(context, 'Write.', profiles(4096), summary_aids=aids)
    assert summary_items(packet)
    chunk = compile_chunks('message:n0', '', OPENING)[0]
    aid = {**next(iter(aids.values())), 'source_sha256': chunk.digest}
    assert smaller_summary(chunk.evidence(), aid) is None
    source = {**specialist(context), 'scope': 'blind'}
    assert assemble_sources(source, 'Write.', profiles(4096), POLICY, aids) == (source, None)


def test_required_citations_and_ooc_never_become_summaries():
    context, aids = fixture()
    context['history'][1].update(role='ooc', text='Keep this private author direction exact.')
    source = specialist(context)
    source['findings'] = [{'source_id': 'message:n0', 'quote': OPENING}]
    packet, memory = assemble_sources(source, 'Review.', profiles(4096), POLICY, aids)
    assert not summary_items(packet) and source['sources'][0] in packet['sources'] and source['sources'][1] in packet['sources']
    assert replay_sources(source, {'content': encode(packet), 'source_memory': memory}) == packet


@pytest.mark.parametrize('kind', ['legacy-algorithm', 'false-marker', 'quote', 'coverage', 'source'])
def test_specialist_replay_rejects_summary_receipt_tampering(kind):
    context, aids = fixture()
    source = specialist(context)
    packet, memory = assemble_sources(source, 'Review.', profiles(4096), POLICY, aids)
    item = next(row for row in memory['selection'] if row.get('reviewed_summary'))
    if kind == 'legacy-algorithm':
        memory.update(algorithm='prospero-source-reviewed-v6', receipt_version=2)
    elif kind == 'false-marker':
        item['reviewed_summary'] = False
    elif kind == 'quote':
        item['reviewed_aid']['quotes'] = ['Invented quotation.']
    elif kind == 'coverage':
        memory['coverage']['summarized_passages'] += 1
    else:
        item['sha256'] = '0' * 64
    with pytest.raises(DomainError):
        replay_sources(source, {'content': encode(packet), 'source_memory': memory}, aids)


def setup_story(client):
    profile = small_profile(client)
    story = client.post('/api/stories', json={'title': 'Condensed history', 'opening_text': OLD,
                        'settings': {'memory': POLICY, 'disabled_prompts': []}}).json()
    client.app.state.summary_runner.provider = SummaryProvider()
    run = started(client, story['branch_id'])
    body = publication(client, run, story['branch_id'])
    body['result']['items'][0].update(summary='Mara promises Ivo the key before the eclipse; fulfillment is unknown.',
                                    quotes=[OPENING.strip()], topics=[], aliases=['lunar doorway'])
    result = client.post('/api/summaries/' + run['id'] + '/versions', json=body)
    assert result.status_code == 201, result.text
    texts = fixture_context()['history'][1:]
    nodes = [append(client, story['branch_id'], row['text'], index + 1) for index, row in enumerate(texts)]
    return story, profile, run, result.json(), nodes


def snapshot(client, branch_id):
    branch = client.get('/api/branches/' + branch_id).json()
    with client.app.state.database.connect() as connection:
        return generation_snapshot(connection, branch_id, GenerateRequest(operation_id=uuid4().hex,
            expected_revision=branch['revision'], direction='The observatory key promise.'))[0]


def test_writer_comparison_inspection_preservation_and_double_restore(client):
    story, first, _, version, _ = setup_story(client)
    second = small_profile(client, 'Larger', 8192)
    branch = client.get('/api/branches/' + story['branch_id']).json()
    report, body = preview(client, story, expected_revision=branch['revision'],
                           profile_ids=[first['profile_id'], second['profile_id']], direction='The observatory key promise.')
    assert report['coverage']['summarized_messages'] == 1
    section = read_section(client, story, report, body, 'reviewed_summaries', view='readable')
    assert section.status_code == 200 and AUTHORITY in section.json()['text'] and OPENING.strip() in section.json()['text']
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    created = client.post('/api/branches/' + story['branch_id'] + '/generations', json={**body, 'operation_id': uuid4().hex})
    assert created.status_code == 201, created.text
    result = finished(client, created.json()['id'])
    frozen = result['snapshot']
    assert frozen['summary_links'][0]['version_id'] == version['id']
    assert len(provider.calls) == 2 and provider.calls[0][1:] == provider.calls[1][1:]
    assert client.get('/api/branches/' + story['branch_id']).json() == branch
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    with client.app.state.database.connect() as connection:
        copied = decode(connection.execute('SELECT snapshot FROM generations WHERE id=?', (mapping[result['id']],)).fetchone()['snapshot'])
    assert copied['content'] == frozen['content']
    assert copied['summary_links'][0]['version_id'] == mapping[version['id']]
    next_file, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, next_file)


@pytest.mark.parametrize('tamper', ['summary', 'quote', 'authority', 'binding', 'receipt', 'omitted'])
def test_writer_archive_rejects_changed_derived_content_even_with_rehashed_inputs(client, tamper):
    story, _, _, _, _ = setup_story(client)
    client.app.state.runner.provider = DraftProvider()
    branch = client.get('/api/branches/' + story['branch_id']).json()
    response = client.post('/api/branches/' + story['branch_id'] + '/generations', json={
        'operation_id': uuid4().hex, 'expected_revision': branch['revision'], 'direction': 'The observatory key promise.'})
    assert response.status_code == 201, response.text
    finished(client, response.json()['id'])
    _, archive = backup(client, story)
    row = archive['data']['generations'][0]
    saved = decode(row['snapshot'])
    content = decode(saved['content'])
    item = content['reviewed_summaries'][0]
    if tamper == 'summary':
        item['text'] = 'Mara has already fulfilled the promise.'
    elif tamper == 'quote':
        item['grounding_quotes'] = ['Fabricated evidence.']
    elif tamper == 'authority':
        item['authority'] = 'Established Canon fact.'
    elif tamper == 'binding':
        saved['summary_links'] = []
    elif tamper == 'receipt':
        saved['memory']['summary_context'] = []
    else:
        content.pop('reviewed_summaries')
        saved['summary_links'] = []
    saved['content'] = encode(content)
    saved['memory']['content_sha256'] = hashlib.sha256(saved['content'].encode()).hexdigest()
    row['snapshot'] = encode(saved)
    with pytest.raises(DomainError):
        parse_archive(encode(archive))


def test_disable_replacement_branch_and_publication_invalidate_new_context(client):
    from server.generation_preparation import prepare_writer
    story, _, run, version, _ = setup_story(client)
    branch_id = story['branch_id']
    before = snapshot(client, branch_id)
    assert summary_items(decode(before['content']))
    first = client.get('/api/branches/' + branch_id).json()['messages'][0]['id']
    changed = fork(client, branch_id, first, 'No promise was made.')
    assert not summary_items(decode(snapshot(client, changed)['content']))
    body = GenerateRequest(operation_id=uuid4().hex, expected_revision=before['branch']['revision'])
    with client.app.state.database.connect() as connection:
        prepared = prepare_writer(connection, branch_id, body)
    response = client.post('/api/summaries/' + run['id'] + '/versions', json=publication(
        client, run, branch_id, expected_version_id=version['id'], enabled=False))
    assert response.status_code == 201, response.text
    assert not summary_items(decode(snapshot(client, branch_id)['content']))
    with client.app.state.database.connect(write=True) as connection:
        with pytest.raises(DomainError, match='while context was being assembled'):
            prepared.validate(connection, body)


def test_historical_and_scene_requests_restore_and_continue_with_live_summary_links(client):
    story, _, _, _, nodes = setup_story(client)
    branch_id = story['branch_id']
    branch = client.get('/api/branches/' + branch_id).json()
    client.app.state.review_runner.provider = ReviewProvider()
    review, _ = start(client, story, {'expected_revision': branch['revision'], 'from_node_id': nodes[-1],
        'through_node_id': nodes[-1], 'steps': [{'key': 'review-continuity'}]})
    result = finished_review(client, review['id'])
    assert result['jobs'][0]['status'] == 'done'
    assert summary_items(decode(result['jobs'][0]['snapshot']['content']))
    client.app.state.scene_runner.provider = GroundedSceneProvider()
    with legacy_scene_creation():
        created = client.post('/api/branches/' + branch_id + '/scenes', json={'operation_id': uuid4().hex,
            'expected_revision': branch['revision'], 'title': 'The promise', 'direction': 'The observatory key promise.',
            'propose_options': False, 'dialogue_split': False})
    assert created.status_code == 201, created.text
    run_id = created.json()['id']
    job = run_stage(client, run_id, 'scene-beats')[0]
    assert job['status'] == 'done' and summary_items(decode(job['snapshot']['content']))
    choose(client, run_id, job)
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied_id = mapping[run_id]
    after = run_stage(client, copied_id, 'scene-brief')[0]
    assert after['status'] == 'done', after
    links = after['snapshot']['summary_links']
    assert links and links[0]['version_id'] != links[0]['frozen_version_id']
    assert get_plan(client, copied_id)['snapshot']['summary_aid_links']
    next_file, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch_id]})
    restore(client, next_file)


@pytest.mark.parametrize('consumer', ['review', 'brief', 'revision', 'continuity'])
def test_interpretations_cannot_be_cited_as_exact_prose(consumer):
    from server.scenes.continuity_models import ContinuityChange, validate_change
    from server.scenes.output import validate_result
    from server.scenes.revision_models import validate_evidence
    from server.workflow.runner import parse_review
    context, aids = fixture()
    packet, _ = assemble_sources(specialist(context), 'Write.', profiles(4096), POLICY, aids)
    source = summary_items(packet)[0]
    def check(quote):
        evidence = {'source_id': source['id'], 'quote': quote}
        if consumer == 'review':
            result = {'summary': 'Fixture', 'findings': [{**evidence, 'severity': 'soft', 'explanation': 'Check uncertainty.', 'suggestion': 'Keep open.'}]}
            return parse_review(encode(result), encode(packet))
        if consumer == 'brief':
            return validate_result('scene-brief', {'summary': 'Fixture', 'facts': [{**evidence, 'relevance': 'Keep open.'}], 'unknowns': []}, encode(packet))
        if consumer == 'revision':
            return validate_evidence([evidence], packet['sources'])
        change = ContinuityChange(id='grounded-fact', action='add', kind='fact', subject='Recorded fact',
                                  text='Preserve the sourced observation.', reason='Use exact prose evidence.',
                                  evidence=[evidence, {'source_id': 'scene:checked', 'quote': 'Checked prose'}])
        return validate_change(change.model_dump(),
                               {source['id']: source, 'scene:checked': {'text': 'Checked prose'}}, {})
    with pytest.raises(DomainError):
        check(source['text'])
    check(source['grounding_quotes'][0])


def test_cited_summary_is_carried_once_with_its_authority_and_exact_quotes():
    from server.memory.source_evidence import carry_evidence
    context, aids = fixture()
    original = specialist(context)
    packet, _ = assemble_sources(original, 'Write.', profiles(4096), POLICY, aids)
    summary = summary_items(packet)[0]
    carried = carry_evidence(original['sources'], {summary['id']}, packet['sources'])
    inputs = {**original, 'sources': carried, 'findings': [{'source_id': summary['id'], 'quote': OPENING.strip()}]}
    next_packet, memory = assemble_sources(inputs, 'Write.', profiles(4096), POLICY, aids)
    assert summary_items(next_packet) == [{**summary, 'kind': 'review evidence'}]
    assert 'not summaries' not in next_packet['memory_guidance']
    assert memory['coverage']['summarized_passages'] == 1
    assert replay_sources(inputs, {'content': encode(next_packet), 'source_memory': memory}, aids) == next_packet


def test_excluded_prose_does_not_return_as_a_summary():
    context, aids = fixture()
    key = next(iter(aids))
    context['author_memory'] = {'entries': [{'kind': 'emphasis', 'stance': 'exclude',
        'sources': [{'id': key, 'node_id': 'n0', 'start': 0, 'end': len(OLD), 'sha256': hashlib.sha256(OLD.encode()).hexdigest()}]}]}
    packet, _ = assemble_memory(context, 'Write.', profiles(4096), summary_aids=aids)
    assert not summary_items(packet)
    sources = {**specialist(context), 'author_memory': context['author_memory']}
    prepared, _ = assemble_sources(sources, 'Write.', profiles(4096), POLICY, aids)
    assert not summary_items(prepared)


class GroundedSceneProvider:
    async def generate(self, profile, prompt, content):
        from server.providers.events import ProviderEvent
        from tests.test_scene_drafting import DraftProvider as SceneDraftProvider
        context = decode(content)
        if context['stage'] == 'scene-brief':
            source = summary_items(context)[0]
            result = {'summary': 'Retain uncertainty.', 'facts': [{'source_id': source['id'],
                      'quote': source['grounding_quotes'][0], 'relevance': 'The promise remains unresolved.'}], 'unknowns': ['Whether the promise is fulfilled.']}
            yield ProviderEvent(text=encode(result), done=True)
        elif context['stage'] == 'scene-draft':
            from tests.test_scene_drafting import fixture_result
            result = fixture_result(context)
            result['blocks'][0]['text'] += ' Mara considers the observatory key and her promise to Ivo before the eclipse.'
            yield ProviderEvent(text=encode(result), done=True)
        else:
            async for event in SceneDraftProvider().generate(profile, prompt, content):
                yield event


class GroundedReviewer:
    async def generate(self, profile, prompt, content):
        from server.providers.events import ProviderEvent
        source = summary_items(decode(content))[0]
        findings = [{'severity': severity, 'source_id': source['id'], 'quote': source['grounding_quotes'][0],
                     'explanation': 'Fixture evidence handoff.', 'suggestion': 'Keep the open decision.'}
                    for severity in ('soft', 'hold', 'hard')]
        yield ProviderEvent(text=encode({'summary': 'Grounding quote fixture.', 'findings': findings}), done=True)


def test_summary_evidence_survives_scene_review_triage_patch_and_archive(client):
    from tests.test_scene_continuity import ContinuityProvider
    from tests.test_scene_patches import PatchProvider, selected_stage
    from tests.test_scene_reviews import scene_body
    from tests.test_scene_revisions import RevisionProvider, rejected_claim
    from tests.test_scenes import decide
    story, _, _, _, _ = setup_story(client)
    small_profile(client, limit=8192)
    branch_id = story['branch_id']
    branch = client.get('/api/branches/' + branch_id).json()
    client.app.state.scene_runner.provider = GroundedSceneProvider()
    with legacy_scene_creation():
        created = client.post('/api/branches/' + branch_id + '/scenes', json={'operation_id': uuid4().hex,
            'expected_revision': branch['revision'], 'title': 'The promise', 'direction': 'The observatory key promise.',
            'propose_options': False, 'dialogue_split': False})
    assert created.status_code == 201, created.text
    run_id = created.json()['id']
    for key in ('scene-beats', 'scene-brief'):
        job = run_stage(client, run_id, key)[0]
        assert job['status'] == 'done', job['error']
        choose(client, run_id, job)
    decide(client, run_id, 'approve')
    for key in ('scene-draft', 'scene-coverage'):
        job = selected_stage(client, run_id, key)
        assert summary_items(decode(job['snapshot']['content']))
    client.app.state.review_runner.provider = GroundedReviewer()
    review, _ = start(client, story, scene_body(client, run_id, [{'key': 'review-continuity'}]))
    report = finished_review(client, review['id'])['jobs'][0]
    assert report['status'] == 'done', report['error']
    client.app.state.scene_runner.provider = RevisionProvider()
    triage = run_stage(client, run_id, 'scene-triage', review_job_ids=[report['id']])[0]
    assert triage['status'] == 'done', triage['error']
    choose(client, run_id, triage)
    rejected_claim(client, run_id)
    decide(client, run_id, 'approve-revision', {'package': 'C', 'confirmed_hold_ids': ['t2']})
    client.app.state.scene_runner.provider = PatchProvider()
    for key in ('scene-patch', 'scene-patch-check'):
        selected_stage(client, run_id, key)
    client.app.state.scene_runner.provider = ContinuityProvider()
    selected_stage(client, run_id, 'scene-continuity')
    assert client.get('/api/branches/' + branch_id).json() == branch
    archive, _ = backup(client, story)
    _, mapping = restore(client, archive)
    next_archive, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch_id]})
    restore(client, next_archive)



def test_assessment_and_prepared_chance_preserve_summary_receipts(client, monkeypatch):
    from tests.test_assessments import AssessmentProvider
    from tests.test_mechanics import configure
    story, _, _, _, _ = setup_story(client)
    small_profile(client, limit=8192)
    monkeypatch.setattr('server.assessment.context.secrets.token_hex', lambda *_: '03' * 32)
    configure(client, story, automatic_assessment=True, chance=100, cooldown=0)
    scribe = client.post('/api/profiles', json={'name': 'Scribe', 'config': {
        'provider': 'local', 'model': 'test', 'context_tokens': 16384, 'max_output_tokens': 512}}).json()
    routing = client.get(f"/api/stories/{story['story_id']}/workflow").json()
    assert client.put(f"/api/stories/{story['story_id']}/workflow", json={
        'expected_revision': routing['story_revision'], 'step_profiles': {'scribe': scribe['profile_id']}}).status_code == 200
    client.app.state.assessment_runner.provider = AssessmentProvider()
    client.app.state.runner.provider = DraftProvider()
    branch = client.get('/api/branches/' + story['branch_id']).json()
    from server.assessment.preparation import prepare_accepted
    from server.assessment.service import Assessments
    from tests.test_post_acceptance import complete
    queued = prepare_accepted(client.app.state.database, story['branch_id'], branch['head_id'])
    run = complete(client, Assessments(client.app.state.database).detail(queued['assessment_id']))
    assert run['opportunity_id'] and not run['generation_id'], run['error']
    request = client.post('/api/branches/' + story['branch_id'] + '/generations', json={
        'operation_id': uuid4().hex, 'expected_revision': branch['revision'], 'direction': 'The observatory key promise.'})
    assert request.status_code == 201, request.text
    result = finished(client, request.json()['id'])
    writer = result['snapshot']
    assert summary_items(decode(writer['content'])) and writer['summary_links']
    assert writer['memory']['content_sha256'] == hashlib.sha256(writer['content'].encode()).hexdigest()
    after = client.get('/api/branches/' + story['branch_id']).json()
    assert all(after[key] == branch[key] for key in ('messages', 'revision', 'head_id'))
    assert after['mechanics']['state'] == branch['mechanics']['state']
    archive, _ = backup(client, story)
    _, mapping = restore(client, archive)
    next_archive, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, next_archive)



@pytest.mark.parametrize('tamper', ['missing-receipt', 'missing-version', 'changed-summary', 'missing-bindings'])
def test_scene_archive_cannot_strip_summary_validation_metadata(client, tamper):
    story, _, _, _, _ = setup_story(client)
    branch = client.get('/api/branches/' + story['branch_id']).json()
    client.app.state.scene_runner.provider = GroundedSceneProvider()
    with legacy_scene_creation():
        created = client.post('/api/branches/' + story['branch_id'] + '/scenes', json={
            'operation_id': uuid4().hex, 'expected_revision': branch['revision'], 'title': 'Archive check',
            'direction': 'The observatory key promise.', 'propose_options': False})
    assert created.status_code == 201, created.text
    job = run_stage(client, created.json()['id'], 'scene-beats')[0]
    assert summary_items(decode(job['snapshot']['content']))
    _, archive = backup(client, story)
    row = archive['data']['scene_jobs'][0]
    saved = decode(row['snapshot'])
    content = decode(saved['content'])
    item = summary_items(content)[0]
    if tamper == 'missing-receipt':
        saved.pop('source_memory')
    elif tamper == 'missing-version':
        item.pop('summary_version_id')
    elif tamper == 'changed-summary':
        item['text'] = 'The promise has been fulfilled.'
    else:
        saved['summary_links'] = []
    saved['content'] = encode(content)
    if saved.get('source_memory'):
        saved['source_memory']['content_sha256'] = hashlib.sha256(saved['content'].encode()).hexdigest()
    row['snapshot'] = encode(saved)
    with pytest.raises(DomainError):
        parse_archive(encode(archive))



def test_retry_preserves_original_summary_after_a_later_exclusion(client):
    from tests.test_generations import WaitingProvider
    story, _, run, version, _ = setup_story(client)
    branch_id = story['branch_id']
    branch = client.get('/api/branches/' + branch_id).json()
    client.app.state.runner.provider = WaitingProvider()
    request = client.post('/api/branches/' + branch_id + '/generations', json={
        'operation_id': uuid4().hex, 'expected_revision': branch['revision'], 'direction': 'The observatory key promise.'})
    assert request.status_code == 201, request.text
    candidate = request.json()['candidate_ids'][0]
    assert client.post('/api/candidates/' + candidate + '/cancel').status_code == 200
    original = finished(client, request.json()['id'])['snapshot']
    assert summary_items(decode(original['content']))
    excluded = client.post('/api/summaries/' + run['id'] + '/versions', json=publication(
        client, run, branch_id, expected_version_id=version['id'], enabled=False))
    assert excluded.status_code == 201, excluded.text
    assert not summary_items(decode(snapshot(client, branch_id)['content']))
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    assert client.post('/api/candidates/' + candidate + '/retry').status_code == 200
    retried = finished(client, request.json()['id'])
    assert retried['snapshot'] == original and provider.calls[0][2] == original['content']
    archive, _ = backup(client, story)
    restore(client, archive)



@pytest.mark.parametrize('enabled', [False, True])
def test_condensation_does_not_implicitly_enable_sidebar_alias_recall(client, enabled):
    from tests.test_sidebar import CollaboratorProvider, ask, settle, thread
    from tests.test_story_summaries import update_memory
    story, _, _, _, _ = setup_story(client)
    update_memory(client, story['story_id'], enabled)
    branch = client.get('/api/branches/' + story['branch_id']).json()
    client.app.state.side_runner.provider = CollaboratorProvider()
    conversation = thread(client, story)
    result = ask(client, conversation, story, revision=branch['revision'], question='lunar doorway')
    settle(client)
    with client.app.state.database.connect() as connection:
        saved = decode(connection.execute('SELECT snapshot FROM side_turns WHERE id=?', (result['id'],)).fetchone()['snapshot'])
    original = [item for item in saved['sources'] if ':message:' + branch['messages'][0]['id'] + ':' in item['id']]
    assert original and any('reviewed_aid' in item for item in original) == enabled
    assert summary_items(decode(snapshot(client, story['branch_id'])['content']))
    assert client.get('/api/branches/' + story['branch_id']).json() == branch
