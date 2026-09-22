"""Migrate prose-guidance boundaries and validate styled scene requests."""
from server.archives.format import V49_TABLES
from server.database import decode
from server.errors import require
from server.writing.scene_requests import SCENE_WRITING_TASKS, writing_task


def upgrade_scene_writing(document):
    if document['version'] == 48:
        require(set(document['data']) == set(V49_TABLES), 'Version 48 needs its original record groups.')
        for row in document['data']['scene_jobs']:
            snapshot = decode(row['snapshot'])
            require(not {'writing_guidance', 'writing_versions'} & set(snapshot)
                    and not {'writing_guidance', 'writing_task'} & set(decode(snapshot['content'])),
                    'Version 48 does not include styled scene requests.')
        require(all('assessment_context_version' not in decode(row['snapshot']) for row in document['data']['assessment_runs']),
                'Version 48 does not include the revised assessment context scope.')
        for row in document['data']['candidate_cleanups']:
            snapshot = decode(row['snapshot'])
            require(snapshot['protocol'] == 1 and not (snapshot.get('guidance') or {}).get('writing_guidance'),
                    'Version 48 does not include styled cleanup requests.')
        document['version'] = 49
    return document


def validate_scene_writing(snapshot):
    guidance = snapshot.get('writing_guidance')
    content = decode(snapshot['content'])
    if guidance is None:
        require('writing_task' not in content, 'A scene writing task lacks its frozen guidance.')
    else:
        key = snapshot['step']
        require(key in SCENE_WRITING_TASKS and content.get('writing_task') == writing_task(key),
                'Writing guidance changed its scene task or authority boundary.')
        task = SCENE_WRITING_TASKS[key]
        recipe = guidance['resolved_recipe']
        if recipe:
            require(recipe['purpose'] == ('draft' if task == 'writer' else 'revise')
                    and all(step['task'] == task for step in recipe['steps']) and recipe['randomness'] is None
                    and not {key, task} & set(recipe['disabled_tasks']), 'This recipe does not authorize the recorded scene writing stage.')
    for actor in snapshot.get('dialogue_actors', []):
        require(actor.get('writing_guidance') == guidance and actor.get('writing_versions') == snapshot.get('writing_versions'),
                'A character writer changed the stage writing preferences.')
