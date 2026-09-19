"""Live ordinary-writing trajectory on a coherent public-domain manuscript prefix.

Only disposable stories are modified. Raw drafts are mechanically accepted to
observe drift, not to certify them. Book future and review labels are withheld.
"""
import argparse
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from scripts.memory_literature_fixture import literature_fixture
from scripts.narrative_reliability import fingerprint, load
from scripts.relationship_evaluation import append_source
from scripts.relationship_live_evaluation import ObservedProvider, lmstudio_config
from server.archives.validate import parse_archive
from server.database import decode, encode
from server.main import create_app
from server.memory.chunks import compile_chunks
from tests.test_archives import backup
from tests.test_generations import finished
from tests.test_writer_recall import start

STYLE = ('Write 120-180 words of third-person prose with dialogue, continuing this alternate path from its '
         'current moment. Use only the supplied story path, not later events from the published play. ')
MAIN = [
    'At dinner Nora quietly asks Christine how her attempt to contact Krogstad went. Christine answers from her experience. Let the others remain occupied nearby.',
    'Torvald asks why Nora seems uneasy about the mail. Nora answers without disclosing her private business. Let his response reflect what he currently understands.',
    'Nora and Christine find a brief private moment to decide whether they can take any further practical step before tomorrow. Keep uncertain possibilities distinct from completed arrangements.',
    'Nora now chooses to tell Torvald, on the page, about the loan and her forged signature. He acknowledges hearing her admission. Stay in the house and let this be a new disclosure.',
    'Torvald responds to what Nora has just told him. Distinguish her admission from what still requires checking with Krogstad, and choose one practical next step.',
    'Christine joins them and asks what has changed. Torvald answers, drawing on what he has actually learned on this path. They settle what they will do next without jumping ahead.',
]
FORK = [
    'Torvald asks Christine whether her errand succeeded. She answers without disclosing Nora\'s private business. Let Nora listen and decide what to do next.',
    'Nora and Torvald speak about the delayed mail and tomorrow\'s plans. Keep their different understandings clear, and advance the evening through one new practical choice.',
]


def freeze(destination):
    stories, _ = literature_fixture()
    original = stories['doll']['text']
    cut = original.index('\nACT III')
    seed = original[:cut]
    chunks = compile_chunks('doll-prefix', '', seed)
    manifest = {'format': 'prospero-manuscript-trajectory/1', 'source': 'Locally preserved A Doll\'s House, before Act III',
                'seed': seed, 'seed_words': len(seed.split()), 'seed_characters': len(seed),
                'passages': [chunk.text for chunk in chunks], 'main_directions': [STYLE + text for text in MAIN],
                'fork_directions': [STYLE + text for text in FORK], 'fork_after_step': 3,
                'review': ['Krogstad\'s first letter is in the letter-box; Torvald suspects a letter but has postponed reading it.',
                           'Christine reported Krogstad out of town until tomorrow evening and wrote a note; do not invent a completed meeting or an answer.',
                           'Nora\'s loan and forged signature are private from Torvald at the cutoff. Step 4 deliberately changes his knowledge on the main path.',
                           'The fork precedes the requested confession; later main-path prose must not enter its evidence.',
                           'Prior generated mistakes can become accepted context under this mechanical acceptance policy. Report drift, do not repair or silently reset.'],
                'method': 'One trajectory and an earlier fork; no claim of novel-scale reliability or independent human assessment. Familiar public-domain work may be known from training.'}
    assert ''.join(manifest['passages']) == seed and 15000 < manifest['seed_words'] < 20000
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'manifest.json').write_text(encode(manifest), encoding='utf-8')
    (destination / 'manifest.sha256').write_text(fingerprint(destination / 'manifest.json'), encoding='ascii')
    print(f"Frozen {manifest['seed_words']} words in {len(chunks)} exact passages; no inference.", flush=True)


def storage(database):
    with database.connect() as connection:
        logical = connection.execute('PRAGMA page_count').fetchone()[0] * connection.execute('PRAGMA page_size').fetchone()[0]
        snapshots = connection.execute('SELECT snapshot FROM generations').fetchall()
    return {'logical_database_bytes': logical, 'snapshot_bytes': sum(len(row['snapshot'].encode('utf-8')) for row in snapshots),
            'database_file_bytes': database.path.stat().st_size,
            'wal_bytes': Path(str(database.path) + '-wal').stat().st_size if Path(str(database.path) + '-wal').exists() else 0}


