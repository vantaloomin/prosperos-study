"""Read-only preview of the same bounded request used by the Companion runner."""
import hashlib
from copy import deepcopy

from server.database import encode
from server.memory.side_archive import permitted_sources
from server.providers.capabilities import input_capacity
from server.side_context import assemble_context, estimated_tokens, initial_sources, side_snapshot
from server.side_work import effective_prompt, freeze_first_content, public_work, writing_labels


def prepare_request(connection, thread, body):
    snapshot, profiles = side_snapshot(connection, thread, body)
    starts = [initial_sources(snapshot, profile) for profile in profiles]
    snapshot['initial_source_ids'] = starts[0] if all(starts) else []
    freeze_first_content(snapshot, profiles[0])
    return snapshot, profiles


def request_fingerprint(snapshot, profiles):
    frozen = deepcopy(snapshot)
    if frozen.get('side_work'):
        frozen['side_work'].pop('request_ref')
    return hashlib.sha256(encode({'snapshot': frozen, 'profiles': profiles}).encode()).hexdigest()


def request_preview(snapshot, profiles):
    content = snapshot['retrieval']['initial_content'] if snapshot.get('retrieval') else assemble_context(snapshot, profiles[0], snapshot['initial_source_ids'])
    prompt = effective_prompt(snapshot)
    work = public_work(snapshot)
    if work:
        work.pop('request_ref')
    return {'fingerprint': request_fingerprint(snapshot, profiles), 'work': work, 'writing': writing_labels(snapshot),
            'models': [{'name': profile['name'], 'number': profile['number'], 'provider': profile['config']['provider'],
                        'model': profile['config']['model'], 'input_allowance': input_capacity(profile['config']),
                        'output_limit': profile['config']['max_output_tokens']} for profile in profiles],
            'input_estimate': estimated_tokens(prompt, content), 'max_calls': len(profiles) * (snapshot['max_reads'] + 1),
            'disclosure': snapshot['disclosure'], 'mode': 'long' if snapshot.get('retrieval') else 'full',
            'sources': [{'id': item['id'], 'title': item['title']} for item in permitted_sources(snapshot)],
            'prompt': prompt, 'content': content, 'cost': None}
