from uuid import uuid4

import pytest

from server.adoptions import Adoptions
from server.models import AdoptionApply
from tests.test_archives import backup, restore
from tests.test_history import append
from tests.test_library import adoption_request, create_book, publish, with_book


def character(client, book, name='Reader'):
    response = client.post('/api/library', json={'kind': 'character', 'name': name,
        'content': {'text': 'A careful reader.', 'lorebook_versions': [book['id']]}})
    assert response.status_code == 201, response.text
    return response.json()


def repin(client, person, book):
    response = client.post(f"/api/library/{person['asset_id']}/versions", json={
        'expected_version_id': person['id'], 'name': person['name'],
        'content': {**person['content'], 'lorebook_versions': [book['id']]}})
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, version, related=()):
    response = client.post(f"/api/versions/{version['id']}/adoption/preview",
                           json={'additional_version_ids': list(related)})
    assert response.status_code == 200, response.text
    return response.json()


def apply(client, version, plan, related=(), **overrides):
    body = {**adoption_request(plan), 'additional_version_ids': list(related),
            'preview_hash': plan['preview_hash'], **overrides}
    return client.post(f"/api/versions/{version['id']}/adoption", json=body), body


def bindings(client, story):
    return {item['asset_id']: item['version_id'] for item in
            client.get(f"/api/stories/{story['story_id']}").json()['attachments']}


def test_character_update_previews_lore_change_and_requires_reviewed_hash(client):
    book = create_book(client)
    person = character(client, book)
    story = with_book(client, person, 'Linked')
    node = append(client, story['branch_id'], 'Historical rain.', 0)
    newer = publish(client, book)
    updated = repin(client, person, newer)
    plan = preview(client, updated)
    assert plan['can_apply']
    changes = {item['asset_id']: item for item in plan['targets'][0]['changes']}
    assert changes[book['asset_id']]['reason'] == 'dependency'
    assert changes[person['asset_id']]['reason'] == 'selected'
    assert bindings(client, story)[book['asset_id']] == book['id']
    denied, _ = apply(client, updated, plan, preview_hash=None)
    assert denied.status_code == 409
    accepted, request = apply(client, updated, plan)
    assert accepted.json() == {'updated': 1}
    assert client.post(f"/api/versions/{updated['id']}/adoption", json=request).json() == accepted.json()
    assert set(bindings(client, story).values()) == {newer['id'], updated['id']}
    branch = client.get(f"/api/branches/{story['branch_id']}").json()
    fork = client.post(f"/api/branches/{story['branch_id']}/forks", json={'operation_id': uuid4().hex,
        'expected_revision': branch['revision'], 'node_id': node, 'name': 'Preserved earlier world'}).json()
    historical = client.get(f"/api/branches/{fork['branch_id']}").json()
    assert {item['version_id'] for item in historical['attachments']} == {book['id'], person['id']}


def test_explicit_related_updates_resolve_multiple_characters_atomically_in_all_stories(client):
    book = create_book(client)
    first, second = character(client, book, 'First reader'), character(client, book, 'Second reader')
    together = client.post('/api/stories', json={'title': 'Together', 'attachments': [
        {'asset_id': item['asset_id'], 'version_id': item['id']} for item in (first, second)]}).json()
    archived = with_book(client, first, 'Archived reader')
    other = with_book(client, book, 'Just the world')
    with client.app.state.database.connect(write=True) as connection:
        connection.execute('UPDATE stories SET archived=1 WHERE id=?', (archived['story_id'],))
    newer = publish(client, book)
    first_new, second_new = repin(client, first, newer), repin(client, second, newer)
    blocked = preview(client, newer)
    assert not blocked['can_apply']
    assert any(target['conflicts'] for target in blocked['targets'])
    denied, _ = apply(client, newer, blocked)
    assert denied.status_code == 400
    assert bindings(client, other)[book['asset_id']] == book['id']
    related = [first_new['id'], second_new['id']]
    plan = preview(client, newer, related)
    assert plan['can_apply'] and len(plan['targets']) == 3
    accepted, _ = apply(client, newer, plan, related)
    assert accepted.json() == {'updated': 3}
    assert set(bindings(client, together).values()) == {newer['id'], first_new['id'], second_new['id']}
    assert client.get(f"/api/stories/{archived['story_id']}").json()['archived']


def test_related_selection_expands_target_set_and_stale_preview_cannot_partially_apply(client):
    book = create_book(client)
    first = with_book(client, book, 'Original')
    newer = publish(client, book)
    plan = preview(client, newer)
    with_book(client, book, 'New use after preview')
    rejected, _ = apply(client, newer, plan)
    assert rejected.status_code == 409
    assert bindings(client, first)[book['asset_id']] == book['id']
    unrelated = create_book(client)
    separate = with_book(client, unrelated, 'Another selected item')
    other_new = publish(client, unrelated)
    widened = preview(client, newer, [other_new['id']])
    assert len(widened['targets']) == 3
    accepted, _ = apply(client, newer, widened, [other_new['id']])
    assert accepted.json() == {'updated': 3}
    assert bindings(client, separate)[unrelated['asset_id']] == other_new['id']


