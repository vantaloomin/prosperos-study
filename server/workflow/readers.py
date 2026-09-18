"""Selected lenses keep their scope and intentional per-task configuration."""
from server.agent_switches import agent_enabled
from server.database import decode
from server.errors import require
from server.prompts import builtin_prompt, original_prompt
from server.roles import role_key
from server.scenes.drafts import CoverageOutput, validate_coverage
from server.workflow.catalog import LENSES, ROLE_MAP
from server.workflow.models import ReviewStep


def lens_task(key):
    return 'scene-coverage' if key == 'coverage' else f'review-{key}'


def lens_keys(connection, story, step, scene=False, disabled=()):
    definitions = ROLE_MAP[step.key].get('lenses')
    if definitions is None:
        require(step.lenses is None, 'Lenses are selected under Independent reader or Informed reader.')
        return None
    allowed = [item['key'] for item in definitions if scene or item['key'] != 'coverage']
    selected = step.lenses if step.lenses is not None else allowed
    require(len(selected) == len(set(selected)) and set(selected) <= set(allowed), 'Choose distinct lenses available to this reader.')
    return [key for key in selected if lens_task(key) not in disabled and agent_enabled(connection, lens_task(key), story)]


def task_override(connection, story, step, lens):
    key = lens_task(lens)
    settings = decode(story['settings'])
    prompt = original_prompt(connection, key, story)
    custom = key not in settings.get('combined_prompt_tasks', []) and (key in settings.get('prompt_versions', {}) or not builtin_prompt(prompt))
    profile = settings.get('step_profiles', {}).get(key)
    return custom or (not step.profile_ids and bool(profile))


def reader_selections(connection, story, steps, *, scene=False, disabled=()):
    result = []
    for step in steps:
        if step.key in disabled or not agent_enabled(connection, step.key, story):
            continue
        keys = lens_keys(connection, story, step, scene, disabled)
        if keys is None:
            result.append(step)
            continue
        separate = [key for key in keys if task_override(connection, story, step, key)]
        combined = [key for key in keys if key not in separate]
        if combined:
            result.append(ReviewStep(key=step.key, profile_ids=step.profile_ids, lenses=combined))
        result.extend(ReviewStep(key=lens_task(key), profile_ids=step.profile_ids) for key in separate)
    require(len({step.key for step in result}) == len(result), 'A retained task is selected both directly and through a combined reader.')
    return result


def reader_context(step, context, beats=None):
    if step.key == 'scene-coverage':
        draft = '\n\n'.join(source['text'] for source in context['sources'] if source['kind'] == 'draft')
        return {**context, 'reader_contract': 'coverage-v1', 'proposed_beats': beats, 'draft': {'text': draft}}
    if step.key not in {'review-blind', 'review-informed'}:
        return context
    result = {**context, 'reader_contract': 2, 'lenses': [LENSES[key] for key in step.lenses]}
    if 'coverage' in step.lenses:
        require(beats, 'Beat coverage needs an approved beat plan.')
        result['approved_beats'] = beats
    return result


def validate_reader(result, context):
    if context.get('reader_contract') == 'coverage-v1':
        return
    if context.get('reader_contract') != 2:
        require(len(result.findings) <= 10 and result.coverage is None, 'A legacy review exceeds its recorded contract.', 502)
        return
    lenses = {item['key'] for item in context['lenses']}
    blind = context['scope'] == 'blind'
    require(len(result.findings) <= (20 if blind else 15), 'The reader exceeded its finding limit.', 502)
    for lens in lenses:
        require(sum(item.lens == lens for item in result.findings) <= (3 if blind else 5), 'The reader exceeded a lens finding limit.', 502)
    require(all(item.lens in lenses for item in result.findings), 'The reader returned a finding for an unselected lens.', 502)
    validate_reader_coverage(result, context)


def validate_reader_contract(context, key):
    if key not in {'review-blind', 'review-informed'}:
        return
    role = ROLE_MAP[key]
    require(context.get('reader_contract') == 2 and context.get('scope') == role['scope'], 'A reader changed its recorded contract or scope.')
    lenses = context.get('lenses', [])
    keys = [item.get('key') for item in lenses]
    allowed = {item['key'] for item in role['lenses']}
    require(keys and len(keys) == len(set(keys)) and set(keys) <= allowed, 'A reader has invalid or repeated lenses.')
    require(lenses == [LENSES[key] for key in keys], 'A reader changed a lens definition.')
    require(('approved_beats' in context) == ('coverage' in keys), 'Reader beat coverage disagrees with its selected lenses.')
    if role['scope'] == 'blind':
        require(not {'private_background', 'author_memory', 'approved_beats', 'continuity', 'prepared_beat'} & context.keys(),
                'An independent reader received privileged context.')


def validate_reader_coverage(result, context):
    beats = context.get('approved_beats')
    if beats is None:
        require(result.coverage is None, 'This reader was not supplied an approved beat plan.', 502)
        return
    require(result.coverage is not None, 'The informed reader must assess every approved beat.', 502)
    draft = '\n\n'.join(source['text'] for source in context['sources'] if source['kind'] == 'draft')
    validate_coverage({'beats': [beat.model_dump() for beat in result.coverage], 'issues': []},
                      {'proposed_beats': beats, 'draft': {'text': draft}})


def prompt_for_review(connection, step, story):
    # A retained specialist keeps its original contract; combined readers use the new defaults.
    from server.prompts import prompt_snapshot
    legacy = (step.startswith('review-') and role_key(step) != step) or step == 'scene-coverage'
    return original_prompt(connection, step, story) if legacy else prompt_snapshot(connection, step, story)


def coverage_report(output, context):
    result = CoverageOutput.model_validate(output).model_dump()
    validate_coverage(result, context)
    source_id = next(source['id'] for source in context['sources'] if source['kind'] == 'draft')
    return {'summary': result['summary'], 'coverage': result['beats'], 'findings': [
        {'lens': 'coverage', 'severity': 'hard' if issue['category'] == 'agency' else 'soft',
         'source_id': source_id, 'quote': issue['quote'], 'explanation': issue['explanation'],
         'suggestion': 'Review this coverage issue before accepting the scene.'} for issue in result['issues']]}
