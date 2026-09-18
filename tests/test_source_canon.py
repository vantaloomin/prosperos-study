"""Specialist Canon selection must preserve scope, exact bytes and archive replay."""
import hashlib
from copy import deepcopy

import pytest

from server.character_content import narrative_asset
from server.database import decode, encode
from server.errors import DomainError
from server.memory.budget import token_estimate
from server.memory.source_canon import compact_canon
from server.memory.source_packet import assemble_sources
from server.memory.source_replay import replay_sources
from tests.test_archives import backup, restore
from tests.test_canon_memory import attached
from tests.test_history import append
from tests.test_memory import profiles, small_profile
from tests.test_reviews import ReviewProvider, finished_review, start
from tests.test_scenes import choose, get_plan, run_stage
from tests.test_source_memory import create_long_scene, set_memory, source_context

QUOTE = 'Moon orchids open the brass observatory key vault. Iron dust makes their petals close.\n\n'


def canon_content():
    return {'text': QUOTE + ('# Transit\n\nCanal barges carry grain through the western district.\n\n' * 450),
            'required_rule': 'Never narrate a decision for the player.',
            'canon_recall': {'mode': 'relevant', 'cues': [{'start': 0, 'end': len(QUOTE),
                'sha256': hashlib.sha256(QUOTE.encode()).hexdigest(), 'summary': '', 'topics': [],
                'aliases': ['silver blossom']}]}}


def fixture():
    asset = attached({'id': 'v1', 'asset_id': 'a1', 'name': 'Pinned city', 'number': 1, 'content': canon_content()})
    context = source_context()
    context['sources'] = [source for source in context['sources'] if source['kind'] != 'reference']
    source = {'id': 'asset:v1', 'kind': 'reference', 'title': 'Pinned city',
              'text': encode(narrative_asset(asset)['version']['content'])}
    context['sources'].insert(-1, source)
    context['director_direction'] = 'Inspect the silver blossom.'
    return context, [asset]


def assemble(context, assets, limits=(8192, 4096)):
    packet, canon = compact_canon(context, 'Write carefully.', profiles(*limits), {'mode': 'long'}, assets)
    packet, memory = assemble_sources(packet, 'Write carefully.', profiles(*limits), {'mode': 'long'})
    if canon:
        memory = {**memory, 'canon': canon}
    return packet, {'content': encode(packet), 'source_memory': memory}


def test_specialist_canon_preserves_originals_required_metadata_placements_and_smallest_budget():
    context, assets = fixture()
    original = deepcopy((context, assets))
    packet, snapshot = assemble(context, assets)
    assert (context, assets) == original
    memory = snapshot['source_memory']
    assert token_estimate('Write carefully.', packet) + memory['overhead_margin'] <= 4096 - 512
    assert packet['sources'][0] == context['sources'][0] and packet['sources'][-1] == context['sources'][-1]
    metadata = next(source for source in packet['sources'] if source['id'] == 'asset:v1')
    assert decode(metadata['text']) == {'required_rule': 'Never narrate a decision for the player.'}
    excerpts = [source for source in packet['sources'] if source['kind'] == 'Canon excerpt']
    assert len(excerpts) == 1 and excerpts[0]['text'] == QUOTE
    assert 'silver blossom' not in excerpts[0]['text'] and excerpts[0]['source_field'] == 'text'
    assert excerpts[0]['sha256'] == hashlib.sha256(QUOTE.encode()).hexdigest()
    assert memory['canon']['coverage']['selected_excerpts'] == 1
    assert replay_sources(context, snapshot, canon_assets=assets) == packet


@pytest.mark.parametrize('mode,scope,limit', [('full', 'rules', 4096), ('long', 'blind', 4096), ('long', 'rules', 65536)])
def test_complete_history_blind_and_fitting_context_are_unchanged(mode, scope, limit):
    context, assets = fixture()
    context['scope'] = scope
    packet, receipt = compact_canon(context, 'Write.', profiles(limit), {'mode': mode}, assets)
    assert packet is context and receipt is None


