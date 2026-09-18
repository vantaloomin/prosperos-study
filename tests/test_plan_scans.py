"""Optional interpretation plumbing; scripted outputs do not establish model quality."""
from copy import deepcopy
from uuid import uuid4

from server.database import decode, encode
from server.providers.events import ProviderEvent
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_plan_edits import save, view
from tests.test_planned_events import AGREEMENT, WITHDRAWAL, change, plan
from tests.test_profiles import make_profile
from tests.test_reviews import finished_review


class ScanProvider:
    def __init__(self):
        self.calls = []
        self.invalid = False

    async def generate(self, profile, prompt, content):
        context = decode(content)
        self.calls.append((profile, prompt, content))
        text = context['passages'][0]['text']
        existing = context['existing_entries']
        value = plan()
        if existing:
            value['participants'][0]['commitment'] = 'withdrawn'
        proposal = change(value, target=existing[0]['id'] if existing else None, quote=text)
        if self.invalid:
            proposal['evidence'][0]['quote'] = 'Fabricated words absent from the source.'
        yield ProviderEvent(text=encode({'summary': 'Scripted plan proposal, not model quality evidence.',
            'scene_summary': text, 'summary_quote': text, 'changes': [proposal]}), done=True)


def scan(client, branch, **overrides):
    route = f'/api/branches/{branch}/plan-reviews'
    body = {'expected_revision': view(client, branch)['revision'], **overrides}
    preview = client.post(route + '/preview', json=body)
    assert preview.status_code == 200, preview.text
    request = {**body, 'preview_hash': preview.json()['preview_hash'], 'operation_id': uuid4().hex}
    response = client.post(route, json=request)
    assert response.status_code == 201, response.text
    assert client.post(route, json=request).json() == response.json()
    return finished_review(client, response.json()['id']), preview.json()


def accept_suggestion(client, branch, proposal):
    state = view(client, branch)
    response = client.post(f'/api/branches/{branch}/plans', json={
        'operation_id': uuid4().hex, 'expected_revision': state['revision'],
        'expected_version_id': state['version_id'], 'change': proposal})
    assert response.status_code == 200, response.text
    return response.json()


def setup(client, story):
    make_profile(client, 'Continuity writer', primary=True)
    provider = ScanProvider()
    client.app.state.review_runner.provider = provider
    append(client, story['branch_id'], AGREEMENT, 0)
    return provider


def test_scan_only_suggests_and_next_batch_uses_changed_prose(client, story):
    provider = setup(client, story)
    branch = story['branch_id']
    run, preview = scan(client, branch)
    assert len(provider.calls) == 1 and preview['request_count'] == 1
    proposal = run['jobs'][0]['result']['changes'][0]
    assert proposal['evidence'][0]['source_id'].startswith('passage:1:')
    assert view(client, branch)['entries'] == []
    assert view(client, branch)['revision'] == 1
    accept_suggestion(client, branch, proposal)
    append(client, branch, WITHDRAWAL, 2)
    next_run, preview = scan(client, branch)
    assert [item['text'] for item in preview['passages']] == [WITHDRAWAL]
    assert decode(next_run['jobs'][0]['snapshot']['content'])['existing_entries'][0]['plan'] == plan()
    assert view(client, branch)['entries'][0]['plan'] == plan()
    accept_suggestion(client, branch, next_run['jobs'][0]['result']['changes'][0])
    current = view(client, branch)['entries'][0]['plan']
    assert current['status'] == 'agreed'
    assert [person['commitment'] for person in current['participants']] == ['withdrawn', 'agreed']
    assert len(client.get(f'/api/branches/{branch}').json()['messages']) == 2
    assert client.get(f'/api/branches/{branch}/reviews').json() == []
    assert len(client.get(f'/api/branches/{branch}/plan-reviews').json()) == 2
    assert client.post(f'/api/branches/{branch}/plan-reviews/preview',
                       json={'expected_revision': 4}).status_code == 409


def test_scan_archive_preserves_requests_proposals_and_cursor(client, story):
    setup(client, story)
    branch = story['branch_id']
    run, _ = scan(client, branch)
    file, document = backup(client, story)
    _, mapping = restore(client, file)
    restored = client.get('/api/reviews/' + mapping[run['id']]).json()
    assert restored['jobs'][0]['snapshot']['content'] == run['jobs'][0]['snapshot']['content']
    assert restored['jobs'][0]['result'] == run['jobs'][0]['result']
    assert client.post(f"/api/branches/{mapping[branch]}/plan-reviews/preview", json={'expected_revision': 1}).status_code == 409
    accept_suggestion(client, mapping[branch], restored['jobs'][0]['result']['changes'][0])
    second_file, _ = backup(client, {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch]})
    restore(client, second_file)
    damaged = deepcopy(document)
    row = damaged['data']['review_jobs'][0]
    snapshot = decode(row['snapshot'])
    context = decode(snapshot['content'])
    context['passages'][0]['text'] = 'Fabricated source.'
    snapshot['content'] = encode(context)
    row['snapshot'] = encode(snapshot)
    response = client.post('/api/archives/imports', json={'content': encode(damaged)})
    assert response.status_code == 400 and 'frozen passages' in response.text


