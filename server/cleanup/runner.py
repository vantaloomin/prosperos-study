"""One cleanup call per completed writer attempt; never retry cleanup automatically."""
import asyncio
import math
import time
from contextlib import aclosing

from server.cleanup.protocol import PROMPT, apply_output, content_for, flag_draft
from server.cleanup.storage import permitted, still_current
from server.database import decode, encode, identifier, many, now, one
from server.errors import DomainError, require
from server.phrases.detection import digest, tokens
from server.phrases.service import MAX_CHARACTERS, MAX_TOKENS, select_passages
from server.prompt_sections import system_prompt
from server.providers.capabilities import input_capacity
from server.providers.scheduling import BackgroundInterrupted, Work, work_scope


def prepare(database, candidate_id, generation):
    with database.connect() as connection:
        candidate = one(connection, 'SELECT * FROM candidates WHERE id=?', (candidate_id,))
        passages, _, _, limited = select_passages(connection, generation['branch']['head_id'], 'recent')
    original = candidate['output']
    passages, trimmed = fit_history(passages, original)
    snapshot = {'protocol': 2 if generation.get('writing_guidance') else 1,
                'branch': generation['branch'], 'story_revision': generation['story_revision'],
                'memory_controls_version_id': generation.get('memory_controls_version_id'),
                'continuity_version_id': generation.get('continuity_version_id'),
                'attempt': candidate['attempt'], 'original': original, 'original_sha256': digest(original),
                'settings': generation['cleanup'], 'evidence': [], 'instruction': PROMPT,
                'guidance': writer_guidance(generation),
                'scope': 'recent', 'passage_count': len(passages), 'limited': limited or trimmed}
    reason = eligibility(original, generation['cleanup'])
    if not reason:
        snapshot.update(flag_draft(passages, f"draft:{candidate_id}:{candidate['attempt']}", original,
                                   generation['cleanup']['choices'], motif_sources(generation)))
        reason = '' if snapshot['evidence'] else 'No eligible repeated wording was found.'
    snapshot['content'] = encode(content_for(original, snapshot['evidence'], snapshot['guidance']))
    return candidate, snapshot, reason


def fit_history(passages, original):
    characters = len(original) + sum(len(item['text']) for item in passages)
    word_count = len(tokens('', original)) + sum(len(tokens(item['id'], item['text'])) for item in passages)
    trimmed = False
    while passages and (characters > MAX_CHARACTERS or word_count > MAX_TOKENS):
        omitted = passages.pop(0)
        characters -= len(omitted['text'])
        word_count -= len(tokens(omitted['id'], omitted['text']))
        trimmed = True
    return passages, trimmed


def motif_sources(generation):
    entries = decode(generation['content']).get('author_memory', {}).get('entries', [])
    return [source['text'] for entry in entries if entry['kind'] == 'emphasis' and entry['stance'] == 'motif'
            for source in entry['sources'] if source.get('text')]


def writer_guidance(generation):
    content = decode(generation['content'])
    return {'role_instructions': system_prompt(generation), 'direction': content.get('direction', ''),
            'story_preferences': content.get('story', {}),
            'author_notes': [item['text'] for item in content.get('history', []) if item['role'] == 'ooc'],
            **({'writing_guidance': content['writing_guidance']} if content.get('writing_guidance') else {}),
            'author_decisions': content.get('author_memory', {})}


def eligibility(original, settings):
    if settings['choices'] is None:
        return 'Phrase-check choices were unavailable. Cleanup was skipped to protect author choices.'
    if len(original) > MAX_CHARACTERS or len(tokens('', original)) > MAX_TOKENS:
        return 'This draft exceeds the local wording-check limit. The original is available.'
    return ''


def record(database, candidate, snapshot, reason):
    with database.connect(write=True) as connection:
        current = one(connection, 'SELECT * FROM candidates WHERE id=?', (candidate['id'],))
        valid = current['status'] in {'cleaning', 'done'} and still_current(connection, current, snapshot) and permitted(connection, snapshot)
        status = ('skipped' if reason else 'running') if valid else 'stale'
        error = reason if valid else 'The path or cleanup setting changed. The original draft is available.'
        cleanup_id = identifier()
        connection.execute('INSERT INTO candidate_cleanups '
                           '(id,candidate_id,attempt,branch_id,snapshot,status,error,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                           (cleanup_id, candidate['id'], candidate['attempt'], snapshot['branch']['id'],
                            encode(snapshot), status, error, now()))
    return cleanup_id, status