@pytest.mark.parametrize('protection', ['full-policy', 'cited', 'character'])
def test_required_overviews_and_character_definitions_cannot_be_trimmed(protection):
    context, assets = fixture()
    if protection == 'full-policy':
        assets[0]['version']['content']['canon_recall']['mode'] = 'full'
    elif protection == 'cited':
        context['findings'] = [{'source_id': 'asset:v1', 'quote': QUOTE}]
    else:
        assets[0]['kind'] = 'character'
    with pytest.raises(DomainError, match='exact working material'):
        assemble(context, assets)


def test_disabled_canon_and_stale_aliases_cannot_enter_the_index():
    context, assets = fixture()
    disabled = deepcopy(assets[0])
    disabled.update(enabled=False, version_id='future')
    disabled['version'].update(id='future', name='Hidden')
    disabled['version']['content']['text'] = 'FORBIDDEN silver blossom'
    assets[0]['version']['content']['canon_recall']['cues'][0]['sha256'] = '0' * 64
    packet, snapshot = assemble(context, [*assets, disabled])
    assert 'FORBIDDEN' not in encode(packet)
    assert snapshot['source_memory']['canon']['collections'][0]['stale_cues'] == 1
    assert all(source['text'] != QUOTE for source in packet['sources'] if source['kind'] == 'Canon excerpt')


@pytest.mark.parametrize('tamper', ['hash', 'range', 'coverage', 'order', 'policy', 'source', 'missing-binding', 'remove-receipt'])
def test_replay_rejects_unbound_or_altered_canon_even_with_matching_content_hash(tamper):
    context, assets = fixture()
    packet, snapshot = assemble(context, assets)
    canon = snapshot['source_memory']['canon']
    selection = canon['collections'][0]
    if tamper == 'hash':
        selection['spans'][0]['sha256'] = '0' * 64
    elif tamper == 'range':
        selection['spans'][0]['end'] -= 1
    elif tamper == 'coverage':
        canon['coverage']['selected_excerpts'] += 1
    elif tamper == 'order':
        selection['spans'].append(deepcopy(selection['spans'][0]))
    elif tamper == 'policy':
        assets[0]['version']['content']['canon_recall']['mode'] = 'full'
    elif tamper == 'source':
        assets[0]['version']['content']['text'] += 'Changed edition.'
    elif tamper == 'missing-binding':
        assets = None
    else:
        del snapshot['source_memory']['canon']
    assert snapshot['source_memory']['content_sha256'] == hashlib.sha256(encode(packet).encode()).hexdigest()
    with pytest.raises(DomainError):
        replay_sources(context, snapshot, canon_assets=assets)


def test_carried_canon_citation_stays_whole_without_duplicate_ids():
    context, assets = fixture()
    packet, _ = assemble(context, assets)
    cited = next(source for source in packet['sources'] if source['kind'] == 'Canon excerpt')
    context['sources'].insert(-1, {**cited, 'kind': 'review evidence'})
    context['findings'] = [{'source_id': cited['id'], 'quote': cited['text']}]
    packet, snapshot = assemble(context, assets)
    assert next(source for source in packet['sources'] if source['id'] == cited['id'])['text'] == QUOTE
    ids = [source['id'] for source in packet['sources']]
    assert len(ids) == len(set(ids))
    assert replay_sources(context, snapshot, canon_assets=assets) == packet


def canon_story(client, character=False):
    response = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Pinned city', 'content': canon_content()})
    assert response.status_code == 201, response.text
    book = response.json()
    selected = book
    if character:
        selected = client.post('/api/library', json={'kind': 'character', 'name': 'Mara',
            'content': {'text': 'Mara protects her friends.', 'lorebook_versions': [book['id']]}}).json()
    story = client.post('/api/stories', json={'title': 'Canon specialist fixture',
        'settings': {'memory': {'mode': 'long'}, 'disabled_prompts': []},
        'attachments': [{'asset_id': selected['asset_id'], 'version_id': selected['id']}]}).json()
    node = append(client, story['branch_id'], 'Mara examines the silver blossom and the brass observatory key.', 0)
    return story, book, node


