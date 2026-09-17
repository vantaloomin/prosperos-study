import math

from server.database import decode, encode, identifier, now, one
from server.errors import require
from server.generations import record_generation, stale_target
from server.lore.placement import writer_context
from server.lore.runtime import attach_lore
from server.mechanics.engine import resolve_beat
from server.mechanics.models import Beat, RngSettings
from server.mechanics.storage import opportunity_stale, opportunity_view


def opportunity_for(connection, run, snapshot, job):
    branch = snapshot['branch']
    existing = connection.execute('SELECT * FROM mechanic_opportunities WHERE branch_id=? AND head_key=?',
                                  (branch['id'], run['head_key'])).fetchone()
    if existing:
        story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
        saved = opportunity_view(dict(existing))
        require(not opportunity_stale(saved, branch, story), 'The prepared beat changed. Start a new branch or skip chance.', 409)
        return saved['id'], saved['snapshot']
    beat = Beat.model_validate(decode(job['result'])['beat'])
    result = resolve_beat(snapshot['tables'], RngSettings.model_validate(snapshot['settings']),
                          beat, snapshot['before'], snapshot['seed'], False)
    if snapshot['writer_snapshot'].get('lore_context'):
        attach_lore(result, snapshot['writer_snapshot']['lore_context'])
    result.update(branch=branch, story_revision=snapshot['story_revision'], reroll_of=None)
    result.update(assessment_id=run['id'], assessment_job_id=job['id'])
    if 'background_state_id' in snapshot['writer_snapshot']:
        result['background_state_id'] = snapshot['writer_snapshot']['background_state_id']
    opportunity_id = identifier()
    connection.execute('INSERT INTO mechanic_opportunities VALUES (?,?,?,?,?,?)',
                       (opportunity_id, branch['story_id'], branch['id'], run['head_key'], encode(result), now()))
    return opportunity_id, result


def apply_opportunity(writer, profiles, opportunity_id, opportunity):
    content = decode(writer['content'])
    content['prepared_beat'] = opportunity['writer']
    if opportunity.get('lore'):
        writer['lore'] = opportunity['lore']
        content = writer_context(content, opportunity['lore'])
    writer.update(content=encode(content), opportunity_id=opportunity_id)
    estimated = math.ceil(len((writer['prompt']['template'] + writer['content']).encode('utf-8')) / 3)
    for profile in profiles:
        capacity = profile['config']['context_tokens'] - profile['config']['max_output_tokens']
        require(estimated <= capacity, f"The assessed beat exceeds {profile['name']}'s context allowance. Continue without chance or use another profile.", 409)
    writer['estimated_input_tokens'] = estimated


def finish_assessment(connection, run, body):
    require(body.without_chance != bool(body.job_id), 'Select one assessment or explicitly continue without chance.')
    snapshot = decode(run['snapshot'])
    writer = snapshot['writer_snapshot']
    _, stale = stale_target(connection, writer)
    require(not stale, 'This assessment belongs to an earlier Story state. Continue from the current branch instead.', 409)
    opportunity_id = None
    if not body.without_chance:
        job = one(connection, 'SELECT * FROM assessment_jobs WHERE id=? AND run_id=?', (body.job_id, run['id']))
        require(job['status'] == 'done', 'Select a completed, validated assessment.', 409)
        opportunity_id, opportunity = opportunity_for(connection, run, snapshot, job)
        apply_opportunity(writer, snapshot['writer_profiles'], opportunity_id, opportunity)
    result = record_generation(connection, writer, snapshot['writer_profiles'])
    connection.execute('UPDATE assessment_runs SET selected_job_id=?,opportunity_id=?,generation_id=?,error=? WHERE id=?',
                       (body.job_id, opportunity_id, result['id'], '', run['id']))
    return result
