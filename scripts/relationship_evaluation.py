"""Equal-budget ordinary-writer evidence evaluation with controlled model responses.

This isolates retrieval and lifecycle behavior. The fixture supplies correct
annotations and queries; it cannot measure a live model's interpretation or prose.
All databases and exact request receipts are disposable synthetic artifacts.
"""
import argparse
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from server.database import decode, encode
from server.main import create_app
from server.memory.relationship_output import PROMPT as ANNOTATE
from server.memory.writer_recall import PROMPT as SEARCH
from server.providers.events import ProviderEvent
from tests.test_generations import finished
from tests.test_history import append
from tests.test_memory import small_profile
from tests.test_memory_controls import entry, evidence, save
from tests.test_relationship_recall import prepare, wait_jobs
from tests.test_writer_recall import change_memory, start

DIRECTION = ('Continue with the recipient asking the sender what happened to the parcel. '
             'Preserve uncertainty and who actually knows each event.')
CORE = ['Sera promised to return the copper parcel to Ilan.',
        'She handed it to the courier Tess.',
        'Tess dropped the package into a ravine. It never reached the recipient.']
DELIVERED = 'Tess handed the package to Ilan, who signed the receipt. Delivery succeeded.'
VARIANTS = ('baseline', 'prewriting', 'prewriting_and_links')
CASES = ('failed_delivery', 'successful_sibling', 'changed_names_pronouns', 'withdrawn_promise',
         'conflicting_testimony', 'excluded_handoff', 'fork_before_handoff')


class ControlledProvider:
    def __init__(self, core):
        self.core, self.calls = core, []

    def background_capability(self, profile):
        return {'verified': False, 'reason': 'Controlled evaluation; no background inference.'}

    async def generate(self, profile, prompt, content):
        category = 'annotation' if prompt == ANNOTATE else 'query' if prompt == SEARCH else 'writer'
        self.calls.append({'kind': category, 'profile': profile['config'], 'prompt': prompt, 'content': content})
        if category == 'query':
            output = encode({'queries': ['parcel promise courier delivery outcome withdrawal testimony']})
        elif category == 'annotation':
            data = decode(content)
            target = next(row for row in data['sources'] if row['id'] == data['target_id'])
            relevant = [row for row in data['sources'] if row['text'] in self.core]
            items = []
            if target in relevant:
                items = [{'kind': 'testimony' if 'said' in target['text'] else 'relationship',
                          'relation': 'withdrawal' if 'withdrew' in target['text'] else 'related',
                          'actor': 'Sender, courier and recipient',
                          'description': 'Parcel promise, handoff and outcome; distinguish testimony and withdrawal.',
                          'evidence': [{'source_id': row['id'], 'quote': row['text']} for row in relevant[-4:]]}]
            output = encode({'items': items})
        else:
            output = 'Controlled writer output; narrative quality is not evaluated.'
        yield ProviderEvent(text=output, done=True)


def append_source(client, branch_id, text, revision, directed):
    if not directed:
        return append(client, branch_id, text, revision)
    response = client.post(f'/api/branches/{branch_id}/messages', json={
        'operation_id': uuid4().hex, 'expected_revision': revision, 'text': text, 'role': 'narrator'})
    assert response.status_code == 201, response.text
    return response.json()['node_id']


def fixture(client, case, profile_config=None, *, directed=False):
    if profile_config is None:
        small_profile(client, limit=4096)
    else:
        response = client.post('/api/profiles', json={'name': 'Synthetic evaluation writer', 'make_primary': True, 'config': profile_config})
        assert response.status_code == 201, response.text
    settings = {'memory': {'mode': 'long'}}
    if directed:
        settings.update(experience='directed', player_agency='shared')
    story = client.post('/api/stories', json={'title': 'The parcel' if directed else case, 'settings': settings}).json()
    core, forbidden = list(CORE), []
    if case == 'changed_names_pronouns':
        core = ['Maren, once called Sera, promised to return the copper parcel to Ivo.',
                'She put it in his hands; Tess, the courier, nodded.',
                'He lost it over the cliff. Nothing arrived for Ivo.']
    elif case == 'withdrawn_promise':
        core.append('Sera explicitly withdrew her promise; Ilan accepted the withdrawal. No return was now owed.')
    elif case == 'conflicting_testimony':
        core[2] = 'Tess said the package had arrived. Ilan said he had received nothing. Neither account was verified.'
    nodes = [append_source(client, story['branch_id'], text, index, directed) for index, text in enumerate(core)]
    if case in {'successful_sibling', 'fork_before_handoff'}:
        index = 2 if case == 'successful_sibling' else 0
        body = {'operation_id': uuid4().hex, 'expected_revision': len(nodes), 'node_id': nodes[index], 'name': case}
        if case == 'successful_sibling':
            body['replacement'] = DELIVERED
        response = client.post(f"/api/branches/{story['branch_id']}/forks", json=body)
        assert response.status_code == 201, response.text
        story['branch_id'] = response.json()['branch_id']
        forbidden = core[index:] if index == 2 else core[1:]
        core = [*core[:2], DELIVERED] if index == 2 else core[:1]
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    filler = [f'Afternoon {i}. ' + 'Sunlight lay on the market square. ' * 30 for i in range(16)]
    for text in [*filler, 'The sender and recipient sat at the desk with a parcel-shaped empty space between them.']:
        append_source(client, story['branch_id'], text, branch['revision'], directed)
        branch = client.get(f"/api/branches/{story['branch_id']}").json()
    if case == 'excluded_handoff':
        source = next(row for row in evidence(client, story['branch_id']) if row['node_id'] == nodes[1])
        save(client, story['branch_id'], [entry([source], 'emphasis', 'exclude')])
        forbidden = [core[1]]
    return story, core, forbidden


