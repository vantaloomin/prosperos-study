import asyncio
import sqlite3

import pytest

from scripts.relationship_evaluation import fixture
from scripts.relationship_live_evaluation import (
    MODEL,
    ObservedProvider,
    require_loaded,
    saved_credential,
)
from server.database import decode, encode
from server.errors import DomainError
from server.providers.config import ProfileConfig
from server.providers.events import ProviderEvent


def test_evaluation_reads_latest_profile_without_initializing_or_modifying_database(tmp_path):
    path = tmp_path / 'profile.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.executescript('CREATE TABLE profiles(id,latest_version_id); CREATE TABLE profile_versions(id,config,credential_ref);')
        connection.execute('INSERT INTO profiles VALUES (?,?)', ('or', 'new'))
        connection.executemany('INSERT INTO profile_versions VALUES (?,?,?)', [
            ('old', encode({'provider': 'openrouter'}), 'stale-fixture-reference'),
            ('new', encode({'provider': 'openrouter'}), 'latest-fixture-reference')])
    before = path.read_bytes()
    assert saved_credential(path, 'or') == 'latest-fixture-reference'
    assert path.read_bytes() == before


def test_live_evaluation_records_requests_without_keys_and_stops_after_auth_failure(tmp_path):
    provider = ObservedProvider('fixture-reference', tmp_path, 3)
    config = ProfileConfig(provider='openrouter', model=MODEL).model_dump()

    class Transport:
        async def generate(self, profile, prompt, content):
            assert profile['credential_ref'] == 'fixture-reference'
            raise DomainError('Fixture authentication failure.', 502, 'authentication')
            yield ProviderEvent()

    provider.service = Transport()

    async def request():
        async for _ in provider.generate({'config': config}, 'synthetic prompt', 'synthetic input'):
            pass

    with pytest.raises(DomainError, match='authentication'):
        asyncio.run(request())
    assert len(provider.calls) == 1
    with pytest.raises(DomainError, match='authentication'):
        asyncio.run(request())
    assert len(provider.calls) == 1
    journal = (tmp_path / 'requests.json').read_text(encoding='utf-8')
    assert 'fixture-reference' not in journal and 'credential_ref' not in journal
    assert decode(journal)[0]['code'] == 'authentication'


def test_local_evaluation_requires_loaded_instance_and_supported_settings():
    config = {'model': 'loaded-instance', 'context_tokens': 4096, 'local_reasoning': 'off'}
    data = {'models': [{'key': 'downloaded-model', 'loaded_instances': [],
                        'capabilities': {'reasoning': {'allowed_options': ['off', 'on']}}}]}
    with pytest.raises(DomainError, match='not loaded'):
        require_loaded(data, config)
    data['models'][0]['loaded_instances'] = [{'id': 'loaded-instance', 'config': {'context_length': 8192}}]
    require_loaded(data, config)
    with pytest.raises(DomainError, match='insufficient context'):
        require_loaded(data, {**config, 'context_tokens': 16384})
    with pytest.raises(DomainError, match='reasoning'):
        require_loaded(data, {**config, 'local_reasoning': 'high'})


def test_live_fixture_is_directed_prose_and_does_not_reveal_case_in_story_title(client):
    story, _, _ = fixture(client, 'successful_sibling', directed=True)
    current = client.get('/api/stories/' + story['story_id']).json()
    branch = client.get('/api/branches/' + story['branch_id']).json()
    assert current['title'] == 'The parcel'
    assert current['settings']['experience'] == 'directed'
    assert current['settings']['player_agency'] == 'shared'
    assert all(row['role'] == 'narrator' for row in branch['messages'])
