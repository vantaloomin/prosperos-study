"""Verify quoted originals and live lineage without rewriting archived model inputs."""
import hashlib

from server.archives.authoring import validate_configuration
from server.branches import path_nodes
from server.database import decode, one
from server.errors import require
from server.memory.summary_catalog import SUMMARY_KEY
from server.memory.summary_context import parse_summary, validate_dependencies, validate_summary
from server.memory.summary_models import SummaryOutput


def validate_summaries(connection, data):
    runs = {row['id']: validate_run(connection, row) for row in data['summary_runs']}
    jobs = {row['id']: row for row in data['summary_jobs']}
    for job in jobs.values():
        snapshot = decode(job['snapshot'])
        require(job['step'] == snapshot['step'] == snapshot['prompt']['key'] == SUMMARY_KEY, 'Invalid summary role.')
        require(snapshot['content'] == runs[job['run_id']]['content'], 'Summary comparisons need identical accepted sources.')
        validate_configuration(connection, snapshot)
        validate_output(job, snapshot)
    for attempt in data['summary_attempts']:
        validate_output(attempt, decode(jobs[attempt['job_id']]['snapshot']))
    versions = {row['id']: row for row in data['summary_versions']}
    for row in versions.values():
        validate_version(connection, row, runs[row['run_id']], jobs[row['job_id']], versions)


def validate_run(connection, row):
    snapshot = decode(row['snapshot'])
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (row['branch_id'],))
    require(snapshot['branch']['id'] == branch['id'] and snapshot['branch']['story_id'] == branch['story_id'], 'Invalid summary Story.')
    require(snapshot['request_key'] == row['request_key'] and len(row['request_key']) == 64, 'Invalid summary request identity.')
    head = one(connection, 'SELECT story_id FROM nodes WHERE id=?', (snapshot['branch']['head_id'],))
    require(head['story_id'] == branch['story_id'], 'A summary head crosses Stories.')
    content = decode(snapshot['content'])
    require(set(content) == {'task', 'authority', 'sources'}, 'Unsupported summary context.')
    sources, links = content['sources'], snapshot['source_links']
    require(1 <= len(sources) <= 8 and len(sources) == len(links), 'Invalid summary source count.')
    require(len({link['id'] for link in links}) == len(links), 'Summary sources must be distinct.')
    for source, link in zip(sources, links, strict=True):
        validate_source(source, link)
    validate_dependencies(connection, snapshot, snapshot['branch']['head_id'])
    return snapshot


def validate_source(source, link):
    require(set(link) == {'id', 'node_id', 'role', 'start', 'end', 'sha256'}, 'Invalid live summary source link.')
    require(set(source) == {'id', 'source_id', 'title', 'text', 'start', 'end', 'sha256', 'kind', 'node_id', 'role'},
            'Invalid frozen summary source.')
    require(all(source[key] == link[key] for key in ('id', 'role', 'start', 'end', 'sha256')), 'Summary source coordinates differ.')
    require(type(link['start']) is int and type(link['end']) is int and 0 <= link['start'] < link['end'], 'Invalid summary range.')
    require(0 < len(source['text']) <= 2400 and len(source['text']) == source['end'] - source['start'], 'Invalid summary source length.')
    require(hashlib.sha256(source['text'].encode()).hexdigest() == link['sha256'], 'A frozen summary source was changed.')


def validate_output(row, snapshot):
    require(row['status'] in {'queued', 'running', 'done', 'error', 'cancelled', 'interrupted'}, 'Invalid summary status.')
    if row['status'] == 'done':
        require(decode(row['result']) == parse_summary(row['output'], snapshot), 'Summary output differs from its validated result.')


def validate_version(connection, row, run, job, versions):
    branch = one(connection, 'SELECT story_id FROM branches WHERE id=?', (row['branch_id'],))
    node = one(connection, 'SELECT story_id FROM nodes WHERE id=?', (row['node_id'],))
    require(branch['story_id'] == node['story_id'] == run['branch']['story_id'], 'Summary publication crosses Stories.')
    require(job['run_id'] == row['run_id'] and job['status'] == 'done', 'A saved summary needs its completed request.')
    validate_dependencies(connection, run, row['node_id'])
    validate_summary(SummaryOutput.model_validate(decode(row['result'])), run['content'])
    if row['parent_id']:
        parent = versions[row['parent_id']]
        require(parent['run_id'] == row['run_id'], 'A summary version replaces another request.')
        require(parent['node_id'] in {node['id'] for node in path_nodes(connection, row['node_id'])},
                'A summary version replaces a decision from a different accepted path.')
