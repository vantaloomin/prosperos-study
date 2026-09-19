"""Explicit synthetic OpenRouter or loaded LM Studio evaluation.

Requires --execute-live and a new output directory. OpenRouter reads only the
selected profile's latest credential reference through read-only SQLite.
LM Studio requires an already-loaded instance. Never changes saved profiles.
"""
import argparse
import sqlite3
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from scripts.relationship_evaluation import CASES, VARIANTS, fixture, run_variant
from server.database import decode, encode
from server.errors import DomainError, require
from server.main import create_app
from server.memory.relationship_output import PROMPT as ANNOTATE
from server.memory.writer_recall import PROMPT as SEARCH
from server.providers.config import ProfileConfig
from server.providers.lmstudio import native_base
from server.providers.service import ProviderService
from server.providers.vault import SystemVault
from tests.test_relationship_recall import prepare, wait_jobs
from tests.test_writer_recall import change_memory

MODEL = 'z-ai/glm-5.3-flash'
LIVE_DIRECTION = ('Write 120-180 words of third-person prose in which the recipient asks about the parcel '
                  'and the sender answers. Make the scene consistent with the recorded promise, transfer '
                  'and outcome. Distinguish what each person knows from what only the narrator knows. '
                  'Keep missing or conflicting history unresolved; do not invent a delivery or an explanation.')


def saved_credential(database, profile_id):
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute('SELECT v.config,v.credential_ref FROM profiles p JOIN profile_versions v '
                                 'ON p.latest_version_id=v.id WHERE p.id=?', (profile_id,)).fetchone()
    require(row is not None and decode(row[0])['provider'] == 'openrouter', 'Select an existing OpenRouter profile.')
    return row[1]


def lmstudio_config(base_url, model):
    config = ProfileConfig(provider='local', base_url=base_url, model=model, local_protocol='lmstudio',
                           local_reasoning='off', context_tokens=4096, max_output_tokens=512,
                           timeout_seconds=60, temperature=0).model_dump()
    response = httpx.get(native_base(config['base_url']) + '/models', timeout=10, trust_env=False)
    response.raise_for_status()
    require_loaded(response.json(), config)
    return config


def require_loaded(data, config):
    for model in data.get('models', []):
        for instance in model.get('loaded_instances', []):
            if instance.get('id') == config['model']:
                require(instance.get('config', {}).get('context_length', 0) >= config['context_tokens'],
                        'The loaded instance has insufficient context for this evaluation.')
                options = model.get('capabilities', {}).get('reasoning', {}).get('allowed_options', [])
                require(config['local_reasoning'] in options, 'This loaded instance does not report the selected reasoning option.')
                return
    require(False, 'The selected LM Studio instance is not loaded. The evaluation will not load it.')


class ObservedProvider:
    def __init__(self, reference, directory, limit, config=None):
        self.reference, self.directory, self.limit = reference, directory, limit
        self.config = config or ProfileConfig(provider='openrouter', model=MODEL, context_tokens=4096,
                                              max_output_tokens=512, timeout_seconds=60, temperature=0).model_dump()
        self.service = ProviderService(SystemVault())
        self.calls, self.halt_reason = [], ''

    def background_capability(self, profile):
        return {'verified': False, 'reason': 'Live evaluation uses explicit foreground requests only.'}

    async def generate(self, profile, prompt, content):
        require(not self.halt_reason, self.halt_reason or 'Evaluation halted.')
        require(len(self.calls) < self.limit, 'The live evaluation request limit was reached.')
        require(all(profile['config'].get(key) == self.config.get(key) for key in
                    ('provider', 'base_url', 'model', 'local_protocol', 'local_reasoning')),
                'The evaluation can call only the selected provider and model.')
        if self.config['provider'] == 'local':
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.get(native_base(self.config['base_url']) + '/models')
                response.raise_for_status()
                require_loaded(response.json(), self.config)
        category = 'annotation' if prompt == ANNOTATE else 'query' if prompt == SEARCH else 'writer'
        record = {'kind': category, 'profile': profile['config'], 'prompt': prompt, 'content': content,
                  'output': '', 'usage': {}, 'actual_model': '', 'status': 'running'}
        self.calls.append(record)
        started = time.perf_counter()
        try:
            async for event in self.service.generate({**profile, 'credential_ref': self.reference}, prompt, content):
                record['output'] += event.text
                record['usage'].update(event.usage)
                record['actual_model'] = event.model or record['actual_model']
                yield event
            record['status'] = 'done'
        except DomainError as error:
            record.update(status='error', error=error.message, code=error.code)
            if error.code in {'authentication', 'access', 'rate_limit'}:
                self.halt_reason = error.message
            raise
        finally:
            record['seconds'] = time.perf_counter() - started
            (self.directory / 'requests.json').write_text(encode(self.calls), encoding='utf-8')
            print(f"{category}: {record['status']} in {record['seconds']:.2f}s", flush=True)