def run_variant(client, story, variant, provider, core, forbidden, *, direction=DIRECTION):
    change_memory(client, story, writer_recall=variant != 'baseline', relationship_recall=variant == 'prewriting_and_links')
    revision = client.get(f"/api/branches/{story['branch_id']}").json()['revision']
    previous = len(provider.calls)
    started = time.perf_counter()
    generation = finished(client, start(client, story, revision, direction=direction)['id'])
    seconds = time.perf_counter() - started
    candidate = generation['candidates'][0]
    assert candidate['status'] == 'done', candidate
    recall = candidate['usage'].get('writer_recall')
    final = recall['final_input'] if recall else generation['snapshot']
    packet = decode(final['content'])
    originals = [row['text'] for key in ('history', 'recalled_passages') for row in packet.get(key, [])]
    required = [text for text in core if text not in forbidden]
    covered = [text for text in required if any(text in original for original in originals)]
    leaks = [text for text in forbidden if any(text in original for original in originals)]
    assert not leaks, (variant, leaks)
    assert final['estimated_input_tokens'] + final['memory']['overhead_margin'] <= final['memory']['input_allowance']
    assert client.get(f"/api/branches/{story['branch_id']}/plans").json()['entries'] == []
    calls = provider.calls[previous:]
    return {'variant': variant, 'required_passages': len(required), 'covered_passages': len(covered),
            'complete_relevant_chain': len(covered) == len(required), 'missing': [text for text in required if text not in covered],
            'forbidden_passages_supplied': leaks, 'input_allowance': final['memory']['input_allowance'],
            'estimated_input_tokens': final['estimated_input_tokens'], 'overhead_margin': final['memory']['overhead_margin'],
            'writer_config': next(call['profile'] for call in calls if call['kind'] == 'writer'),
            'controlled_pipeline_seconds': seconds, 'request_counts': {kind: sum(call['kind'] == kind for call in calls) for kind in ('query', 'writer')},
            'narrative_quality': None, 'narrative_quality_reason': 'Controlled provider; no narrative inference.',
            'final_content': final['content'], 'recall_receipt': recall,
            'writer_output': candidate['output'], 'writer_usage': candidate['usage']}


def evaluate(directory):
    directory.mkdir(parents=True, exist_ok=False)
    report = {'mode': 'controlled', 'scope': __doc__, 'cases': [], 'live_requests': 0,
              'semantic_recall': 'Disabled: no live embedding model is configured for this comparison.'}
    for case in CASES:
        with TestClient(create_app(directory / (case + '.sqlite3')), headers={'x-roleplay-client': 'workspace'}) as client:
            story, core, forbidden = fixture(client, case)
            provider = ControlledProvider(core)
            client.app.state.runner.provider = provider
            client.app.state.relationship_runner.provider = provider
            variants = [run_variant(client, story, variant, provider, core, forbidden) for variant in VARIANTS[:2]]
            change_memory(client, story, relationship_recall=True)
            started = time.perf_counter()
            jobs = wait_jobs(client, prepare(client, story)['job_ids'])
            preparation_seconds = time.perf_counter() - started
            assert all(job['status'] == 'done' for job in jobs), jobs
            variants.append(run_variant(client, story, VARIANTS[2], provider, core, forbidden))
            assert len({variant['input_allowance'] for variant in variants}) == 1
            assert all(variant['writer_config'] == variants[0]['writer_config'] for variant in variants)
            row = {'case': case, 'direction': DIRECTION, 'variants': variants,
                   'initial_preparation': {'requests': sum(job['usage']['calls'] for job in jobs),
                       'controlled_pipeline_seconds': preparation_seconds, 'manual_batch_actions': 1, 'link_curation_actions': 0},
                   'annotation_jobs': jobs}
            report['cases'].append(row)
            (directory / 'report.json').write_text(encode(report), encoding='utf-8')
            print(case + ': ' + ', '.join(f"{item['variant']}={item['covered_passages']}/{item['required_passages']}" for item in variants), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True, help='A new directory for synthetic databases and report.json.')
    arguments = parser.parse_args()
    evaluate(arguments.output_directory)
