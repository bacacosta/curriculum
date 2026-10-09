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


def test_inline_subitem_creation_returns_local_row(client):
    client.post('/sections', data={'title': 'Work'})
    section = client.get('/api/resume').json()['sections'][0]
    url = f"/sections/{section['id']}/items"
    client.post(url, data={'content': 'Parent'})
    parent = client.get('/api/resume').json()['sections'][0]['children'][0]
    response = client.post(url, data={'content': '<Child>', 'parent_id': parent['id']},
                           headers={'HX-Request': 'true', 'X-Inline-Create': 'true'})
    assert response.status_code == 200
    assert 'id="editor"' not in response.text
    assert '&lt;Child&gt;' in response.text
    child = client.get('/api/resume').json()['sections'][0]['children'][0]['children'][0]
    assert f'data-item-id="{child["id"]}"' in response.text
    assert f'data-parent-id="{child["id"]}"' in response.text
    assert 'class="icon-button delete-item"' in response.text
    assert f'data-url="/items/{child["id"]}/edit"' in response.text
    client.post(url, data={'content': 'Grandchild', 'parent_id': child['id']},
                headers={'HX-Request': 'true', 'X-Inline-Create': 'true'})
    tree = client.get('/api/resume').json()['sections'][0]['children'][0]
    assert tree['children'][0]['children'][0]['content'] == 'Grandchild'


def test_move_reorders_reparents_and_moves_subtrees(client):
    for title in ['One', 'Two']:
        client.post('/sections', data={'title': title})
    first, second = client.get('/api/resume').json()['sections']
    sid = first['id']
    for text in ['A', 'B', 'C']:
        client.post(f'/sections/{sid}/items', data={'content': text})
    a, b, c = client.get('/api/resume').json()['sections'][0]['children']
    client.post(f'/sections/{sid}/items', data={'content': 'Child', 'parent_id': a['id']})
    assert client.post(f"/items/{c['id']}/move", data={'section_id': sid, 'position': 0}).status_code == 200
    assert [i['content'] for i in client.get('/api/resume').json()['sections'][0]['children']] == ['C', 'A', 'B']
    assert client.post(f"/items/{a['id']}/move", data={'section_id': sid, 'parent_id': b['id'], 'position': 0}).status_code == 200
    tree = client.get('/api/resume').json()['sections'][0]['children']
    assert tree[1]['children'][0]['children'][0]['content'] == 'Child'
    assert client.post(f"/items/{b['id']}/move", data={'section_id': second['id'], 'position': 0}).status_code == 200
    main.init_db()
    sections = client.get('/api/resume').json()['sections']
    moved = sections[1]['children'][0]
    assert moved['children'][0]['children'][0]['section_id'] == second['id']
    assert sections[0]['children'][0]['content'] == 'C'
    assert client.post(f"/items/{a['id']}/move", data={'section_id': sid, 'position': 1}).status_code == 200
    assert [i['content'] for i in client.get('/api/resume').json()['sections'][0]['children']] == ['C', 'A']
    with main.database() as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_invalid_moves_leave_tree_unchanged(client):
    client.post('/sections', data={'title': 'One'})
    client.post('/sections', data={'title': 'Two'})
    first, second = client.get('/api/resume').json()['sections']
    sid = first['id']
    client.post(f'/sections/{sid}/items', data={'content': 'Parent'})
    parent = client.get('/api/resume').json()['sections'][0]['children'][0]
    client.post(f'/sections/{sid}/items', data={'content': 'Child', 'parent_id': parent['id']})
    original = client.get('/api/resume').json()
    child = original['sections'][0]['children'][0]['children'][0]
    for data, status in [
        ({'section_id': sid, 'parent_id': parent['id'], 'position': 0}, 422),
        ({'section_id': sid, 'parent_id': child['id'], 'position': 0}, 422),
        ({'section_id': second['id'], 'parent_id': child['id'], 'position': 0}, 422),
        ({'section_id': sid, 'position': -1}, 422),
        ({'section_id': sid, 'position': 9}, 422),
        ({'section_id': 9999, 'position': 0}, 404),
        ({'section_id': sid, 'parent_id': 9999, 'position': 0}, 404),
    ]:
        assert client.post(f"/items/{parent['id']}/move", data=data).status_code == status
        assert client.get('/api/resume').json() == original


def test_inline_section_creation_returns_section_card(client):
    page = client.get('/').text
    assert 'class="icon-button add-section"' in page
    assert '<h2>New section</h2>' not in page
    response = client.post('/sections', data={'title': '<Skills>'},
                           headers={'HX-Request': 'true', 'X-Inline-Create': 'true'})
    assert response.status_code == 200
    section = client.get('/api/resume').json()['sections'][0]
    assert f'data-section-id="{section["id"]}"' in response.text
    assert '&lt;Skills&gt;' in response.text
    assert 'class="icon-button add-bullet"' in response.text
    assert 'class="icon-button delete-section"' in response.text
    assert f'data-url="/sections/{section["id"]}/edit"' in response.text
    assert 'id="editor"' not in response.text
    assert 'class="icon-button add-section"' not in response.text


def test_section_reorder_preserves_contents_and_persists(client):
    for title in ['First', 'Second', 'Third']:
        client.post('/sections', data={'title': title})
    first, second, third = client.get('/api/resume').json()['sections']
    client.post(f"/sections/{third['id']}/items", data={'content': 'Keep this bullet'})
    response = client.post(f"/sections/{third['id']}/move", data={'position': 0})
    assert response.status_code == 200
    main.init_db()
    tree = client.get('/api/resume').json()['sections']
    assert [section['title'] for section in tree] == ['Third', 'First', 'Second']
    assert tree[0]['children'][0]['content'] == 'Keep this bullet'
    assert [section['position'] for section in tree] == [0, 1, 2]
    assert client.post(f"/sections/{third['id']}/move", data={'position': 2}).status_code == 200
    original = client.get('/api/resume').json()
    assert [section['title'] for section in original['sections']] == ['First', 'Second', 'Third']
    for position in [-1, 3]:
        assert client.post(f"/sections/{first['id']}/move", data={'position': position}).status_code == 422
        assert client.get('/api/resume').json() == original
    assert client.post('/sections/9999/move', data={'position': 0}).status_code == 404
    assert 'class="icon-button section-drag-handle"' in client.get('/').text