def live_case(directory, case, provider):
    config = provider.config
    with TestClient(create_app(directory / (case + '.sqlite3')), headers={'x-roleplay-client': 'workspace'}) as client:
        story, core, forbidden = fixture(client, case, config, directed=True)
        client.app.state.runner.provider = provider
        client.app.state.relationship_runner.provider = provider
        variants = []
        for variant in VARIANTS[:2]:
            variants.append(run_variant(client, story, variant, provider, core, forbidden, direction=LIVE_DIRECTION))
        change_memory(client, story, relationship_recall=True)
        started = time.perf_counter()
        jobs = wait_jobs(client, prepare(client, story)['job_ids'])
        preparation_seconds = time.perf_counter() - started
        require(not provider.halt_reason, provider.halt_reason or 'Evaluation halted.')
        variants.append(run_variant(client, story, VARIANTS[2], provider, core, forbidden, direction=LIVE_DIRECTION))
        for variant in variants:
            variant['pipeline_seconds'] = variant.pop('controlled_pipeline_seconds')
            variant['narrative_quality_reason'] = 'Live prose saved; narrative rubric still needs independent review.'
        assert all(variant['writer_config'] == config for variant in variants)
        return {'case': case, 'direction': LIVE_DIRECTION, 'variants': variants, 'annotation_jobs': jobs,
                'initial_preparation': {'requests': sum(job['usage'].get('calls', 0) for job in jobs),
                    'seconds': preparation_seconds, 'manual_batch_actions': 1, 'link_curation_actions': 0}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--profile-database', type=Path, default=Path('data/roleplay.sqlite3'))
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--openrouter-profile-id')
    selection.add_argument('--lmstudio-model', help='Exact already-loaded instance ID.')
    parser.add_argument('--lmstudio-url', default='http://127.0.0.1:1234/v1')
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES[:2]))
    args = parser.parse_args()
    if not args.execute_live or args.output_directory.exists():
        parser.error('Use --execute-live and a new output directory. This performs model requests.')
    reference = saved_credential(args.profile_database, args.openrouter_profile_id) if args.openrouter_profile_id else None
    config = lmstudio_config(args.lmstudio_url, args.lmstudio_model) if args.lmstudio_model else None
    args.output_directory.mkdir(parents=True)
    import os
    (args.output_directory / 'process.pid').write_text(str(os.getpid()), encoding='ascii')
    cases = list(dict.fromkeys(args.cases))
    provider = ObservedProvider(reference, args.output_directory, len(cases) * 9, config)
    report = {'mode': 'live', 'model': provider.config['model'], 'config': provider.config,
              'cases': [], 'request_limit': provider.limit,
              'semantic_recall': 'Disabled; no embedding model requested.', 'status': 'running'}
    try:
        for case in cases:
            if (args.output_directory / 'stop-after-case').exists():
                report['status'] = 'stopped_between_cases'
                return
            report['cases'].append(live_case(args.output_directory, case, provider))
            (args.output_directory / 'report.json').write_text(encode(report), encoding='utf-8')
            print(case + ': saved inputs, evidence coverage and ungraded live prose.', flush=True)
        report['status'] = 'completed_ungraded'
    except Exception as error:
        report.update(status='error', error=str(error))
        print('Evaluation stopped; inspect report.json and requests.json.', flush=True)
    finally:
        report['requests'] = len(provider.calls)
        (args.output_directory / 'report.json').write_text(encode(report), encoding='utf-8')


if __name__ == '__main__':
    main()
