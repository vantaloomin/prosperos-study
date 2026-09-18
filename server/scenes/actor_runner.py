"""Keep per-character outputs and resume only unfinished calls on explicit retry."""
import asyncio
import time

from server.database import decode, encode
from server.errors import DomainError, require
from server.prompt_sections import system_prompt
from server.scenes.output import parse_scene, validate_result


def combined_result(records, snapshot):
    actors = snapshot['dialogue_actors']
    require(len(records) == len(actors), 'Some character dialogue requests are incomplete.', 502)
    lines = {}
    for index, (record, actor) in enumerate(zip(records, actors, strict=True)):
        require(record['index'] == index and record['status'] == 'done', 'Character dialogue is incomplete or out of order.', 502)
        result = parse_scene(record['output'], {'step': 'scene-dialogue', 'content': actor['content']})
        for line in result['lines']:
            require(line['slot_id'] not in lines, 'Two character writers returned the same dialogue slot.', 502)
            lines[line['slot_id']] = line
    skeleton = decode(snapshot['content'])['skeleton']
    result = {'summary': 'Dialogue assembled from independently scoped character proposals; no Story events accepted.',
              'lines': [lines[block['id']] for block in skeleton['blocks'] if block['kind'] == 'dialogue']}
    return validate_result('scene-dialogue', result, snapshot['content'])


def previous_records(runner, job_id, snapshot):
    with runner.database.connect() as connection:
        row = connection.execute('SELECT output FROM scene_attempts WHERE job_id=? ORDER BY attempt DESC LIMIT 1', (job_id,)).fetchone()
    if not row:
        return []
    try:
        records = decode(row['output'])['actors']
    except (ValueError, KeyError, TypeError):
        return []
    kept = []
    for index, record in enumerate(records):
        if record.get('status') != 'done' or index >= len(snapshot['dialogue_actors']):
            break
        require(record['index'] == index, 'Preserved character responses are out of order.', 409)
        parse_scene(record['output'], {'step': 'scene-dialogue', 'content': snapshot['dialogue_actors'][index]['content']})
        kept.append({**record, 'reused': True})
    return kept


def record_state(state, records):
    state['output'] = encode({'version': 1, 'actors': records})
    state['usage'] = {'character_requests': [{'subject': item['subject'], 'status': item['status'], 'reused': item.get('reused', False), 'usage': item['usage']} for item in records]}


async def consume_actor(runner, job_id, snapshot, actor, record, records, state):
    saved = 0.0  # Persist the first partial response before waiting for another event.
    try:
        async for event in runner.provider.generate(snapshot['profile'], system_prompt(snapshot), actor['content']):
            record['output'] += event.text
            record['usage'].update(event.usage)
            if event.model:
                record['usage']['actual_model'] = event.model
            record_state(state, records)
            if time.monotonic() - saved > 0.15:
                runner.save(job_id, state)
                saved = time.monotonic()
        parse_scene(record['output'], {'step': 'scene-dialogue', 'content': actor['content']})
        record['status'] = 'done'
    except asyncio.CancelledError:
        record['status'] = 'cancelled'
        raise
    except DomainError as error:
        record.update(status='error', error=error.message)
        raise DomainError(record['subject'] + ': ' + error.message, error.status) from error
    except Exception:
        record.update(status='error', error='This character request could not complete.')
        raise
    finally:
        record_state(state, records)


async def consume_actors(runner, job_id, snapshot, state):
    records = previous_records(runner, job_id, snapshot)
    record_state(state, records)
    for index in range(len(records), len(snapshot['dialogue_actors'])):
        actor = snapshot['dialogue_actors'][index]
        record = {'index': index, 'subject': actor['knowledge_lens']['subject'], 'status': 'running', 'output': '', 'usage': {}, 'error': ''}
        records.append(record)
        await consume_actor(runner, job_id, snapshot, actor, record, records, state)
        runner.save(job_id, state)