def test_invalid_proposal_is_preserved_and_retry_keeps_original_input(client, story):
    provider = setup(client, story)
    provider.invalid = True
    branch = story['branch_id']
    run, _ = scan(client, branch)
    job = run['jobs'][0]
    assert job['status'] == 'error' and job['output']
    assert job['result'] is None and not view(client, branch)['entries']
    append(client, branch, 'Unrelated later prose.', 1)
    provider.invalid = False
    response = client.post('/api/review-jobs/' + job['id'] + '/retry', json={})
    assert response.status_code == 200, response.text
    retried = finished_review(client, run['id'])['jobs'][0]
    assert retried['status'] == 'done'
    assert provider.calls[0][1:] == provider.calls[1][1:]
    assert len(client.get('/api/review-jobs/' + job['id'] + '/attempts').json()) == 2


def test_scan_is_bounded_and_comparison_is_explicit(client, story):
    provider = setup(client, story)
    branch = story['branch_id']
    for index in range(5):
        append(client, branch, f'Unrelated accepted passage {index}.', index + 1)
    second = make_profile(client, 'Alternative interpretation')
    primary = next(item['profile_id'] for item in client.get('/api/profiles').json()['profiles'] if item['profile_id'] != second['profile_id'])
    run, preview = scan(client, branch, limit=2, profile_ids=[primary, second['profile_id']])
    assert len(run['jobs']) == len(provider.calls) == 2
    assert len(preview['passages']) == 2 and preview['remaining_passages'] == 4
    assert provider.calls[0][1:] == provider.calls[1][1:]
    assert all(job['status'] == 'done' for job in run['jobs'])
    assert view(client, branch)['revision'] == 6


def test_disabled_continuity_and_stale_preview_never_dispatch(client, story):
    provider = setup(client, story)
    branch = story['branch_id']
    route = f'/api/branches/{branch}/plan-reviews'
    body = {'expected_revision': 1}
    preview = client.post(route + '/preview', json=body).json()
    append(client, branch, 'A new contribution.', 1)
    response = client.post(route, json={**body, 'operation_id': uuid4().hex, 'preview_hash': preview['preview_hash']})
    assert response.status_code == 409 and not provider.calls
    with client.app.state.database.connect(write=True) as connection:
        from server.agent_switches import set_agent
        set_agent(connection, 'scene-continuity', False, 0)
    response = client.post(route + '/preview', json={'expected_revision': 2})
    assert response.status_code == 409 and 'disabled' in response.text
    save(client, branch, source_index=0)
    assert len(view(client, branch)['entries']) == 1 and not provider.calls


def test_revisiting_old_batch_does_not_rewind_progress_or_lose_later_work(client, story):
    setup(client, story)
    branch = story['branch_id']
    for index in range(3):
        append(client, branch, f'Unique accepted passage {index}.', index + 1)
    scan(client, branch, limit=2)
    scan(client, branch, limit=1, from_beginning=True)
    response = client.post(f'/api/branches/{branch}/plan-reviews/preview',
                           json={'expected_revision': 4, 'limit': 1})
    assert response.status_code == 200, response.text
    assert response.json()['passages'][0]['text'] == 'Unique accepted passage 1.'


def test_story_disabled_role_prevents_retry_without_disabling_author_records(client, story):
    provider = setup(client, story)
    provider.invalid = True
    run, _ = scan(client, story['branch_id'])
    with client.app.state.database.connect(write=True) as connection:
        connection.execute('UPDATE stories SET settings=? WHERE id=?',
                           (encode({'disabled_prompts': ['scene-continuity']}), story['story_id']))
    response = client.post('/api/review-jobs/' + run['jobs'][0]['id'] + '/retry', json={})
    assert response.status_code == 409 and len(provider.calls) == 1


def test_reviewing_latest_excerpt_keeps_skipped_passages_pending(client, story):
    setup(client, story)
    branch = story['branch_id']
    scan(client, branch)
    append(client, branch, 'An intervening accepted passage.', 1)
    append(client, branch, 'The latest accepted passage.', 2)
    run, preview = scan(client, branch, latest_only=True)
    assert preview['passages'][0]['text'] == 'The latest accepted passage.'
    assert preview['remaining_passages'] == 1
    next_preview = client.post(f'/api/branches/{branch}/plan-reviews/preview', json={'expected_revision': 3}).json()
    assert [item['text'] for item in next_preview['passages']] == ['An intervening accepted passage.']
    file, _ = backup(client, story)
    restore(client, file)
