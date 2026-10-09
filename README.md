# Resume editor

A single-resume starter using Python 3.10+, FastAPI, SQLite, server-rendered Jinja HTML, and HTMX. Add, edit, and delete sections, bullets, and nested subitems.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. SQLite is initialized automatically at `data/resume.sqlite3`; startup preserves saved data. Set `RESUME_DB` to override the database file. HTMX is loaded from a versioned CDN URL and requires internet access; forms also work through ordinary POST/redirect requests.

```bash
pytest
```

## Proposed schema

The implemented DDL is in `app/schema.sql`.

| Table | Columns | Purpose |
| --- | --- | --- |
| `sections` | `id`, `title`, `position` | Ordered resume sections |
| `items` | `id`, `section_id`, `parent_id`, `content`, `position` | Ordered bullets and subitems |

An item with `parent_id = NULL` is a top-level bullet. Other items reference their parent, allowing further nesting without extra tables. The composite foreign key `(parent_id, section_id)` ensures parent and child belong to the same section. Foreign keys are enabled on every connection; section and parent deletion cascade to descendants.

Positions describe insertion order within sections or sibling lists. Reads sort by `position, id`, with `id` breaking ties. Deletion leaves harmless position gaps. Reordering is a future extension; the UI currently appends new entries. The API never changes parents, preventing cycles through supported operations. A future reparenting endpoint must explicitly reject cycles; the schema alone only rejects self-parenting.

This is preferable to storing a whole section as JSON because individual bullets can be updated and deleted while SQLite enforces relationships. It assumes one resume. For multiple resumes, introduce `resumes` and a `resume_id` foreign key on `sections`.

## Routes

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/` | HTML editor |
| GET | `/api/resume` | Complete JSON tree with `children` arrays |
| POST | `/sections` | Create section (`title`) |
| POST | `/sections/{id}/edit` | Update title (`title`) |
| POST | `/sections/{id}/delete` | Delete section and its items |
| POST | `/sections/{id}/items` | Create bullet (`content`, optional `parent_id`) |
| POST | `/items/{id}/edit` | Update bullet (`content`) |
| POST | `/items/{id}/delete` | Delete bullet and its descendants |

Mutation routes accept form data, return the editor fragment for `HX-Request: true`, and otherwise redirect to `/`. Interactive API documentation is at `/docs`. SQL statements use bound parameters, and templates escape user text. Validation errors are shown by the HTMX editor.

The scaffold is intended for local use. Authentication, CSRF protection, schema migrations, and multi-user access are future work before public deployment. Whole-editor swaps keep this draft simple; each successful mutation closes open edit panels and clears unsaved forms elsewhere.

Implementation references: [FastAPI templates](https://fastapi.tiangolo.com/advanced/templates/), [HTMX targets](https://htmx.org/attributes/hx-target/), [HTMX swaps](https://htmx.org/attributes/hx-swap/).
