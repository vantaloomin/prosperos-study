import re

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from server.branches import Branches
from tests.test_history import append
from tests.test_library import create_book, with_book


def test_direct_branch_json_preserves_bytes_and_exposes_only_numeric_durations(client):
    book = create_book(client)
    story = with_book(client, book, "Serialization evidence")
    branch_id = story['branch_id']
    append(client, branch_id, 'Unicode: 雨 · 🌧️\n\n"Quoted" text and \\slashes.', 0)
    expected = Branches(client.app.state.database).detail(branch_id)
    response = client.get(f'/api/branches/{branch_id}')
    assert response.status_code == 200
    assert response.content == JSONResponse(jsonable_encoder(expected)).body
    assert response.json()['attachments'][0]['version_id'] == book['id']
    spans = response.headers['server-timing'].split(', ')
    assert [span.split(';')[0] for span in spans] == [
        'lookup', 'path', 'attachments', 'mechanics', 'close', 'serialize', 'total']
    assert all(re.fullmatch(r'[a-z]+;dur=\d+\.\d{3}', span) for span in spans)
    durations = [float(span.split('=')[1]) for span in spans]
    assert abs(sum(durations[:-1]) - durations[-1]) < .01
    assert response.headers['content-type'] == 'application/json'


def test_direct_response_keeps_missing_branch_errors(client):
    response = client.get('/api/branches/missing')
    assert response.status_code == 404
    assert response.json() == {'detail': 'This item could not be found.'}
    assert 'server-timing' not in response.headers