def test_historical_comparison_uses_pinned_canon_and_survives_repeated_archive_import(client):
    first = small_profile(client, limit=8192)
    second = small_profile(client, 'Second', 4096)
    story, book, node = canon_story(client, character=True)
    changed = client.post(f"/api/library/{book['asset_id']}/versions", json={
        'expected_version_id': book['id'], 'name': 'Future city', 'content': {'text': 'FUTURE CANON silver blossom'}})
    assert changed.status_code == 201, changed.text
    append(client, story['branch_id'], 'FUTURE EVENT silver blossom', 1)
    client.app.state.review_runner.provider = ReviewProvider()
    run, _ = start(client, story, {'expected_revision': 2, 'from_node_id': node, 'through_node_id': node,
        'steps': [{'key': 'review-continuity', 'profile_ids': [first['profile_id'], second['profile_id']]},
                  {'key': 'review-pacing'}]})
    jobs = finished_review(client, run['id'])['jobs']
    reviewed = [job for job in jobs if job['step'] == 'review-continuity']
    assert all(job['status'] == 'done' for job in jobs)
    assert reviewed[0]['snapshot']['content'] == reviewed[1]['snapshot']['content']
    for job in reviewed:
        assert any(source['kind'] == 'Canon excerpt' and source['text'] == QUOTE
                   for source in decode(job['snapshot']['content'])['sources'])
        assert 'FUTURE' not in job['snapshot']['content']
        assert job['snapshot']['source_memory']['canon']['coverage']['selected_excerpts'] > 0
        assert 'source_context' in job['snapshot']
        assert all('text' not in source and len(source['source_text_sha256']) == 64
                   for source in job['snapshot']['source_context']['sources'])
    assert 'source_memory' not in next(job for job in jobs if job['step'] == 'review-pacing')['snapshot']
    set_memory(client, story, 'full')
    archive, _ = backup(client, story)
    restored, mapping = restore(client, archive)
    copied = client.get(f"/api/reviews/{mapping[run['id']]}").json()['jobs']
    assert [job['snapshot']['content'] for job in copied] == [job['snapshot']['content'] for job in jobs]
    second_archive, _ = backup(client, {'story_id': restored['story_ids'][0], 'branch_id': mapping[story['branch_id']]})
    restore(client, second_archive)


def test_scene_continues_after_archive_with_frozen_source_ids_and_pinned_canon(client):
    small_profile(client, limit=8192)
    story, _book, _node = canon_story(client)
    scene = create_long_scene(client, story, 1)
    job = run_stage(client, scene, 'scene-beats')[0]
    assert job['status'] == 'done', job['error']
    assert job['snapshot']['source_memory']['canon']['coverage']['selected_excerpts'] > 0
    choose(client, scene, job)
    archive, _ = backup(client, story)
    _, mapping = restore(client, archive)
    copied = get_plan(client, mapping[scene])
    assert copied['jobs'][0]['snapshot']['content'] == job['snapshot']['content']
    next_job = run_stage(client, mapping[scene], 'scene-brief')[0]
    assert next_job['status'] == 'done', next_job['error']
    assert next_job['snapshot']['source_memory']['canon']['coverage']['selected_excerpts'] > 0
    assert len(client.get(f"/api/branches/{story['branch_id']}").json()['messages']) == 1


