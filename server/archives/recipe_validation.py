from copy import deepcopy

from server.archives.authoring import validate_configuration
from server.archives.identities import SourceIdentities, records
from server.archives.links import snapshot_links
from server.archives.recipe_switches import validate_switches
from server.archives.remap import fields
from server.archives.text_edits import validate_snapshot
from server.archives.v07 import validate_sections
from server.archives.writing_requests import validate_guidance
from server.database import decode, one
from server.errors import DomainError, require
from server.mechanics.models import Beat, RngSettings
from server.memory.settings import MemorySettings
from server.prompt_sections import compose
from server.providers.completion import StreamCompletion
from server.providers.config import SavedProfileConfig
from server.roles import role_key
from server.text_edits.models import TextSelection
from server.text_edits.selection import apply_selection
from server.text_edits.targets import snapshot_version
from server.workflow.catalog import ROLE_MAP
from server.workflow.models import ReviewStep
from server.writing.recipe_bindings import bind_job, initial_bindings
from server.writing.recipe_chance import resolve_chance
from server.writing.recipe_context import compile_job
from server.writing.recipe_output import parse_recipe_output
from server.writing.recipe_templates import REVIEW_RULE, TEXT_RULE


def validate_run(connection, run, data):
    snapshot, bindings = run['snapshot'], run['bindings']
    require(set(snapshot) == {'protocol', 'branch', 'story_revision', 'target', 'selection', 'action', 'direction', 'guidance',
                             'writing_versions', 'switches', 'sources', 'plan', 'chance'} and snapshot['protocol'] == 1,
            'Unsupported recipe execution protocol.')
    catalog = records(data)
    identities = SourceIdentities(connection, catalog)
    require(set(bindings) == set(initial_bindings(snapshot)) and all(live in catalog and identities.matches(live, frozen)
            for frozen, live in bindings.items()), 'A recipe dependency is missing or has changed identity.')
    branch = fields(snapshot['branch'], bindings)
    require(branch['id'] == run['branch_id'] and branch['story_id'] == run['story_id'], 'A recipe run changed its Story or telling.')
    snapshot_links(connection, {'branch': branch}, run['story_id'])
    validate_target(connection, run)
    require(snapshot['action'] in {'replace', 'add', 'update', 'insert-before', 'insert-after'}
            and isinstance(snapshot['direction'], str) and len(snapshot['direction']) <= 30000, 'Invalid recipe text action.')
    apply_selection(snapshot['target']['text'], TextSelection.model_validate(snapshot['selection']), snapshot['action'], '')
    guidance = snapshot['guidance']
    validate_guidance(connection, {'writing_versions': [bindings[value] for value in snapshot['writing_versions']]}, guidance, identities)
    require(guidance['recipe'] is not None, 'A recipe run needs a published recipe.')
    require(guidance['resolved_recipe']['purpose'] == 'draft' or snapshot['selection']['text'].strip(), 'A recipe review or revision needs selected prose.')
    validate_switches(snapshot)
    validate_plan(connection, snapshot, bindings)
    validate_chance(connection, run)
    from server.archives.recipe_sources import validate_sources
    validate_sources(connection, run, identities)


def validate_target(connection, run):
    frozen, live, bindings = run['snapshot']['target'], run['target'], run['bindings']
    require(frozen['version'] == snapshot_version(frozen), 'A recipe changed its original target fingerprint.')
    expected = deepcopy(frozen)
    expected['ref'] = fields(expected['ref'], bindings)
    expected['basis'] = fields(expected['basis'], bindings)
    if frozen['ref'].get('workspace_id') and frozen['ref']['story_id'] != run['story_id']:
        require(live['ref']['workspace_id'].startswith('restored:'), 'Restored recipes cannot edit host workspace defaults.')
        expected['ref']['workspace_id'] = live['ref']['workspace_id']
    if expected['ref']['kind'] == 'prompt':
        edition = one(connection, 'SELECT number FROM prompt_versions WHERE id=?', (expected['basis']['version_id'],))
        expected['basis']['revision'] = edition['number']
    expected['version'] = snapshot_version(expected)
    require(live == expected, 'The live recipe destination differs from its frozen source.')
    validate_snapshot(connection, live, run['story_id'])


def validate_plan(connection, snapshot, bindings):
    content = snapshot['guidance']['resolved_recipe']
    steps = content['steps'] or [{'task': {'draft': 'writer', 'review': 'review', 'revise': 'revision'}[content['purpose']], 'instructions': ''}]
    tasks = [step['task'] for step in steps]
    require((content['purpose'] == 'draft' and tasks[0] == 'writer') or (content['purpose'] == 'review' and tasks == ['review']) or
            (content['purpose'] == 'revise' and 'writer' not in tasks and 'revision' in tasks), 'A recipe changed its purpose or task order.')
    require(len(snapshot['plan']) == len(steps) and 1 <= len(steps) <= 3, 'A recipe changed its configured steps.')
    require(any(stage['templates'] for stage in snapshot['plan']), 'A recipe has no enabled tasks.')
    for stage, step in zip(snapshot['plan'], steps, strict=True):
        review = step['task'] == 'review'
        require(stage['task'] == step['task'] and stage['skipped'] == (not stage['templates']) and
                (review or len(stage['templates']) == 1), 'A recipe changed its task or skip state.')
        require(set(stage) == {'task', 'templates', 'skipped', 'reason'} and stage['reason'] ==
                ('All selected reader tasks or lenses are disabled.' if stage['skipped'] else ''), 'A recipe changed its skip explanation.')
        require(len({item['step'] for item in stage['templates']}) == len(stage['templates']), 'A recipe repeats a reader request.')
        for template in stage['templates']:
            validate_template(connection, template, bindings, step, review)
    MemorySettings.model_validate(snapshot['sources']['memory_policy'])


