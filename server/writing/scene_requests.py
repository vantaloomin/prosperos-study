"""Writing preferences apply to prose stages, never factual scene bookkeeping."""
from server.errors import require
from server.writing.context import request_guidance, writer_profiles

SCENE_WRITING_TASKS = {'scene-draft': 'writer', 'scene-dialogue': 'writer',
                       'scene-patch': 'revision', 'scene-dialogue-patch': 'revision'}
SCENE_WRITING_RULE = (
    'Apply writing_guidance only to the prose or dialogue this stage is authorized to propose. '
    'Keep the required JSON structure, approved revision scope, evidence, character agency and slot identities. '
    'Samples are examples of style, not Story events or additional character knowledge. '
    'Do not restyle factual findings, citations, continuity records or other fields outside the proposed wording.'
)


def writing_task(key):
    return {'version': 1, 'task': SCENE_WRITING_TASKS[key], 'rule': SCENE_WRITING_RULE}


def stage_writing(connection, story, body):
    task = SCENE_WRITING_TASKS.get(body.key)
    if task is None:
        require(body.writing is None, 'Writing styles and prose recipes apply only to drafting, dialogue or patch wording.', 409)
        return body, None
    guidance = request_guidance(connection, story, body, purpose='draft' if task == 'writer' else 'revise', task=task)
    if guidance and guidance['resolved_recipe']:
        require(body.key not in guidance['resolved_recipe']['disabled_tasks'], 'This scene stage is disabled by the recipe.', 409)
    return body.model_copy(update={'profile_ids': writer_profiles(body.profile_ids, guidance, task)}), guidance
