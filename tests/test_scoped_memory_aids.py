from copy import deepcopy
from uuid import uuid4

import pytest

from server.archives.validate import parse_archive
from server.database import decode, encode
from server.errors import DomainError
from server.memory.chunks import compile_chunks
from server.memory.scoped_aids import annotated_documents, validate_document_aid
from server.memory.side_packet import prepare_archive
from server.memory.side_search import SourceArchive
from server.memory.source_packet import assemble_sources
from server.memory.source_replay import replay_sources
from tests.test_archives import backup, restore
from tests.test_memory import profiles, small_profile
from tests.test_memory_maintenance import append
from tests.test_reviews import ReviewProvider, finished_review, start
from tests.test_scenes import SceneProvider, get_plan, run_stage
from tests.test_sidebar import CollaboratorProvider, ask, settle, thread
from tests.test_source_memory import source_context
from tests.test_story_summaries import TEXT, fork, publication, setup, started, update_memory


def aid_for(source):
    chunk = compile_chunks(source['id'], source['title'], source['text'])[0]
    return chunk.id, {'source_id': chunk.id, 'version_id': 'reviewed-version',
        'source_sha256': chunk.digest, 'summary': 'A reviewed interpretation, not a new fact.',
        'quotes': [chunk.text[:80]], 'topics': [], 'aliases': ['lunar doorway']}


def test_scoped_aids_retrieve_original_prose_without_inserting_derived_claims():
    context = source_context()
    source = context['sources'][1]
    key, aid = aid_for(source)
    context['director_direction'] = 'lunar doorway'
    before = deepcopy(context)
    packet, receipt = assemble_sources(context, 'Write carefully.', profiles(4096, 8192),
                                       {'mode': 'long', 'summary_recall': True}, {key: aid})
    selected = [item for item in receipt['selection'] if item.get('reviewed_aid')]
    assert len(selected) == 1 and selected[0]['reviewed_aid'] == aid
    assert context == before and aid['summary'] not in encode(packet)
    assert any(item['text'] == source['text'] for item in packet['sources'])
    snapshot = {'content': encode(packet), 'source_memory': receipt}
    assert replay_sources(context, snapshot, {key: aid}) == packet
    with pytest.raises(DomainError, match='frozen memory decisions'):
        replay_sources(context, snapshot, {})
    receipt['selection'][receipt['selection'].index(selected[0])]['reviewed_aid']['quotes'] = ['Invented evidence']
    with pytest.raises(DomainError, match='quotations'):
        replay_sources(context, snapshot)


@pytest.mark.parametrize('mode,scope,enabled', [('full', 'rules', True), ('long', 'blind', True), ('long', 'rules', False)])
def test_full_blind_and_disabled_requests_do_not_use_reviewed_aids(mode, scope, enabled):
    context = {**source_context(), 'scope': scope, 'director_direction': 'lunar doorway'}
    key, aid = aid_for(context['sources'][1])
    _, receipt = assemble_sources(context, 'Review.', profiles(4096),
                                  {'mode': mode, 'summary_recall': enabled}, {key: aid})
    assert not receipt or not any(item.get('reviewed_aid') for item in receipt['selection'])


def test_sidebar_alignment_keeps_every_character_and_filters_private_aids_before_indexing():
    text = '\n\n# First\n' + ('A quiet exact passage. 雨🔑 ' * 420) + '\n\n# Last\n\n'
    source = {'id': 'message:n1', 'title': 'Narration', 'text': text}
    key, aid = aid_for(source)
    parts = annotated_documents(source['id'], source['title'], text, {key: aid})
    assert ''.join(part['text'] for part in parts) == text
    documents = [{'id': f'branch:message:n1:{index + 1}', 'title': 'Narration', **part} for index, part in enumerate(parts)]
    for document in documents:
        validate_document_aid(document)
    snapshot = {'question': 'lunar doorway', 'disclosure': 'spoiler-conscious', 'conversation': [],
                'prompt': {'template': 'Collaborate.'}, 'sources': documents, 'max_reads': 3}
    archive = prepare_archive(snapshot, [], profiles(4096))
    found = SourceArchive(archive).search('lunar doorway')
    assert found['total'] == 1 and found['results'][0]['recall_aid']['version_id'] == aid['version_id']
    assert aid['summary'] not in archive['retrieval']['initial_content']
    for document in archive['sources']:
        document['private'] = True
    scoped = SourceArchive(archive)
    assert scoped.search('lunar doorway')['total'] == 0 and not scoped.corpus.df