class CanonEvidenceReviewer:
    async def generate(self, _profile, _prompt, content):
        from server.providers.events import ProviderEvent
        source = next(source for source in decode(content)['sources'] if source['kind'] == 'Canon excerpt')
        findings = [{'severity': severity, 'source_id': source['id'], 'quote': source['text'],
                     'explanation': 'Fixture Canon evidence handoff.', 'suggestion': 'Preserve the stated world rule.'}
                    for severity in ('soft', 'hold', 'hard')]
        yield ProviderEvent(text=encode({'summary': 'Exact Canon fixture.', 'findings': findings}), done=True)


def test_scene_canon_citation_survives_review_revision_patch_continuity_and_repeated_restore(client):
    from tests.test_scene_continuity import ContinuityProvider
    from tests.test_scene_patches import PatchProvider, selected_stage
    from tests.test_scene_reviews import scene_body
    from tests.test_scene_revisions import RevisionProvider, rejected_claim
    from tests.test_scenes import decide

    small_profile(client, limit=8192)
    story, _book, _node = canon_story(client)
    original = client.get(f"/api/branches/{story['branch_id']}").json()
    scene = create_long_scene(client, story, 1)
    for key in ('scene-beats', 'scene-brief'):
        choose(client, scene, run_stage(client, scene, key)[0])
    decide(client, scene, 'approve')
    for key in ('scene-draft', 'scene-coverage'):
        selected_stage(client, scene, key)
    client.app.state.review_runner.provider = CanonEvidenceReviewer()
    run, _ = start(client, story, scene_body(client, scene, [{'key': 'review-continuity'}]))
    review = finished_review(client, run['id'])['jobs'][0]
    assert review['status'] == 'done', review['error']
    cited = review['result']['findings'][0]['source_id']
    client.app.state.scene_runner.provider = RevisionProvider()
    triage = run_stage(client, scene, 'scene-triage', review_job_ids=[review['id']])[0]
    assert triage['status'] == 'done', triage['error']
    choose(client, scene, triage)
    rejected_claim(client, scene)
    decide(client, scene, 'approve-revision', {'package': 'C', 'confirmed_hold_ids': ['t2']})
    client.app.state.scene_runner.provider = PatchProvider()
    patch = selected_stage(client, scene, 'scene-patch')
    selected_stage(client, scene, 'scene-patch-check')
    client.app.state.scene_runner.provider = ContinuityProvider()
    continuity = selected_stage(client, scene, 'scene-continuity')
    for job in (triage, patch):
        evidence = [source for source in decode(job['snapshot']['content'])['sources'] if source['id'] == cited]
        assert len(evidence) == 1 and evidence[0]['text'] == QUOTE
    assert continuity['status'] == 'done'
    assert client.get(f"/api/branches/{story['branch_id']}").json() == original
    archive, _ = backup(client, story)
    restored, mapping = restore(client, archive)
    assert [job['snapshot']['content'] for job in get_plan(client, scene)['jobs']] == [
        job['snapshot']['content'] for job in get_plan(client, mapping[scene])['jobs']]
    again, _ = backup(client, {'story_id': restored['story_ids'][0], 'branch_id': mapping[story['branch_id']]})
    restore(client, again)


def test_conditional_entries_stay_scoped_and_active_required_entries_stay_exact():
    context, assets = fixture()
    assets[0]['version']['content']['lore_definition'] = {'entries': [
        {'id': 'off', 'title': 'Hidden', 'text': 'FORBIDDEN silver blossom secret', 'enabled': False, 'activation': 'always'}]}
    active = {'id': 'lore:required', 'kind': 'world reference', 'title': 'Active rule',
              'text': 'The player alone decides whether to open the vault.', 'placement': 'tail'}
    context['sources'].append(active)
    packet, snapshot = assemble(context, assets)
    assert packet['sources'][-1] == active
    assert 'FORBIDDEN' not in encode(packet)
    assert replay_sources(context, snapshot, canon_assets=assets) == packet


