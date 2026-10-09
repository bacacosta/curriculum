import sqlite3

import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'resume.sqlite3')
    with TestClient(main.app) as client:
        yield client


def test_crud_nested_items_and_persistence(client):
    assert client.get('/').status_code == 200
    response = client.post('/sections', data={'title': 'Experience'}, headers={'HX-Request': 'true'})
    assert response.status_code == 200
    assert 'id="editor"' in response.text
    assert '<html' not in response.text
    section = client.get('/api/resume').json()['sections'][0]
    sid = section['id']
    client.post(f'/sections/{sid}/items', data={'content': 'Engineer'})
    parent = client.get('/api/resume').json()['sections'][0]['children'][0]['id']
    client.post(f'/sections/{sid}/items', data={'content': 'Built APIs', 'parent_id': parent})
    child = client.get('/api/resume').json()['sections'][0]['children'][0]['children'][0]['id']
    client.post(f'/sections/{sid}/items', data={'content': 'FastAPI', 'parent_id': child})
    client.post(f'/items/{parent}/edit', data={'content': 'Senior engineer'})
    client.post(f'/sections/{sid}/edit', data={'title': 'Work'})
    main.init_db()  # Startup must preserve existing data.
    tree = client.get('/api/resume').json()['sections'][0]
    assert tree['title'] == 'Work'
    assert tree['children'][0]['content'] == 'Senior engineer'
    assert tree['children'][0]['children'][0]['children'][0]['content'] == 'FastAPI'
    client.post(f'/items/{child}/delete')
    assert client.get('/api/resume').json()['sections'][0]['children'][0]['children'] == []
    client.post(f'/sections/{sid}/delete')
    assert client.get('/api/resume').json() == {'sections': []}
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 0


def test_validation_and_parent_integrity(client):
    assert client.post('/sections', data={'title': '  '}).status_code == 422
    client.post('/sections', data={'title': 'One'})
    client.post('/sections', data={'title': 'Two'})
    first, second = client.get('/api/resume').json()['sections']
    client.post(f"/sections/{first['id']}/items", data={'content': '<script>alert(1)</script>'})
    item = client.get('/api/resume').json()['sections'][0]['children'][0]
    assert '&lt;script&gt;' in client.get('/').text
    assert client.post(f"/sections/{second['id']}/items", data={'content': 'Invalid', 'parent_id': item['id']}).status_code == 422
    assert client.post('/items/999/delete').status_code == 404
    with main.database() as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('INSERT INTO items(section_id, parent_id, content, position) VALUES (?, ?, ?, ?)', (second['id'], item['id'], 'Invalid', 0))