def prepared_story(client, publish_first=True):
    story, _ = setup(client)
    run = started(client, story['branch_id'])
    version = None
    if publish_first:
        version = client.post('/api/summaries/' + run['id'] + '/versions', json=publication(client, run, story['branch_id'])).json()['id']
    update_memory(client, story['story_id'], True)
    for _ in range(32):
        append(client, story['branch_id'], 'The market stalls were quiet. Vendors folded cloth beside the fountain. ' * 12)
    target = append(client, story['branch_id'], 'Remember the lunar doorway.')
    small = small_profile(client)
    return story, run, version, target, small


def create_scene(client, story):
    branch = client.get('/api/branches/' + story['branch_id']).json()
    response = client.post('/api/branches/' + story['branch_id'] + '/scenes', json={
        'expected_revision': branch['revision'], 'operation_id': uuid4().hex, 'title': 'Remembering',
        'direction': 'Recall the lunar doorway.', 'propose_options': False})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_scene_freezes_reviewed_decisions_across_exclusion_and_repeated_restore(client):
    story, run, version, _, small = prepared_story(client)
    scene_id = create_scene(client, story)
    frozen = get_plan(client, scene_id)['snapshot']['summary_aids']
    assert next(iter(frozen.values()))['version_id'] == version
    client.post('/api/summaries/' + run['id'] + '/versions', json=publication(
        client, run, story['branch_id'], expected_version_id=version, enabled=False))
    assert get_plan(client, create_scene(client, story))['snapshot']['summary_aids'] == {}
    client.app.state.scene_runner.provider = SceneProvider()
    jobs = run_stage(client, scene_id, 'scene-beats', [small['profile_id']])
    assert jobs[0]['status'] == 'done'
    saved = jobs[0]['snapshot']
    assert any(item.get('reviewed_aid', {}).get('version_id') == version for item in saved['source_memory']['selection'])
    assert 'Elin makes an untested claim.' not in saved['content']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    copied = get_plan(client, mapping[scene_id])
    assert copied['snapshot']['summary_aids'] == frozen and copied['jobs'][0]['snapshot']['content'] == saved['content']
    again = run_stage(client, mapping[scene_id], 'scene-beats', [mapping[small['profile_id']]])[0]
    assert again['snapshot']['content'] == saved['content']
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]})
    restore(client, second)


def test_historical_review_uses_only_aids_published_at_its_selected_boundary(client):
    story, run, _, target, small = prepared_story(client, publish_first=False)
    append(client, story['branch_id'], 'A later accepted event.')
    version = client.post('/api/summaries/' + run['id'] + '/versions', json=publication(client, run, story['branch_id'])).json()['id']
    current = client.get('/api/branches/' + story['branch_id']).json()
    body = {'expected_revision': current['revision'], 'from_node_id': target, 'through_node_id': target,
            'steps': [{'key': 'review-continuity', 'profile_ids': [small['profile_id']]}]}
    client.app.state.review_runner.provider = ReviewProvider()
    response, _ = start(client, story, body)
    old = finished_review(client, response['id'])['jobs'][0]['snapshot']
    assert not any(item.get('reviewed_aid') for item in old['source_memory']['selection'])
    final = append(client, story['branch_id'], 'Revisit the lunar doorway.')
    body.update(expected_revision=current['revision'] + 1, from_node_id=final, through_node_id=final)
    body['steps'].append({'key': 'review-pacing', 'profile_ids': [small['profile_id']]})
    response, _ = start(client, story, body)
    jobs = finished_review(client, response['id'])['jobs']
    aided = next(job for job in jobs if job['step'] == 'review-continuity')['snapshot']
    assert any(item.get('reviewed_aid', {}).get('version_id') == version for item in aided['source_memory']['selection'])
    assert 'source_memory' not in next(job for job in jobs if job['step'] == 'review-pacing')['snapshot']