def test_new_link_is_added_and_removed_link_remains_explicitly_attached(client):
    book, other = create_book(client), create_book(client)
    person = character(client, book)
    story = with_book(client, person, 'Changing links')
    updated = repin(client, person, other)
    plan = preview(client, updated)
    change = next(item for item in plan['targets'][0]['changes'] if item['asset_id'] == other['asset_id'])
    assert change['before_version_id'] is None and change['reason'] == 'dependency'
    assert apply(client, updated, plan)[0].status_code == 200
    assert set(bindings(client, story).values()) == {book['id'], other['id'], updated['id']}


def test_disabled_character_keeps_lore_inactive_and_duplicate_versions_are_rejected(client):
    book = create_book(client)
    person = character(client, book)
    story = client.post('/api/stories', json={'title': 'Inactive character', 'attachments': [
        {'asset_id': person['asset_id'], 'version_id': person['id'], 'enabled': False}]}).json()
    newer = repin(client, person, publish(client, book))
    plan = preview(client, newer)
    assert len(plan['targets'][0]['changes']) == 1
    assert not plan['targets'][0]['changes'][0]['enabled_after']
    assert apply(client, newer, plan)[0].status_code == 200
    assert list(bindings(client, story).values()) == [newer['id']]
    response = client.post(f"/api/versions/{newer['id']}/adoption/preview", json={'additional_version_ids': [person['id']]})
    assert response.status_code == 400


def test_rollback_uses_preserved_dependencies_and_rejects_a_substituted_preview(client):
    book = create_book(client)
    person = character(client, book)
    story = with_book(client, person, 'Reversible')
    newer = repin(client, person, publish(client, book))
    assert apply(client, newer, preview(client, newer))[0].status_code == 200
    plan = preview(client, person)
    assert apply(client, person, plan, preview_hash='wrong')[0].status_code == 409
    assert apply(client, person, plan)[0].status_code == 200
    assert set(bindings(client, story).values()) == {book['id'], person['id']}


def test_nested_lore_dependencies_are_resolved_without_obsolete_parent_requirements(client):
    leaf = create_book(client)
    response = client.post('/api/library', json={'kind': 'lorebook', 'name': 'Nested book',
        'content': {'text': 'Linked world material.', 'lorebook_versions': [leaf['id']]}})
    assert response.status_code == 201
    middle = response.json()
    parent = character(client, middle)
    story = with_book(client, parent, 'Nested lore')
    leaf_new = publish(client, leaf)
    middle_new = repin(client, middle, leaf_new)
    parent_new = repin(client, parent, middle_new)
    plan = preview(client, parent_new)
    assert plan['can_apply'] and len(plan['targets'][0]['changes']) == 3
    assert apply(client, parent_new, plan)[0].status_code == 200
    assert set(bindings(client, story).values()) == {parent_new['id'], middle_new['id'], leaf_new['id']}


def test_failure_during_multi_story_application_rolls_back_every_manifest(client, monkeypatch):
    book = create_book(client)
    person = character(client, book)
    stories = [with_book(client, person, name) for name in ['A', 'B']]
    updated = repin(client, person, publish(client, book))
    plan = preview(client, updated)
    original, calls = Adoptions._apply_story, []

    def interrupt(connection, target, operation_id):
        original(connection, target, operation_id)
        calls.append(target['story_id'])
        if len(calls) == 2:
            raise RuntimeError('Fixture interruption after second update')

    monkeypatch.setattr(Adoptions, '_apply_story', staticmethod(interrupt))
    body = AdoptionApply(**adoption_request(plan), preview_hash=plan['preview_hash'])
    with pytest.raises(RuntimeError, match='Fixture interruption'):
        Adoptions(client.app.state.database).apply(updated['id'], body)
    for story in stories:
        assert set(bindings(client, story).values()) == {book['id'], person['id']}
    with client.app.state.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM adoptions').fetchone()[0] == 0


def test_linked_update_restore_preserves_old_and_new_manifests(client):
    book = create_book(client)
    person = character(client, book)
    story = with_book(client, person, 'Portable links')
    append(client, story['branch_id'], 'It rains before the update.', 0)
    new_book = publish(client, book)
    new_person = repin(client, person, new_book)
    plan = preview(client, new_book, [new_person['id']])
    assert apply(client, new_book, plan, [new_person['id']])[0].status_code == 200
    archive, document = backup(client, story)
    _, mapping = restore(client, archive)
    restored = {'story_id': mapping[story['story_id']], 'branch_id': mapping[story['branch_id']]}
    assert set(bindings(client, restored).values()) == {mapping[new_book['id']], mapping[new_person['id']]}
    assert len(document['data']['adoptions']) == 1
    assert {version['id'] for version in document['data']['asset_versions']} == {book['id'], person['id'], new_book['id'], new_person['id']}
    backup(client, restored)
