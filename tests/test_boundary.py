def test_write_guard_rejects_cross_site_form_and_validates_payload(client):
    response = client.post("/api/stories", json={"title": "Blocked"}, headers={"x-roleplay-client": ""})
    assert response.status_code == 403
    assert client.post("/api/stories", json={"title": "  "}).status_code == 422
    assert client.post("/api/stories", json={"title": "Valid", "shell": "ignored?"}).status_code == 422


def test_database_reopens_without_losing_stories(client, story):
    from server.database import Database
    from server.stories import Stories

    reopened = Database(client.app.state.database.path)
    assert Stories(reopened).detail(story["story_id"])["title"] == "A quiet place"
