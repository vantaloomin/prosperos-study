from uuid import uuid4

import pytest

from server.database import decode
from server.errors import DomainError
from tests.test_archives import backup, restore
from tests.test_generations import DraftProvider, finished
from tests.test_knowledge_lens import fixture, request, snapshot
from tests.test_knowledge_references import fixture as reference_fixture
from tests.test_knowledge_references import grant
from tests.test_writing_resources import create


@pytest.mark.parametrize('references', [False, True])
def test_styled_character_writer_preserves_grants_and_historical_inputs(client, references):
    character = None
    if references:
        story, character, _, book = reference_fixture(client)
        grant(client, story, character, book)
    else:
        story, _, _ = fixture(client)
    lens = {'knowledge_subject': None, 'knowledge_character_id': character['asset_id']} if character else {}
    branch = story['branch_id']
    baseline = snapshot(client, branch, **lens)
    style = create(client, content={'prose': 'Concrete verbs and measured dialogue.'})
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    response = client.post(f'/api/branches/{branch}/generations', json=request(
        client, branch, **lens, writing={'style': style['id']}))
    assert response.status_code == 201, response.text
    run = finished(client, response.json()['id'])
    saved = run['snapshot']
    context = decode(saved['content'])
    assert saved['knowledge_lens']['algorithm'] == 'prospero-character-evidence-v3'
    assert saved['knowledge_lens']['reference_grants'] is references
    assert saved['knowledge_lens']['selected_ids'] == baseline['knowledge_lens']['selected_ids']
    assert context['writing_guidance']['style']['id'] == style['id']
    assert {key: value for key, value in context.items() if key != 'writing_guidance'} == decode(baseline['content'])
    assert 'SECRET' not in saved['content'] and 'PRIVATE PREMISE' not in saved['content']
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    restored = {'story_id': mapping[story['story_id']], 'branch_id': mapping[branch]}
    second, _ = backup(client, restored)
    _, next_map = restore(client, second)
    twice = client.get(f"/api/generations/{next_map[mapping[run['id']]]}").json()
    assert twice['snapshot']['content'] == saved['content']
    assert len(provider.calls) == 1


def test_style_cannot_displace_character_evidence_to_fit(client):
    story, _, _ = fixture(client)
    baseline = snapshot(client, story['branch_id'])
    style = create(client, content={'examples': [{'label': str(index), 'text': 'A' * 20000} for index in range(8)]})
    with pytest.raises(DomainError, match='No evidence was dropped'):
        snapshot(client, story['branch_id'], writing={'style': style['id']})
    plain = snapshot(client, story['branch_id'], writing={'style': 'none', 'recipe': 'none'})
    assert plain['content'] == baseline['content']
    assert 'writing_guidance' not in plain
    provider = DraftProvider()
    client.app.state.runner.provider = provider
    response = client.post(f"/api/branches/{story['branch_id']}/generations", json=request(
        client, story['branch_id'], operation_id=uuid4().hex, writing={'style': style['id']}))
    assert response.status_code == 409 and provider.calls == []
