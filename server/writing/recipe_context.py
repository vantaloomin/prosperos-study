"""Compose each actual stage from the run's frozen sources and completed inputs."""
from server.database import encode
from server.errors import require
from server.memory.budget import token_estimate
from server.memory.source_canon import compact_canon
from server.memory.source_packet import assemble_sources
from server.providers.capabilities import input_capacity
from server.text_edits.models import TextSelection
from server.text_edits.selection import apply_selection
from server.workflow.models import ReviewStep
from server.workflow.readers import reader_context


def working_sources(snapshot, draft):
    source = {'id': 'recipe:draft', 'kind': 'draft', 'title': 'Selected working text' if draft is None else 'Current unaccepted recipe text',
              'text': snapshot['selection']['text'] if draft is None else draft}
    scene = snapshot['sources']['scene']
    if scene is None:
        return [source]
    target_text = snapshot['target']['text'] if draft is None else apply_selection(
        snapshot['target']['text'], TextSelection.model_validate(snapshot['selection']), snapshot['action'], draft)
    blocks = [{**block, 'text': target_text} if block['id'] == scene['block_id'] else block for block in scene['blocks']]
    return [{**source, 'kind': 'selected working text'}, {'id': 'recipe:scene-draft', 'kind': 'draft',
             'title': 'Complete unaccepted scene with the proposed block wording', 'text': '\n\n'.join(block['text'] for block in blocks)}]


def stage_context(snapshot, template, draft, reviews=(), chance=None):
    review = template['task'] == 'review'
    blind = template['scope'] == 'blind'
    sources = snapshot['sources']
    context = {'task': 'Review the draft sources.' if review else 'Prepare the requested text proposal.',
               'scope': template['scope'], 'recipe_task': {'task': template['task'],
                   'instructions': snapshot['guidance']['resolved_recipe']['instructions'],
                   'step_instructions': template['task_instructions'], 'direction': snapshot['direction']},
               'sources': working_sources(snapshot, draft) + sources['blind' if blind else 'informed']}
    if not blind and sources['author_memory']:
        context['author_memory'] = sources['author_memory']
    if review:
        return reader_context(ReviewStep.model_validate(template['reader']), context, sources['scene']['beats'] if sources['scene'] else None)
    context['text_action'] = snapshot['action']
    context['original_selection'] = snapshot['selection']['text']
    style = snapshot['guidance']['style']
    if style:
        context['prose_guidance'] = {'style': style, 'notice': snapshot['guidance']['guidance']}
    if reviews:
        context['review_suggestions'] = list(reviews)
    if chance and template['task'] == 'writer':
        context['prepared_chance'] = chance['writer']
    return context


def compile_job(snapshot, template, draft, reviews=(), chance=None):
    original = stage_context(snapshot, template, draft, reviews, chance)
    sources = snapshot['sources']
    profile, instructions = template['profile'], template['instructions']
    assets = sources['assets'] if template['scope'] != 'blind' else []
    context, canon = compact_canon(original, instructions, [profile], sources['memory_policy'], assets)
    context, memory = assemble_sources(context, instructions, [profile], sources['memory_policy'], sources['summary_aids'])
    if canon:
        memory = {**(memory or {}), 'canon': canon}
    allowance = input_capacity(profile['config'])
    estimate = token_estimate(instructions, context)
    margin = min(512, max(128, allowance // 50))
    require(estimate + margin <= allowance, f"{profile['name']} cannot fit this recipe step's complete working text and required guidance. "
            'Choose a larger context profile or a narrower target; no required text was dropped.', 409)
    return {**template, 'protocol': 1, 'content': encode(context), 'source_context': original,
            'estimated_input_tokens': estimate, 'input_allowance': allowance, 'overhead_margin': margin,
            'source_memory': memory, 'upstream_draft': draft, 'upstream_reviews': list(reviews)}
