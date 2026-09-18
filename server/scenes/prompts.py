"""Match new requests on historical scenes to their recorded output contracts."""
from server.database import decode, one
from server.prompts import builtin_prompt, original_prompt
from server.workflow.readers import prompt_for_review


def stage_prompt(connection, story, run, key):
    historical = run['snapshot'].get('workflow_version', 1) == 1
    if not historical or key not in {'scene-triage', 'scene-verify', 'scene-patch', 'scene-dialogue-patch'}:
        return prompt_for_review(connection, key, story)
    prompt = original_prompt(connection, key, story)
    pinned = key in decode(story['settings']).get('prompt_versions', {})
    if pinned or not builtin_prompt(prompt):
        return prompt
    # v1 triage returns verification requests; its patch writers have distinct
    # prose/dialogue contracts. Combined defaults would request invalid output.
    return one(connection, 'SELECT * FROM prompt_versions WHERE id=?', (f'{key}-default-v1',))
