from server.database import decode
from tests.test_archives import backup, restore
from tests.test_knowledge_lens import snapshot
from tests.test_knowledge_references import adopt, fixture, generated, grant, publish, sources
from tests.test_memory_controls import entry, evidence, save, view
from tests.test_scene_continuity import acceptance_body, ready_continuity


def test_stale_mixed_denial_cannot_silently_widen_remaining_prose_grants(client):
    story, character, _, book = fixture(client)
    branch = story['branch_id']
    prose = evidence(client, branch)
    reference = [source for source in sources(client, branch) if source['asset_id'] == book['asset_id'] and source['title'] == 'Ferry']
    voice = [source for source in sources(client, branch) if source['field'] == 'voice']
    grants = [entry(prose, stance='knows', character_id=character['asset_id']),
              entry(voice, stance='knows', character_id=character['asset_id'])]
    deny = entry([*prose, *reference], stance='unaware', character_id=character['asset_id'])
    save(client, branch, [*grants, deny])
    adopt(client, publish(client, book, content={'text': 'New ferry rules.'}))
    assert view(client, branch)['unavailable_entries'][0]['id'] == deny['id']
    result = snapshot(client, branch, knowledge_character_id=character['asset_id'])
    assert result['knowledge_lens']['selected_ids'] == [grants[1]['id']]
    assert 'arrives at the shore' not in result['content']
    generated(client, story, character)
    file, _ = backup(client, story)
    restore(client, file)


def test_reference_decisions_remain_exact_in_scene_workflow_and_repeated_archive(client):
    story, character, _, book = fixture(client)
    grant(client, story, character, book)
    run_id, _ = ready_continuity(client, story)
    response = client.post('/api/scenes/' + run_id + '/accept', json=acceptance_body(client, run_id, as_new_branch=True))
    assert response.status_code == 200, response.text
    file, _ = backup(client, story)
    _, mapping = restore(client, file)
    with client.app.state.database.connect() as connection:
        origin = connection.execute('SELECT snapshot FROM scene_runs WHERE id=?', (run_id,)).fetchone()
        restored = connection.execute('SELECT snapshot FROM scene_runs WHERE id=?', (mapping[run_id],)).fetchone()
        assert decode(origin['snapshot'])['author_memory'] == decode(restored['snapshot'])['author_memory']
    file2, _ = backup(client, {key: mapping[value] for key, value in story.items()})
    restore(client, file2)


def test_historical_review_cannot_import_a_later_reference_edition_through_author_decisions(client):
    from server.workflow.context import review_snapshot
    from server.workflow.models import ReviewPreview
    from tests.test_memory_maintenance import append
    story, character, _, book = fixture(client)
    branch = story['branch_id']
    old = client.get('/api/branches/' + branch).json()['head_id']
    revised = publish(client, book, content={'text': '# Ferry\\nFUTURE_EDITION ferry rules.'})
    adopt(client, revised)
    source = [item for item in sources(client, branch) if item['asset_id'] == book['asset_id']]
    save(client, branch, [entry(source, stance='knows', character_id=character['asset_id'], text='FUTURE_EDITION interpretation.')])
    later = append(client, branch, 'Elin considers the fare.')
    current = client.get('/api/branches/' + branch).json()
    def review(through):
        with client.app.state.database.connect() as connection:
            return review_snapshot(connection, branch, ReviewPreview(expected_revision=current['revision'],
                through_node_id=through, steps=[{'key': 'review-continuity'}, {'key': 'review-plausibility'}]))
    historic = review(old)
    assert all('FUTURE_EDITION' not in job['content'] for job in historic['jobs'])
    recent = review(later)
    assert 'FUTURE_EDITION' in recent['jobs'][0]['content']
    assert 'FUTURE_EDITION' not in recent['jobs'][1]['content']