def test_historical_review_after_adoption_uses_the_passages_old_manifest(client):
    from tests.test_library import adoption_request

    small_profile(client, limit=4096)
    story, book, node = canon_story(client)
    version = client.post(f"/api/library/{book['asset_id']}/versions", json={
        'expected_version_id': book['id'], 'name': 'Revised city', 'content': {'text': 'FUTURE CANON silver blossom'}}).json()
    route = f"/api/versions/{version['id']}/adoption"
    adopted = client.post(route, json=adoption_request(client.get(route).json()))
    assert adopted.status_code == 200, adopted.text
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    assert branch['attachments'][0]['version_id'] == version['id']
    client.app.state.review_runner.provider = ReviewProvider()
    run, _ = start(client, story, {'expected_revision': branch['revision'], 'from_node_id': node, 'through_node_id': node,
        'steps': [{'key': 'review-continuity'}]})
    job = finished_review(client, run['id'])['jobs'][0]
    assert job['status'] == 'done' and 'FUTURE CANON' not in job['snapshot']['content']
    assert job['snapshot']['source_memory']['canon']['coverage']['selected_excerpts'] > 0
    archive, _ = backup(client, story)
    restore(client, archive)


def test_archive_cannot_replace_historical_canon_origin_or_forge_selected_text(client):
    from server.archives.validate import parse_archive

    small_profile(client)
    story, _book, _node = canon_story(client)
    client.app.state.review_runner.provider = ReviewProvider()
    run, _ = start(client, story, {'expected_revision': 1, 'steps': [{'key': 'review-continuity'}]})
    finished_review(client, run['id'])
    _, document = backup(client, story)
    for defect in ('origin', 'content', 'binding', 'message-binding', 'empty-receipt', 'full-mode'):
        changed = deepcopy(document)
        row = changed['data']['review_jobs'][0]
        snapshot = decode(row['snapshot'])
        if defect == 'origin':
            snapshot['source_context']['sources'][0]['text'] = 'Foreign invented draft.'
        elif defect == 'binding':
            snapshot['source_links'][0]['frozen_version_id'] = 'foreign'
        elif defect == 'message-binding':
            next(link for link in snapshot['source_links'] if 'node_id' in link)['node_id'] = 'foreign'
        elif defect == 'full-mode':
            review_row = changed['data']['review_runs'][0]
            review_snapshot = decode(review_row['snapshot'])
            review_snapshot['review_settings']['memory']['mode'] = 'full'
            review_row['snapshot'] = encode(review_snapshot)
        elif defect == 'empty-receipt':
            snapshot['source_memory']['canon'] = {}
        else:
            content = decode(snapshot['content'])
            next(source for source in content['sources'] if source['kind'] == 'Canon excerpt')['text'] = 'Invented Canon.'
            snapshot['content'] = encode(content)
            snapshot['source_memory']['content_sha256'] = hashlib.sha256(snapshot['content'].encode()).hexdigest()
        row['snapshot'] = encode(snapshot)
        with pytest.raises(DomainError):
            parse_archive(encode(changed))
    assert len(client.get('/api/stories').json()) == 1


def test_legacy_explicit_null_memory_receipt_keeps_complete_scene_inputs():
    from server.archives.source_memory import validate_scene_projection
    context = {'stage': 'scene-brief', 'sources': [{'id': 'old', 'kind': 'accepted', 'title': 'narrator contribution', 'text': 'Original prose.'}]}
    validate_scene_projection(None, {'branch': {'manifest_id': 'unused'}}, context,
                              {'content': encode(context), 'source_memory': None})



def test_canon_allowance_is_independent_from_earlier_history_allowance():
    context, assets = fixture()
    context['director_direction'] = 'Canal barges carry grain.'
    for recall_limit, canon_limit in ((16, 1), (1, 3)):
        _, receipt = compact_canon(context, 'Write.', profiles(16384),
                                  {'mode': 'long', 'recall_limit': recall_limit, 'canon_limit': canon_limit}, assets)
        assert receipt['coverage']['selected_excerpts'] == canon_limit
