import os
import sqlite3
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.pdf import render_pdf

BASE = Path(__file__).resolve().parent
DB_PATH = Path(
    os.environ.get("RESUME_DB", str(BASE.parent / "data" / "resume.sqlite3"))
)


@contextmanager
def database():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.executescript((BASE / "schema.sql").read_text())


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="Resume editor", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


def get_sections():
    with database() as db:
        sections = [
            dict(row, children=[])
            for row in db.execute("SELECT * FROM sections ORDER BY position, id")
        ]
        bullets = [
            dict(row, children=[])
            for row in db.execute("SELECT * FROM bullets ORDER BY position, id")
        ]
    section_map = {section["id"]: section for section in sections}
    bullet_map = {bullet["id"]: bullet for bullet in bullets}
    for bullet in bullets:
        parent = (
            section_map[bullet["section_id"]]
            if bullet["parent_id"] is None
            else bullet_map[bullet["parent_id"]]
        )
        parent["children"].append(bullet)
    return sections


def require_row(db, table, row_id):
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Not found")
    return row


def validate_text(value, limit):
    value = value.strip()
    if not 1 <= len(value) <= limit:
        raise HTTPException(422, f"Text must contain 1–{limit} characters.")
    return value


def get_header():
    with database() as db:
        return dict(
            db.execute(
                "SELECT name, address, email, phone FROM header WHERE id = 1"
            ).fetchone()
        )


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"sections": get_sections(), "header": get_header()},
    )


@app.get("/api/resume")
def get_resume():
    return {"header": get_header(), "sections": get_sections()}


@app.get("/export.pdf")
def export_pdf():
    html = templates.env.get_template("pdf.html").render(
        sections=get_sections(),
        header=get_header(),
        stylesheet=(BASE / "static" / "style.css").read_text(),
    )
    pdf = render_pdf(html)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="resume.pdf"'},
    )


@app.post("/header/{field}/edit")
async def edit_header(field: str, request: Request):
    if field not in {"name", "address", "email", "phone"}:
        raise HTTPException(404, "Unknown header field.")
    form = await request.form()
    value = form.get(field, "")
    if not isinstance(value, str) or len(value.strip()) > 5000:
        raise HTTPException(422, "Header text must contain at most 5000 characters.")
    with database() as db:
        db.execute(f"UPDATE header SET {field} = ? WHERE id = 1", (value.strip(),))
    return {"saved": True}


@app.post("/sections")
def add_section(request: Request, title: str = Form(...)):
    with database() as db:
        cursor = db.execute(
            """
            INSERT INTO sections(title, position)
            VALUES (?, (SELECT COALESCE(MAX(position), -1) + 1 FROM sections))
            """,
            (validate_text(title, 200),),
        )
        section = dict(require_row(db, "sections", cursor.lastrowid), children=[])
    if request.headers.get("X-Inline-Create") == "true":
        return templates.TemplateResponse(
            request=request, name="_section.html", context={"section": section}
        )
    return RedirectResponse("/", status_code=303)


@app.post("/sections/{section_id}/edit")
def edit_section(section_id: int, title: str = Form(...)):
    with database() as db:
        require_row(db, "sections", section_id)
        db.execute(
            "UPDATE sections SET title = ? WHERE id = ?",
            (validate_text(title, 200), section_id),
        )
    return {"saved": True}


@app.post("/sections/{section_id}/delete")
def delete_section(section_id: int):
    with database() as db:
        require_row(db, "sections", section_id)
        db.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    return {"saved": True}


@app.post("/sections/{section_id}/move")
def move_section(section_id: int, position: int = Form(...)):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        require_row(db, "sections", section_id)
        siblings = [
            row["id"]
            for row in db.execute(
                "SELECT id FROM sections WHERE id != ? ORDER BY position, id",
                (section_id,),
            )
        ]
        if not 0 <= position <= len(siblings):
            raise HTTPException(422, "Position is outside the section list.")
        siblings.insert(position, section_id)
        db.executemany(
            "UPDATE sections SET position = ? WHERE id = ?", enumerate(siblings)
        )
    return {"saved": True}