def save(database, cleanup_id, state, final=False):
    with database.connect(write=True) as connection:
        row = one(connection, 'SELECT * FROM candidate_cleanups WHERE id=?', (cleanup_id,))
        snapshot = decode(row['snapshot'])
        candidate = one(connection, 'SELECT * FROM candidates WHERE id=?', (row['candidate_id'],))
        if row['status'] != 'running':
            return
        if final and not (permitted(connection, snapshot) and still_current(connection, candidate, snapshot)):
            state.update(status='stale', selected='original', error='The path, draft or cleanup setting changed. The original draft is available.')
        connection.execute('UPDATE candidate_cleanups SET status=?,output=?,cleaned=?,edits=?,usage=?,error=?,selected=?,updated_at=? WHERE id=?',
                           (state['status'], state['output'], state['cleaned'], encode(state['edits']),
                            encode(state['usage']), state['error'], state['selected'], now(), cleanup_id))


async def run(database, provider, candidate_id, generation):
    started = time.monotonic()
    candidate, snapshot, reason = await asyncio.to_thread(prepare, database, candidate_id, generation)
    reading = generation['cleanup'].get('timing') == 'reading'
    if reading and not reason:
        capability = getattr(provider, 'background_capability', lambda _: {'verified': False})(decode(candidate['profile']))
        if not capability['verified']:
            reason = 'Reading-time cleanup needs verified interruption for this profile. Use cleanup before ready or verify the connection in model settings.'
    cleanup_id, status = record(database, candidate, snapshot, reason)
    if status != 'running':
        return
    state = {'status': 'running', 'output': '', 'cleaned': '', 'edits': [], 'usage': {}, 'error': '', 'selected': 'original'}
    try:
        work = Work(20, 'reading-time cleanup', True, lambda: validate_dispatch(database, candidate_id, snapshot)) if reading else Work(10, 'cleanup before ready')
        with work_scope(work):
            await consume(database, provider, candidate, snapshot, cleanup_id, state)
        cleaned, edits = apply_output(state['output'], snapshot['original'], snapshot['evidence'])
        state.update(status='done', cleaned=cleaned, edits=edits, selected='cleaned' if edits and not reading else 'original')
    except asyncio.CancelledError:
        state.update(status='cancelled', error='Cleanup stopped. The original draft is available.')
    except BackgroundInterrupted as error:
        state.update(status='cancelled', error=error.message)
    except DomainError as error:
        state.update(status='error', error=error.message)
    except Exception:
        state.update(status='error', error='Cleanup could not finish. The original draft is available.')
    finally:
        state['usage']['cleanup_seconds'] = time.monotonic() - started
        save(database, cleanup_id, state, final=True)


def validate_dispatch(database, candidate_id, snapshot):
    with database.connect() as connection:
        candidate = one(connection, 'SELECT * FROM candidates WHERE id=?', (candidate_id,))
        require(still_current(connection, candidate, snapshot) and permitted(connection, snapshot),
                'The draft or cleanup setting changed before dispatch. The original is available.', 409)


async def consume(database, provider, candidate, snapshot, cleanup_id, state):
    profile = decode(candidate['profile'])
    estimated = math.ceil(len((snapshot['instruction'] + snapshot['content']).encode('utf-8')) / 3)
    require(estimated <= input_capacity(profile['config']),
            'Cleanup does not fit this profile’s saved context allowance. The original draft is available.', 409)
    last_save = time.monotonic()
    async with aclosing(provider.generate(profile, snapshot['instruction'], snapshot['content'])) as stream:
        async for event in stream:
            state['output'] += event.text
            state['usage'].update(event.usage)
            require(len(state['output']) <= 16_000, 'Cleanup exceeded its response limit. The original draft is available.', 502)
            if time.monotonic() - last_save > 0.15:
                save(database, cleanup_id, state)
                last_save = time.monotonic()


def recover(connection):
    connection.execute("UPDATE candidates SET usage=json_set(usage,'$.cleanup_pending',json('false')) WHERE json_extract(usage,'$.cleanup_pending')=1")
    rows = many(connection, "SELECT id AS candidate_id FROM candidates WHERE status='cleaning'")
    for row in rows:
        connection.execute("UPDATE candidates SET status='done',error='' WHERE id=?", (row['candidate_id'],))
        connection.execute("UPDATE candidate_activity SET finished_at=?,error_kind='cleanup_interrupted' "
                           "WHERE candidate_id=? AND finished_at IS NULL", (now(), row['candidate_id']))
    connection.execute("UPDATE candidate_cleanups SET status='interrupted',selected='original',error=?,updated_at=? WHERE status='running'",
                       ('Cleanup was interrupted. The original draft is available; no cleanup was resent.', now()))
    return rows
