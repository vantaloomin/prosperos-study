from server.archives.authoring import validate_configuration
from server.archives.records import related_rows
from server.database import decode, many
from server.errors import require
from server.memory.budget import token_estimate
from server.providers.capabilities import input_capacity
from server.writing.analysis_context import analysis_content, analysis_instructions, parse_analysis
from server.writing.analysis_models import AnalysisPreview
from server.writing.resources import version


def collect_analyses(connection, data, complete):
    data['style_analysis_jobs'] = (many(connection, 'SELECT * FROM style_analysis_jobs ORDER BY rowid') if complete else
        related_rows(connection, 'style_analysis_jobs', 'source_version_id', {row['id'] for row in data['writing_versions']}))
    data['style_analysis_attempts'] = related_rows(connection, 'style_analysis_attempts', 'job_id', {row['id'] for row in data['style_analysis_jobs']})


def validate_analyses(connection, data):
    snapshots = {}
    for row in data['style_analysis_jobs']:
        snapshot = decode(row['snapshot'])
        require(snapshot['protocol'] == 1 and snapshot['step'] == row['step'] == 'library-assist', 'Invalid style analysis protocol.')
        require(snapshot['source_version_id'] == row['source_version_id'] and snapshot['draft_id'] == row['draft_id'], 'Style analysis source changed.')
        AnalysisPreview.model_validate({key: snapshot[key] for key in ('source_version_id', 'draft_id', 'name', 'samples')})
        if row['source_version_id']:
            version(connection, row['source_version_id'], 'style')
        validate_configuration(connection, snapshot)
        require(snapshot['content'] == analysis_content(snapshot['samples']) and snapshot['instructions'] == analysis_instructions(snapshot),
                'Style analysis changed its exact samples or instructions.')
        allowance = input_capacity(snapshot['profile']['config'])
        estimate = token_estimate(snapshot['instructions'], decode(snapshot['content']))
        margin = min(512, max(128, allowance // 50))
        require(snapshot['input_allowance'] == allowance and snapshot['estimated_input_tokens'] == estimate
                and snapshot['overhead_margin'] == margin and estimate + margin <= allowance, 'Style analysis has altered budget decisions.')
        validate_output(row, snapshot)
        snapshots[row['id']] = snapshot
    for row in data['style_analysis_attempts']:
        validate_output(row, snapshots[row['job_id']])


def validate_output(row, snapshot):
    require(row['status'] in {'queued', 'running', 'done', 'error', 'cancelled', 'interrupted'}, 'Invalid style analysis status.')
    if row['status'] == 'done':
        require(decode(row['result']) == parse_analysis(row['output'], snapshot), 'Style analysis suggestions differ from their original output.')
    else:
        require(decode(row['result']) is None, 'An unfinished style analysis has usable suggestions.')


def upgrade_analyses(document):
    from server.archives.format import STYLE_ANALYSIS_TABLES, V49_TABLES
    if document['version'] == 49:
        require(set(document['data']) == set(V49_TABLES), 'Version 49 needs its original record groups.')
        document['data'].update({table: [] for table in STYLE_ANALYSIS_TABLES})
        document['version'] = 50
    return document
