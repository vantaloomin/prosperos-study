"""One optional search-planning call; only exact retrieved prose reaches the writer."""
import asyncio
import json
import time
from contextlib import aclosing

from server.database import decode, encode
from server.errors import DomainError
from server.memory.budget import token_estimate
from server.memory.semantic_recall import semantic_search
from server.memory.summary_format import json_payload
from server.memory.writer_recall import MAX_OUTPUT_CHARS, MAX_QUERIES, digest, preparation_profile
from server.memory.writer_recall_packet import final_snapshot, pack_recall
from server.providers.capabilities import input_capacity


def parse_queries(output):
    value = json.loads(json_payload(output))
    if not isinstance(value, dict) or set(value) != {'queries'}:
        raise ValueError('Expected a queries object.')
    queries = value['queries']
    if (not isinstance(queries, list) or len(queries) > MAX_QUERIES
            or any(not isinstance(query, str) or not query.strip() or len(query) > 1000 for query in queries)):
        raise ValueError('Invalid bounded search queries.')
    return list(dict.fromkeys(query.strip() for query in queries))


def reusable(usage):
    receipt = usage.get('writer_recall', {})
    result = {'writer_recall': receipt} if receipt.get('status') in {'completed', 'fallback'} else {}
    if 'continuity_revision' in usage:
        result['continuity_revision'] = usage['continuity_revision']
    return result


async def collect(provider, profile, prompt, content, receipt):
    async with asyncio.timeout(profile['config']['timeout_seconds']):
        async with aclosing(provider.generate(profile, prompt, content)) as events:
            async for event in events:
                receipt['output'] += event.text
                receipt['usage'].update(event.usage)
                if event.model:
                    receipt['actual_model'] = event.model
                if len(receipt['output']) > MAX_OUTPUT_CHARS:
                    receipt['output'] = receipt['output'][:MAX_OUTPUT_CHARS]
                    raise ValueError('Preparation output exceeded its limit.')


async def prepare(provider, candidate, snapshot, state, save):
    if 'writer_recall' not in snapshot:
        return snapshot
    previous = reusable(decode(candidate['usage'])).get('writer_recall')
    if previous:
        state['usage']['writer_recall'] = previous
        return final_snapshot(snapshot, previous['final_input'])
    profile = preparation_profile(decode(candidate['profile']))
    receipt = {'version': snapshot['writer_recall']['version'], 'status': 'preparing', 'base_sha256': digest(snapshot['content']),
               'sources_sha256': snapshot['writer_recall']['sources_sha256'], 'output': '', 'usage': {},
               'config': profile['config'], 'calls': 0}
    if receipt['version'] >= 2:
        receipt['archive_sha256'] = digest(encode(snapshot['writer_recall']))
    state['usage']['writer_recall'] = receipt
    save(candidate['id'], state)
    started = time.monotonic()
    try:
        capacity = input_capacity(profile['config']) if receipt['version'] >= 6 else profile['config']['context_tokens'] - profile['config']['max_output_tokens']
        estimate = token_estimate(snapshot['writer_recall']['prompt'], decode(snapshot['content']))
        if estimate + snapshot['memory']['overhead_margin'] > capacity:
            raise ValueError('Preparation input exceeds its allowance.')
        receipt['calls'] = 1
        save(candidate['id'], state)
        await collect(provider, profile, snapshot['writer_recall']['prompt'], snapshot['content'], receipt)
        queries = parse_queries(receipt['output'])
        semantic = await semantic_search(provider, decode(candidate['profile']), snapshot, queries, receipt,
                                         lambda: save(candidate['id'], state))
        packed = await asyncio.to_thread(pack_recall, snapshot, queries, semantic)
        receipt.update(packed, status='completed')
    except asyncio.CancelledError:
        receipt['status'] = 'cancelled'
        raise
    except (ValueError, DomainError, TimeoutError):
        receipt.update(pack_recall(snapshot, []), status='fallback',
                       reason='Preparation was unavailable, exceeded its limits, or returned invalid searches. Original context retained.')
    except Exception:
        receipt.update(pack_recall(snapshot, []), status='fallback',
                       reason='Preparation failed. Original context retained.')
    finally:
        receipt['seconds'] = time.monotonic() - started
        state['usage']['timings']['recall_seconds'] = receipt['seconds']
        save(candidate['id'], state)
    return final_snapshot(snapshot, receipt['final_input'])
