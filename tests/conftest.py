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
    response = client.post("/api/stories", json={"title": "A quiet place"})
    assert response.status_code == 201
    return response.json()