def continuation(client, provider, story, direction, path, step):
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    before = len(provider.calls)
    started = time.perf_counter()
    run = start(client, story, branch['revision'], direction=direction)
    candidate = finished(client, run['id'])['candidates'][0]
    assert candidate['status'] == 'done', candidate
    receipt = candidate['usage'].get('writer_recall')
    assert receipt and receipt['version'] == 5
    final = receipt['final_input']
    assert final['estimated_input_tokens'] + final['memory']['overhead_margin'] <= final['memory']['input_allowance']
    with client.app.state.database.connect() as connection:
        snapshot = decode(connection.execute('SELECT snapshot FROM generations WHERE id=?', (run['id'],)).fetchone()['snapshot'])
    scope = {source['source_id'].removeprefix('message:') for source in snapshot['writer_recall']['sources']}
    assert scope <= {node['id'] for node in branch['messages']}
    response = client.post(f"/api/candidates/{candidate['id']}/accept", json={'operation_id': uuid4().hex})
    assert response.status_code == 200, response.text
    return {'path': path, 'step': step, 'direction': direction, 'generation_id': run['id'], 'candidate_id': candidate['id'],
            'accepted': response.json(), 'output': candidate['output'], 'source_node_ids': sorted(scope),
            'recall': receipt, 'calls': len(provider.calls) - before, 'request_indices': list(range(before, len(provider.calls))),
            'pipeline_seconds': time.perf_counter() - started, 'usage': candidate['usage'],
            'storage': storage(client.app.state.database), 'review': None}


def execute(args):
    assert fingerprint(args.fixture / 'manifest.json') == (args.fixture / 'manifest.sha256').read_text(encoding='ascii')
    manifest = load(args.fixture / 'manifest.json')
    config = lmstudio_config(args.lmstudio_url, args.lmstudio_model)
    config.update(context_tokens=8192, max_output_tokens=512, temperature=0.4)
    args.output.mkdir(parents=True, exist_ok=False)
    provider = ObservedProvider(None, args.output, 16, config)
    report = {'format': 'prospero-manuscript-trajectory-results/1', 'fixture_sha256': fingerprint(args.fixture / 'manifest.json'),
              'config': config, 'steps': [], 'status': 'running', 'manual_prose_corrections': 0,
              'acceptance_policy': 'Mechanically accept each raw draft in a disposable story. Zero corrections is a test policy, not measured absence of need.'}

    def save():
        (args.output / 'report.json').write_text(encode(report), encoding='utf-8')

    started = time.perf_counter()
    try:
        with TestClient(create_app(args.output / 'trajectory.sqlite3'), headers={'x-roleplay-client': 'workspace'}) as client:
            client.app.state.runner.provider = provider
            profile = client.post('/api/profiles', json={'name': 'Trajectory writer', 'make_primary': True, 'config': config})
            assert profile.status_code == 201, profile.text
            response = client.post('/api/stories', json={'title': 'An alternate evening', 'settings': {
                'experience': 'directed', 'player_agency': 'shared',
                'memory': {'mode': 'long', 'writer_recall': True, 'semantic_recall': False, 'relationship_recall': False}}})
            assert response.status_code == 201, response.text
            story = response.json()
            for revision, text in enumerate(manifest['passages']):
                append_source(client, story['branch_id'], text, revision, True)
            report['initial_storage'] = storage(client.app.state.database)
            for index, direction in enumerate(manifest['main_directions'], 1):
                report['steps'].append(continuation(client, provider, story, direction, 'main', index))
                save()
                print(f'main step {index}: saved and mechanically accepted', flush=True)
            checkpoint = report['steps'][manifest['fork_after_step'] - 1]
            branch = client.get(f"/api/branches/{story['branch_id']}").json()
            response = client.post(f"/api/branches/{story['branch_id']}/forks", json={
                'operation_id': uuid4().hex, 'expected_revision': branch['revision'],
                'node_id': checkpoint['accepted']['node_id'], 'replacement': checkpoint['output'], 'name': 'Before disclosure'})
            assert response.status_code == 201, response.text
            fork = {**story, 'branch_id': response.json()['branch_id']}
            forbidden = {step['accepted']['node_id'] for step in report['steps'][manifest['fork_after_step']:]}
            for index, direction in enumerate(manifest['fork_directions'], 1):
                row = continuation(client, provider, fork, direction, 'fork', index)
                assert not forbidden.intersection(row['source_node_ids']), 'Main-path future leaked into fork evidence.'
                row['forbidden_future_node_ids'] = sorted(forbidden)
                report['steps'].append(row)
                save()
                print(f'fork step {index}: saved; main-path future excluded', flush=True)
            file, archive = backup(client, story)
            parse_archive(encode(archive))
            report.update(archive_bytes=len(encode(archive).encode('utf-8')), archive_sha256=file['sha256'],
                          final_storage=storage(client.app.state.database), status='completed_unreviewed')
    except Exception as error:
        report.update(status='error', error=str(error))
        raise
    finally:
        report.update(calls=len(provider.calls), wall_seconds=time.perf_counter() - started)
        save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--execute-live', action='store_true')
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--lmstudio-model')
    parser.add_argument('--lmstudio-url', default='http://127.0.0.1:1234/v1')
    args = parser.parse_args()
    if args.freeze:
        freeze(args.fixture)
    elif not args.output or not args.lmstudio_model:
        parser.error('Live mode requires --output and --lmstudio-model.')
    else:
        execute(args)
