"""Freeze bounded, original accepted prose; no Canon, background or prior summaries."""
import hashlib

from pydantic import ValidationError

from server.branches import path_nodes
from server.database import decode, encode, one
from server.errors import DomainError, require
from server.memory.prose_sources import source_chunks, source_evidence
from server.memory.summary_catalog import SUMMARY_KEY
from server.memory.summary_format import json_payload, restore_citations
from server.memory.summary_models import SummaryOutput
from server.stories import check_revision
from server.workflow.context import job_snapshot
from server.workflow.models import ReviewStep


def prepare_summary(connection, branch_id, body):
    branch = one(connection, 'SELECT * FROM branches WHERE id=?', (branch_id,))
    check_revision(branch, body.expected_revision)
    story = one(connection, 'SELECT * FROM stories WHERE id=?', (branch['story_id'],))
    require(len(set(body.source_ids)) == len(body.source_ids), 'Choose distinct Story excerpts.')
    selected = [source_evidence(node, chunk) for node, chunk in source_chunks(connection, branch['head_id'])
                if chunk.id in body.source_ids]
    require(len(selected) == len(body.source_ids), 'A summary source is outside the selected accepted path.', 409)
    return prepared_from_sources(connection, branch, story, selected, body.profile_ids)


def prepared_from_sources(connection, branch, story, selected, profile_ids, *, validate_budget=True):
    context = {'task': 'Summarize these accepted prose excerpts without adding facts or advancing the Story.',
               'authority': 'Derived aid; original quotations retain their speakers and uncertainty.', 'sources': selected}
    jobs = job_snapshot(connection, story, ReviewStep(key=SUMMARY_KEY, profile_ids=profile_ids), context, validate_budget=validate_budget)
    links = [{key: item[key] for key in ('id', 'node_id', 'role', 'start', 'end', 'sha256')} for item in selected]
    key = hashlib.sha256(encode({'links': links, 'jobs': jobs}).encode()).hexdigest()
    return {'branch': branch, 'story_revision': story['revision'], 'source_links': links,
            'content': jobs[0]['content'], 'request_key': key, 'jobs': jobs}


def parse_summary(output, snapshot):
    try:
        result = SummaryOutput.model_validate_json(json_payload(output))
    except ValidationError as error:
        raise DomainError('The summary did not match the required structure. Its output is preserved; inspect the prompt or retry.', 502) from error
    canonical = restore_citations(result, decode(snapshot['content'])['sources'])
    return validate_summary(SummaryOutput.model_validate(canonical), snapshot['content'])


def validate_summary(result, content):
    sources = {item['id']: item['text'] for item in decode(content)['sources']}
    ids = [item.source_id for item in result.items]
    require(len(ids) == len(set(ids)) and set(ids) <= sources.keys(), 'A summary cites repeated or unavailable sources.', 502)
    for item in result.items:
        require(all(quote.strip() and quote in sources[item.source_id] for quote in item.quotes),
                'A summary quotation does not match its accepted source. No memory version was published.', 502)
    return result.model_dump()


def validate_dependencies(connection, snapshot, head_id):
    nodes = {node['id']: node for node in path_nodes(connection, head_id)}
    for link in snapshot['source_links']:
        require(link['node_id'] in nodes, 'This summary belongs to a different path or later point in the Story.', 409)
        node = nodes[link['node_id']]
        text = node['text'][link['start']:link['end']]
        require(node['role'] != 'ooc' and node['role'] == link['role'] and 0 <= link['start'] < link['end'] <= len(node['text'])
                and hashlib.sha256(text.encode()).hexdigest() == link['sha256'], 'A summary source no longer matches accepted prose.', 409)
