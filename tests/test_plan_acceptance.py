"""Fixed lifecycle scenarios exercise stored branch state and actual writer inputs."""
from uuid import uuid4

from server.database import encode
from server.providers.events import ProviderEvent
from tests.test_history import append
from tests.test_plan_edits import view
from tests.test_plan_scans import accept_suggestion, scan
from tests.test_planned_events import AGREEMENT, fork, plan, writer_context
from tests.test_profiles import make_profile


def record(client, branch, subject, text, value, target=None):
    state = view(client, branch)
    append(client, branch, text, state['revision'])
    sources = client.get(f'/api/branches/{branch}/plan-sources').json()['items']
    evidence = next(source for source in sources if source['text'] == text)
    proposal = {'id': uuid4().hex, 'action': 'replace' if target else 'add', 'target_id': target,
                'kind': 'plan', 'subject': subject, 'text': text,
                'reason': 'Explicit author-confirmed interpretation of the quoted passage.',
                'evidence': [{'source_id': evidence['id'], 'quote': text}], 'plan': value}
    return accept_suggestion(client, branch, proposal)['entry_id']


def test_postponement_changes_current_timing_and_retains_earlier_branch(client, story):
    branch = story['branch_id']
    make_profile(client, 'Writer', primary=True)
    target = record(client, branch, 'Camping trip', AGREEMENT, plan())
    earlier = fork(client, branch, client.get(f'/api/branches/{branch}').json()['head_id'])
    value = plan('postponed')
    value.update(timing='next weekend', time_anchor='Friday afternoon when they postponed it')
    text = 'On Friday afternoon, Mara and Jules agreed to move the camping trip to next weekend.'
    record(client, branch, 'Camping trip', text, value, target)
    current = writer_context(client, branch)['continuity']['entries'][0]
    assert current['plan'] == value and current['status'] == 'active'
    assert current['evidence'][0]['quote'] == text
    assert writer_context(client, earlier)['continuity']['entries'][0]['plan']['timing'] == 'this weekend'
    assert len(view(client, branch)['commits']) == 2


def test_attempted_letter_delivery_and_evidenced_completion_are_distinct(client, story):
    branch = story['branch_id']
    make_profile(client, 'Writer', primary=True)
    value = plan()
    value.update(participants=[{'id': 'mara', 'name': 'Mara', 'commitment': 'agreed'}],
                 timing='before sunset', time_anchor='the morning Mara made the promise')
    target = record(client, branch, 'Letter for Ivo', 'Mara promised to deliver the letter to Ivo before sunset.', value)
    value = {**value, 'status': 'attempted'}
    record(client, branch, 'Letter for Ivo', 'Mara handed the letter to a courier, but the courier lost it before reaching Ivo.', value, target)
    unfinished = fork(client, branch, client.get(f'/api/branches/{branch}').json()['head_id'])
    value = {**value, 'status': 'completed', 'resolution': 'Ivo explicitly received and read the recovered letter.'}
    text = 'Mara recovered the lost letter and put it in Ivo\'s hands. Ivo received it and read it.'
    record(client, branch, 'Letter for Ivo', text, value, target)
    done = writer_context(client, branch)['continuity']['entries'][0]
    pending = writer_context(client, unfinished)['continuity']['entries'][0]
    assert done['plan'] == value and done['status'] == 'resolved' and done['evidence'][0]['quote'] == text
    assert pending['plan']['status'] == 'attempted' and pending['plan']['resolution'] is None
    assert pending['status'] == 'active'


class AmbiguousFixture:
    async def generate(self, _profile, _prompt, content):
        import json
        context = json.loads(content)
        assert len(context['existing_entries']) == 2
        text = context['passages'][0]['text']
        yield ProviderEvent(text=encode({'summary': 'Scripted ambiguous reference: no plan can be uniquely identified.',
            'scene_summary': text, 'summary_quote': text, 'changes': []}), done=True)


def test_ambiguous_suggestions_leave_competing_plans_and_writer_context_intact(client, story):
    branch = story['branch_id']
    make_profile(client, 'Writer', primary=True)
    record(client, branch, 'Camping trip', AGREEMENT, plan())
    record(client, branch, 'Museum visit', 'Mara and Jules also agreed to visit the museum this weekend.', plan())
    before = view(client, branch)['entries']
    append(client, branch, 'Someone in the room said, "I cannot go this weekend."', view(client, branch)['revision'])
    client.app.state.review_runner.provider = AmbiguousFixture()
    run, _ = scan(client, branch, latest_only=True)
    assert run['jobs'][0]['status'] == 'done' and run['jobs'][0]['result']['changes'] == []
    assert view(client, branch)['entries'] == before
    assert {entry['subject'] for entry in writer_context(client, branch)['continuity']['entries']} == {'Camping trip', 'Museum visit'}