def validate_template(connection, template, bindings, step, review):
    require(set(template) == {'step', 'task', 'profile', 'profile_source', 'prompt', 'prompt_sections', 'instructions', 'scope',
                             'reader', 'task_instructions', 'routing_settings'} and template['profile_source'] in {'request', 'recipe', 'inherited'},
            'A recipe has unsupported request settings.')
    live = bind_job(template, bindings)
    require(template['task'] == step['task'] and template['task_instructions'] == step['instructions'], 'A recipe changed its task instructions.')
    require(not template['profile'].get('credential_ref'), 'Recipe archives cannot include credential references.')
    SavedProfileConfig.model_validate(template['profile']['config'], context={'archived': True})
    validate_configuration(connection, live)
    key = template['step']
    if review:
        reader = ReviewStep.model_validate(template['reader'])
        require(reader.key == key and template['scope'] == ROLE_MAP[key]['scope'] and role_key(key) in {'review-blind', 'review-informed'},
                'A recipe reader changed its scope.')
    else:
        require(key == ('writer' if step['task'] == 'writer' else 'collaborator') and template['scope'] == 'informed'
                and template['reader'] is None, 'A recipe changed its prose role.')
    require(template['prompt']['key'] in {key, role_key(key)}, 'A recipe prompt belongs to another task.')
    section_request = live if review else {**live, 'prompt': {**live['prompt'], 'key': 'writer'}}
    validate_sections(connection, section_request)
    require(template['instructions'] == compose(template['prompt'], template['prompt_sections']) + '\n\n' + (REVIEW_RULE if review else TEXT_RULE),
            'A recipe changed its fixed text or review authority.')


def validate_chance(connection, run):
    spec, bindings = run['snapshot']['chance'], run['bindings']
    settings = RngSettings.model_validate(spec['settings'])
    require(spec['applicable'] == (run['snapshot']['guidance']['resolved_recipe']['purpose'] == 'draft')
            and spec['automatic_assessment_applicable'] is False, 'A recipe changed its chance authority.')
    require(spec['beat'] is None or (spec['applicable'] and settings.enabled), 'A review or disabled run acquired chance events.')
    if spec['beat']:
        Beat.model_validate(spec['beat'])
    require(settings.table_versions == {key: value['id'] for key, value in spec['tables'].items()}, 'Recipe chance tables are incomplete.')
    for key, table in spec['tables'].items():
        live = one(connection, 'SELECT * FROM roll_table_versions WHERE id=?', (bindings[table['id']],))
        require(live['table_id'] == key and decode(live['definition']) == table['definition'] and live['hash'] == table['hash'],
                'A recipe changed its frozen chance table.')
    chance = run['chance']
    if spec['applicable'] and spec['beat'] is not None:
        require(isinstance(chance, dict) and isinstance(chance['seed'], str) and 1 <= len(chance['seed']) <= 100
                and chance == resolve_chance(spec, seed=chance['seed']), 'A recipe chance result cannot be reproduced from its recorded draw.')
    else:
        require(chance is None, 'An inapplicable recipe has a chance result.')


def validate_stages(run, jobs):
    draft, reviews, started, pending = None, [], 0, False
    accounted = set()
    for index, stage in enumerate(run['snapshot']['plan']):
        current = [job for job in jobs if job['stage'] == index]
        if stage['skipped']:
            require(not current, 'A skipped recipe stage has jobs.')
            continue
        if not current:
            pending = True
            continue
        require(not pending and len(current) == len(stage['templates']), 'A recipe has incomplete or out-of-order stages.')
        started += 1
        by_step = {job['step']: job for job in current}
        require(set(by_step) == {template['step'] for template in stage['templates']}, 'Recipe jobs differ from planned tasks.')
        ordered = [by_step[template['step']] for template in stage['templates']]
        for job, template in zip(ordered, stage['templates'], strict=True):
            expected = bind_job(compile_job(run['snapshot'], template, draft, reviews, run['chance']), run['bindings'])
            require(job['snapshot'] == expected, 'A recipe job changed its frozen request or preceding results.')
            validate_output(job, expected)
            accounted.add(job['id'])
        if any(job['status'] != 'done' for job in ordered):
            pending = True
        elif stage['task'] == 'review':
            reviews = [job['result'] for job in ordered]
        else:
            draft = ordered[0]['result']['replacement']
    require(len(accounted) == len(jobs) and started == run['revision'], 'A recipe changed its stage revision sequence.')


def validate_output(row, snapshot):
    require(row['status'] in {'queued', 'running', 'done', 'error', 'cancelled', 'interrupted'}, 'Invalid recipe job status.')
    result = decode(row['result']) if isinstance(row['result'], str) else row['result']
    if row['status'] == 'done':
        usage = decode(row['usage']) if isinstance(row['usage'], str) else row['usage']
        completion = StreamCompletion(**usage['completion'])
        try:
            completion.validate(snapshot['profile']['config'])
        except DomainError:
            require(False, 'A completed recipe job lacks a successful provider completion receipt.')
        require(result == parse_recipe_output(row['output'], snapshot), 'A recipe result differs from its original output.')
    else:
        require(result is None, 'An unfinished recipe job has a usable result.')