@app.post("/sections/{section_id}/bullets")
def add_bullet(
    section_id: int,
    request: Request,
    content: str = Form(...),
    parent_id: int | None = Form(None),
):
    with database() as db:
        require_row(db, "sections", section_id)
        if parent_id is not None:
            parent = require_row(db, "bullets", parent_id)
            if parent["section_id"] != section_id:
                raise HTTPException(422, "Parent must belong to the same section.")
        position = db.execute(
            """
            SELECT COALESCE(MAX(position), -1) + 1 FROM bullets
            WHERE section_id = ? AND parent_id IS ?
            """,
            (section_id, parent_id),
        ).fetchone()[0]
        cursor = db.execute(
            "INSERT INTO bullets(section_id, parent_id, content, position) VALUES (?, ?, ?, ?)",
            (section_id, parent_id, validate_text(content, 5000), position),
        )
        bullet = dict(require_row(db, "bullets", cursor.lastrowid), children=[])
    if request.headers.get("X-Inline-Create") == "true":
        return templates.TemplateResponse(
            request=request,
            name="_bullet.html",
            context={"bullet": bullet, "section_id": section_id},
        )
    return RedirectResponse("/", status_code=303)


@app.post("/bullets/{bullet_id}/edit")
def edit_bullet(bullet_id: int, content: str = Form(...)):
    with database() as db:
        require_row(db, "bullets", bullet_id)
        db.execute(
            "UPDATE bullets SET content = ? WHERE id = ?",
            (validate_text(content, 5000), bullet_id),
        )
    return {"saved": True}


@app.post("/bullets/{bullet_id}/delete")
def delete_bullet(bullet_id: int):
    with database() as db:
        require_row(db, "bullets", bullet_id)
        db.execute("DELETE FROM bullets WHERE id = ?", (bullet_id,))
    return {"saved": True}


@app.post("/bullets/{bullet_id}/move")
def move_bullet(
    bullet_id: int,
    section_id: int = Form(...),
    parent_id: int | None = Form(None),
    position: int = Form(...),
):
    if position < 0:
        raise HTTPException(422, "Position must be nonnegative.")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        bullet = require_row(db, "bullets", bullet_id)
        require_row(db, "sections", section_id)
        descendants = [
            row["id"]
            for row in db.execute(
                """
            WITH RECURSIVE subtree(id) AS (
                SELECT id FROM bullets WHERE id = ?
                UNION ALL SELECT bullets.id FROM bullets JOIN subtree ON bullets.parent_id = subtree.id
            ) SELECT id FROM subtree
        """,
                (bullet_id,),
            )
        ]
        if parent_id is not None:
            parent = require_row(db, "bullets", parent_id)
            if parent_id in descendants:
                raise HTTPException(
                    422, "A bullet cannot be moved into itself or its descendants."
                )
            if parent["section_id"] != section_id:
                raise HTTPException(
                    422, "Parent must belong to the destination section."
                )
        siblings = [
            row["id"]
            for row in db.execute(
                "SELECT id FROM bullets WHERE section_id = ? AND parent_id IS ? AND id != ? ORDER BY position, id",
                (section_id, parent_id, bullet_id),
            )
        ]
        if position > len(siblings):
            raise HTTPException(422, "Position is outside the destination list.")
        # Defer composite foreign keys while relocating the whole subtree.
        db.execute("PRAGMA defer_foreign_keys = ON")
        db.executemany(
            "UPDATE bullets SET section_id = ? WHERE id = ?",
            [(section_id, descendant) for descendant in descendants],
        )
        db.execute(
            "UPDATE bullets SET parent_id = ? WHERE id = ?", (parent_id, bullet_id)
        )
        old_siblings = [
            row["id"]
            for row in db.execute(
                "SELECT id FROM bullets WHERE section_id = ? AND parent_id IS ? ORDER BY position, id",
                (bullet["section_id"], bullet["parent_id"]),
            )
        ]
        db.executemany(
            "UPDATE bullets SET position = ? WHERE id = ?", enumerate(old_siblings)
        )
        siblings.insert(position, bullet_id)
        db.executemany(
            "UPDATE bullets SET position = ? WHERE id = ?", enumerate(siblings)
        )
    return {"saved": True}
