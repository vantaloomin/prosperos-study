"""Bounded embeddings on explicitly configured OpenAI-compatible connections."""
import asyncio
import json
import math

import httpx

from server.errors import require
from server.providers.http import check_status
from server.providers.requests import headers_for, validate_key

MAX_DIMENSIONS = 8192
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def unit_vector(value):
    require(isinstance(value, list) and 1 <= len(value) <= MAX_DIMENSIONS,
            'The embedding vector has an unsupported size.', 502)
    require(all(type(item) in {float, int} and math.isfinite(item) for item in value),
            'The embedding vector contains invalid numbers.', 502)
    norm = math.hypot(*value)
    require(math.isfinite(norm) and norm > 0, 'The embedding vector is empty or invalid.', 502)
    return [item / norm for item in value]


def parse_embeddings(data, count, requested_model):
    require(isinstance(data, dict) and isinstance(data.get('data'), list) and len(data['data']) == count,
            'The service returned an incomplete embedding batch.', 502)
    rows = data['data']
    require(all(isinstance(row, dict) and type(row.get('index')) is int for row in rows)
            and {row['index'] for row in rows} == set(range(count)), 'Invalid embedding batch indexes.', 502)
    vectors = [unit_vector(row.get('embedding')) for row in sorted(rows, key=lambda row: row['index'])]
    require(len({len(vector) for vector in vectors}) == 1, 'Embedding dimensions changed within a batch.', 502)
    model = data.get('model', requested_model)
    require(isinstance(model, str) and 0 < len(model) <= 300, 'Invalid embedding model identity.', 502)
    usage = data.get('usage', {})
    require(isinstance(usage, dict), 'Invalid embedding usage.', 502)
    return {'vectors': vectors, 'model': model, 'usage': {key: value for key, value in usage.items()
            if key in {'prompt_tokens', 'total_tokens'} and type(value) is int and value >= 0}}


async def embed(config, key, texts, transport=None):
    require(config['provider'] in {'local', 'compatible', 'openai'} and bool(config.get('embedding_model', '').strip()),
            'Choose an embedding model on a Local, OpenAI or compatible connection first.', 409)
    maximum = 2417 if config.get('embedding_input_format') == 'nomic-search-v1' else 2400
    require(1 <= len(texts) <= 16 and all(isinstance(text, str) and 0 < len(text) <= maximum for text in texts),
            'Embedding inputs exceed the bounded batch.', 409)
    validate_key(config['provider'], key)
    base = config['base_url']
    if config['provider'] == 'local' and config.get('local_protocol') == 'lmstudio':
        base = base.removesuffix('/api/v1') + '/v1'
    body = {'model': config['embedding_model'], 'input': texts, 'encoding_format': 'float'}
    deadline = min(config['timeout_seconds'], 30)
    async with asyncio.timeout(deadline):
        async with httpx.AsyncClient(transport=transport, timeout=deadline, follow_redirects=False, trust_env=False) as client:
            async with client.stream('POST', base + '/embeddings', headers=headers_for(config, key), json=body) as response:
                check_status(response)
                payload = bytearray()
                async for part in response.aiter_bytes():
                    payload.extend(part)
                    require(len(payload) <= MAX_RESPONSE_BYTES, 'Embedding response exceeded its limit.', 502)
    return parse_embeddings(json.loads(payload), len(texts), config['embedding_model'])
