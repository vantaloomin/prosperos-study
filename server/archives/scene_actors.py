"""Validate each character's actual request separately from assembly context."""
import hashlib

from server.archives.knowledge import validate_snapshot
from server.database import decode, encode, many, one
from server.errors import require
from server.scenes.actor_context import actor_frame
from server.scenes.actor_runner import combined_result
from server.scenes.output import parse_scene


def validate_actors(connection, row, snapshot, origin):
    actors = snapshot.get('dialogue_actors')
    if actors is None:
        return
    require(row['step'] == 'scene-dialogue' and 1 <= len(actors) <= 8, 'Invalid character dialogue requests.')
    draft = one(connection, 'SELECT result FROM scene_jobs WHERE id=?', (snapshot['upstream']['selections']['scene-draft'],))
    skeleton = decode(snapshot['content'])['skeleton']
    require(skeleton == decode(draft['result']), 'Character dialogue changed its selected draft skeleton.')
    slots = [block['id'] for block in skeleton['blocks'] if block['kind'] == 'dialogue']
    assigned = [key for actor in actors for key in actor['slot_ids']]
    require(len(assigned) == len(set(assigned)) and set(assigned) == set(slots), 'Character assignments omit or repeat dialogue slots.')
    for actor in actors:
        validate_actor(connection, actor, origin, slots)
    validate_records(row['output'], actors)
    if row['status'] == 'done':
        require(decode(row['result']) == combined_result(decode(row['output'])['actors'], snapshot),
                'Assembled dialogue differs from its preserved character responses.')
    for attempt in many(connection, 'SELECT * FROM scene_attempts WHERE job_id=?', (row['id'],)):
        validate_records(attempt['output'], actors)
        if attempt['status'] == 'done':
            require(decode(attempt['result']) == combined_result(decode(attempt['output'])['actors'], snapshot),
                    'A preserved dialogue attempt differs from its character responses.')


def validate_actor(connection, actor, origin, slots):
    require(actor['branch'] == origin['branch'] and actor['memory_controls_version_id'] == origin.get('memory_controls_version_id'),
            'A character writer changed its scene boundary or knowledge version.')
    require(actor['slot_ids'] == [key for key in slots if key in actor['slot_ids']], 'Assigned dialogue slots are out of order.')
    validate_snapshot(connection, {**actor, 'content': actor['knowledge_content']})
    expected = encode({**decode(actor['knowledge_content']), **actor_frame(actor['knowledge_lens']['subject'], actor['slot_ids'])})
    require(actor['content'] == expected and actor['content_sha256'] == hashlib.sha256(expected.encode('utf-8')).hexdigest(),
            'A character writer received changed or additional scene material.')


def validate_records(output, actors):
    if not output:
        return
    envelope = decode(output)
    require(envelope['version'] == 1 and len(envelope['actors']) <= len(actors), 'Unsupported character-response journal.')
    for index, record in enumerate(envelope['actors']):
        require(record['index'] == index and record['subject'] == actors[index]['knowledge_lens']['subject'],
                'Character responses changed identity or order.')
        require(record['status'] in {'running', 'done', 'cancelled', 'error'}, 'Unsupported character response status.')
        if record['status'] == 'done':
            parse_scene(record['output'], {'step': 'scene-dialogue', 'content': actors[index]['content']})
        else:
            require(index == len(envelope['actors']) - 1, 'An incomplete character response precedes later work.')
