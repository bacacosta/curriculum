import os
import sqlite3
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('RESUME_DB', str(BASE.parent / 'data' / 'resume.sqlite3')))


@contextmanager
def database():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.executescript((BASE / 'schema.sql').read_text())


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title='Resume editor', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
templates = Jinja2Templates(directory=BASE / 'templates')


def resume():
    with database() as db:
        sections = [dict(row, children=[]) for row in db.execute('SELECT * FROM sections ORDER BY position, id')]
        items = [dict(row, children=[]) for row in db.execute('SELECT * FROM items ORDER BY position, id')]
    section_map = {s['id']: s for s in sections}
    item_map = {i['id']: i for i in items}
    for item in items:
        parent = section_map[item['section_id']] if item['parent_id'] is None else item_map[item['parent_id']]
        parent['children'].append(item)
    return sections


def require_row(db, table, row_id):
    row = db.execute(f'SELECT * FROM {table} WHERE id = ?', (row_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Not found')
    return row


def clean(value, limit):
    value = value.strip()
    if not 1 <= len(value) <= limit:
        raise HTTPException(422, f'Text must contain 1–{limit} characters.')
    return value


def editor_response(request):
    if request.headers.get('HX-Request') == 'true':
        return templates.TemplateResponse(request=request, name='_editor.html', context={'sections': resume()})
    return RedirectResponse('/', status_code=303)


@app.get('/')
def index(request: Request):
    return templates.TemplateResponse(request=request, name='index.html', context={'sections': resume()})


@app.get('/api/resume')
def get_resume():
    return {'sections': resume()}


@app.post('/sections')
def add_section(request: Request, title: str = Form(...)):
    with database() as db:
        cursor = db.execute('INSERT INTO sections(title, position) VALUES (?, (SELECT COALESCE(MAX(position), -1) + 1 FROM sections))', (clean(title, 200),))
        section = dict(require_row(db, 'sections', cursor.lastrowid), children=[])
    if request.headers.get('X-Inline-Create') == 'true':
        return templates.TemplateResponse(request=request, name='_section.html', context={'section': section})
    return editor_response(request)


@app.post('/sections/{section_id}/edit')
def edit_section(section_id: int, request: Request, title: str = Form(...)):
    with database() as db:
        require_row(db, 'sections', section_id)
        db.execute('UPDATE sections SET title = ? WHERE id = ?', (clean(title, 200), section_id))
    return editor_response(request)


@app.post('/sections/{section_id}/delete')
def delete_section(section_id: int, request: Request):
    with database() as db:
        require_row(db, 'sections', section_id)
        db.execute('DELETE FROM sections WHERE id = ?', (section_id,))
    return editor_response(request)


@app.post('/sections/{section_id}/move')
def move_section(section_id: int, position: int = Form(...)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        require_row(db, 'sections', section_id)
        siblings = [row['id'] for row in db.execute(
            'SELECT id FROM sections WHERE id != ? ORDER BY position, id', (section_id,))]
        if not 0 <= position <= len(siblings):
            raise HTTPException(422, 'Position is outside the section list.')
        siblings.insert(position, section_id)
        db.executemany('UPDATE sections SET position = ? WHERE id = ?', enumerate(siblings))
    return {'saved': True}


@app.post('/sections/{section_id}/items')
def add_item(section_id: int, request: Request, content: str = Form(...), parent_id: int | None = Form(None)):
    with database() as db:
        require_row(db, 'sections', section_id)
        if parent_id is not None:
            parent = require_row(db, 'items', parent_id)
            if parent['section_id'] != section_id:
                raise HTTPException(422, 'Parent must belong to the same section.')
        position = db.execute('SELECT COALESCE(MAX(position), -1) + 1 FROM items WHERE section_id = ? AND parent_id IS ?', (section_id, parent_id)).fetchone()[0]
        cursor = db.execute('INSERT INTO items(section_id, parent_id, content, position) VALUES (?, ?, ?, ?)', (section_id, parent_id, clean(content, 5000), position))
        item = dict(require_row(db, 'items', cursor.lastrowid), children=[])
    if request.headers.get('X-Inline-Create') == 'true':
        return templates.TemplateResponse(request=request, name='_item.html', context={'item': item, 'section_id': section_id})
    return editor_response(request)


@app.post('/items/{item_id}/edit')
def edit_item(item_id: int, request: Request, content: str = Form(...)):
    with database() as db:
        require_row(db, 'items', item_id)
        db.execute('UPDATE items SET content = ? WHERE id = ?', (clean(content, 5000), item_id))
    return editor_response(request)


@app.post('/items/{item_id}/delete')
def delete_item(item_id: int, request: Request):
    with database() as db:
        require_row(db, 'items', item_id)
        db.execute('DELETE FROM items WHERE id = ?', (item_id,))
    return editor_response(request)


@app.post('/items/{item_id}/move')
def move_item(item_id: int, section_id: int = Form(...),
              parent_id: int | None = Form(None), position: int = Form(...)):
    if position < 0:
        raise HTTPException(422, 'Position must be nonnegative.')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        item = require_row(db, 'items', item_id)
        require_row(db, 'sections', section_id)
        descendants = [row['id'] for row in db.execute('''
            WITH RECURSIVE subtree(id) AS (
                SELECT id FROM items WHERE id = ?
                UNION ALL SELECT items.id FROM items JOIN subtree ON items.parent_id = subtree.id
            ) SELECT id FROM subtree
        ''', (item_id,))]
        if parent_id is not None:
            parent = require_row(db, 'items', parent_id)
            if parent_id in descendants:
                raise HTTPException(422, 'An item cannot be moved into itself or its descendants.')
            if parent['section_id'] != section_id:
                raise HTTPException(422, 'Parent must belong to the destination section.')
        siblings = [row['id'] for row in db.execute(
            'SELECT id FROM items WHERE section_id = ? AND parent_id IS ? AND id != ? ORDER BY position, id',
            (section_id, parent_id, item_id))]
        if position > len(siblings):
            raise HTTPException(422, 'Position is outside the destination list.')
        # Defer composite foreign keys while relocating the whole subtree.
        db.execute('PRAGMA defer_foreign_keys = ON')
        db.executemany('UPDATE items SET section_id = ? WHERE id = ?',
                       [(section_id, descendant) for descendant in descendants])
        db.execute('UPDATE items SET parent_id = ? WHERE id = ?', (parent_id, item_id))
        old_siblings = [row['id'] for row in db.execute(
            'SELECT id FROM items WHERE section_id = ? AND parent_id IS ? ORDER BY position, id',
            (item['section_id'], item['parent_id']))]
        db.executemany('UPDATE items SET position = ? WHERE id = ?', enumerate(old_siblings))
        siblings.insert(position, item_id)
        db.executemany('UPDATE items SET position = ? WHERE id = ?', enumerate(siblings))
    return {'saved': True}
