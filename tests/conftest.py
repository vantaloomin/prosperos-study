import pytest
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.sqlite3"),
                    headers={"x-roleplay-client": "workspace"}) as test_client:
        yield test_client


@pytest.fixture
def story(client):
    # Most workflow tests explicitly exercise every role. New-mode defaults have their own tests.
    response = client.post("/api/stories", json={"title": "A quiet place", "settings": {"disabled_prompts": []}})
    assert response.status_code == 201
    return response.json()