def test_sidebar_freezes_aids_comparison_and_exact_receipts_without_story_mutation(client):
    story, run, version, _, small = prepared_story(client)
    other = small_profile(client, 'Other profile', 8192)
    client.app.state.side_runner.provider = CollaboratorProvider()
    before = client.get('/api/branches/' + story['branch_id']).json()
    thread_id = thread(client, story)
    request = ask(client, thread_id, story, revision=before['revision'], question='lunar doorway',
                  profile_ids=[small['profile_id'], other['profile_id']])
    settle(client)
    route = '/api/side-turns/' + request['id'] + '/source-search'
    found = client.get(route, params={'query': 'lunar doorway'}).json()
    exact = next(item for item in found['results'] if item['text'] == TEXT)
    assert exact['recall_aid']['version_id'] == version
    replies = client.get('/api/side-conversations/' + thread_id).json()['turns'][0]['replies']
    inputs = [client.get('/api/side-replies/' + reply['id'] + '/requests/0').json()['content'] for reply in replies]
    assert inputs[0] == inputs[1] and 'Elin makes an untested claim.' not in inputs[0]
    client.post('/api/summaries/' + run['id'] + '/versions', json=publication(
        client, run, story['branch_id'], expected_version_id=version, enabled=False))
    assert client.get(route, params={'query': 'lunar doorway'}).json() == found
    assert client.get('/api/branches/' + story['branch_id']).json() == before
    file, _ = backup(client, story, include_sidebar=True)
    _, mapping = restore(client, file)
    copied = client.get('/api/side-turns/' + mapping[request['id']] + '/source-search', params={'query': 'lunar doorway'}).json()
    assert copied == found
    second, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}, include_sidebar=True)
    restore(client, second)


def test_replacement_branch_cannot_inherit_an_aid_for_the_removed_source(client):
    story, _, _, _, _ = prepared_story(client)
    original = client.get('/api/branches/' + story['branch_id']).json()['messages'][0]
    edited = fork(client, story['branch_id'], original['id'], 'A different opening.')
    copied_story = {**story, 'branch_id': edited}
    assert get_plan(client, create_scene(client, copied_story))['snapshot']['summary_aids'] == {}


@pytest.mark.parametrize('kind', ['scene-source', 'scene-quote', 'sidebar-hash', 'sidebar-reference'])
def test_archives_reject_altered_scoped_aid_sources_and_receipts(client, kind):
    story, _, _, _, _ = prepared_story(client)
    create_scene(client, story)
    client.app.state.side_runner.provider = CollaboratorProvider()
    revision = client.get('/api/branches/' + story['branch_id']).json()['revision']
    ask(client, thread(client, story), story, revision=revision, question='lunar doorway')
    settle(client)
    _, document = backup(client, story, include_sidebar=True)
    if kind.startswith('scene'):
        row = document['data']['scene_runs'][0]
        snapshot = decode(row['snapshot'])
        aid = next(iter(snapshot['summary_aids'].values()))
        if kind == 'scene-source':
            snapshot['summary_aids'] = {'foreign:source': aid}
        else:
            aid['quotes'] = ['Not present in the original.']
        row['snapshot'] = encode(snapshot)
    else:
        row = document['data']['side_turns'][0]
        snapshot = decode(row['snapshot'])
        source = next(item for item in snapshot['sources'] if item.get('reviewed_aid'))
        if kind == 'sidebar-hash':
            source['reviewed_aid']['source_sha256'] = '0' * 64
        else:
            source['memory_source']['id'] = 'foreign-source'
        row['snapshot'] = encode(snapshot)
    with pytest.raises(DomainError):
        parse_archive(encode(document))
