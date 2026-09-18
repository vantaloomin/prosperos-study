"""Verified literature sources and pre-retrieval evidence annotations."""
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from server.memory.chunks import compile_chunks

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/long_story_literature'
EVALUATOR_FILES = ('scripts/memory_literature_fixture.py', 'scripts/memory_literature_metrics.py',
                   'scripts/memory_literature_evaluation.py', 'scripts/memory_scoring.py',
                   'scripts/memory_quality_metrics.py', 'scripts/memory_quality_variants.py',
                   'scripts/memory_ablation.py')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def source_texts(directory=FIXTURES):
    texts = {}
    for source in load_json(directory / 'sources.json')['files']:
        data = (directory / source['file']).read_bytes()
        if sha256(data) != source['sha256'] or len(data) != source['bytes']:
            raise ValueError(f"Original download changed: {source['file']}")
        texts[source['file']] = data.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    return texts


def story_sources(spec, originals):
    text = originals[spec['file']]
    end = spec.get('end') or text.index(spec['end_marker'], spec['start'])
    text = text[spec['start']:end]
    chunks = compile_chunks(spec['id'], '', text)
    if ''.join(chunk.text for chunk in chunks) != text:
        raise ValueError('Story segmentation lost original text')
    sources = [{'id': f"{spec['id']}:{index:04d}", 'text': chunk.text,
                'start': chunk.start, 'end': chunk.end} for index, chunk in enumerate(chunks)]
    return {'text': text, 'sources': sources, 'title': spec['title'], 'genre': spec['genre']}


def quote_range(text, quote):
    if not quote.strip():
        raise ValueError('Empty evidence quote')
    expression = r'\s+'.join(re.escape(word) for word in quote.split())
    matches = list(re.finditer(expression, text))
    if len(matches) != 1:
        raise ValueError(f'Gold quote must match once, found {len(matches)}: {quote[:110]}')
    return matches[0].span()


def source_ranges(story, quote):
    start, end = quote_range(story['text'], quote)
    return [{'source_id': source['id'], 'start': max(start, source['start']) - source['start'],
             'end': min(end, source['end']) - source['start']}
            for source in story['sources'] if start < source['end'] and source['start'] < end]


def literature_fixture(directory=FIXTURES):
    annotations = load_json(directory / 'annotations.json')
    originals = source_texts(directory)
    stories = {spec['id']: story_sources(spec, originals) for spec in annotations['stories']}
    probes = annotations['probes']
    if len({probe['id'] for probe in probes}) != len(probes):
        raise ValueError('Duplicate probe identity')
    for probe in probes:
        probe['evidence'] = [[source_ranges(stories[probe['story']], quote) for quote in group['any_of']]
                             for group in probe['groups']]
        if any(not group for group in probe['evidence']):
            raise ValueError('Evidence group has no alternatives')
    return stories, probes


def fingerprints():
    paths = [FIXTURES / 'sources.json', FIXTURES / 'annotations.json',
             *(ROOT / name for name in EVALUATOR_FILES), *sorted((ROOT / 'server/memory').glob('*.py'))]
    return {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()) for path in paths}


def freeze_fixture(path=FIXTURES / 'freeze.json'):
    # This is deliberately a separate command; evaluate never creates its own freeze.
    literature_fixture()
    data = {'format': 'prospero-literature-freeze/1', 'created_at': datetime.now(UTC).isoformat(),
            'files': fingerprints(), 'contract': 'No score-driven edits after this freeze. Not human-adjudicated.'}
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return data


def verify_freeze(path=FIXTURES / 'freeze.json'):
    frozen = load_json(path)
    current = fingerprints()
    if current != frozen['files']:
        changed = sorted(name for name in current.keys() | frozen['files'].keys()
                         if current.get(name) != frozen['files'].get(name))
        raise ValueError(f'Frozen evaluation inputs changed: {changed}')
    return {'created_at': frozen['created_at'], 'sha256': sha256(path.read_bytes()),
            'annotation_sha256': frozen['files']['tests/fixtures/long_story_literature/annotations.json']}
