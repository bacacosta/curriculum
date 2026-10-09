# Resume editor

A single-resume starter using Python 3.10+, FastAPI, SQLite, server-rendered Jinja HTML, and HTMX. Add, edit, and delete sections, bullets, and nested subitems.

## Run

Start the app without activating the virtual environment:

```bash
./start.sh
```

The script creates `.venv` and installs runtime dependencies if needed, then starts the development server with automatic reload. Stop it with Ctrl+C. Pass server options as needed, for example `./start.sh --port 8080`.

For manual setup (including test dependencies):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. SQLite is initialized automatically at `data/resume.sqlite3`; startup preserves saved data. Set `RESUME_DB` to override the database file. Click a section title or bullet to edit it directly; leaving the text saves automatically. Enter saves and leaves any editing field, Shift+Enter inserts a line break, and Escape cancels unsaved typing. Every bullet and subitem has a trash button and a plus button. Plus opens a new subitem field that saves on blur; leaving it empty or pressing Escape cancels it. The single plus button at the bottom opens a blank section title; Enter or leaving the field saves it, and an empty title or Escape cancels it. Section titles also have plus and trash buttons for adding top-level bullets and deleting the entire section. Every trash button asks for confirmation before deleting. Inline editing requires JavaScript. HTMX is loaded from a versioned CDN URL and requires internet access; add/delete forms also work through ordinary POST/redirect requests.

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

Positions describe insertion order within sections or sibling lists. Reads sort by `position, id`, with `id` breaking ties. Deletion leaves harmless position gaps. New entries append to their sibling list. Drag the ⠿ handle to reorder or move a bullet with all its descendants. Drop on the top/bottom of a row to insert before/after it, the middle to nest under it, or a section heading to append at that section’s top level. With the handle focused, Up/Down reorder, Right nests under the previous sibling, and Left moves out one level. Moves save automatically. Sections also have a ⠿ handle: drag above or below another section to reorder, or focus the handle and press Up/Down. The section and all its bullets move together. The move endpoint rejects self-parenting and descendant cycles, updates the entire subtree when moving between sections, and normalizes sibling positions in one transaction.

This is preferable to storing a whole section as JSON because individual bullets can be updated and deleted while SQLite enforces relationships. It assumes one resume. For multiple resumes, introduce `resumes` and a `resume_id` foreign key on `sections`.

## Routes

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/` | HTML editor |
| GET | `/api/resume` | Complete JSON tree with `children` arrays |
| POST | `/sections` | Create section (`title`) |
| POST | `/sections/{id}/edit` | Update title (`title`) |
| POST | `/sections/{id}/delete` | Delete section and its items |
| POST | `/sections/{id}/move` | Reorder section (`position`, zero-based destination index excluding the moved section) |
| POST | `/sections/{id}/items` | Create bullet (`content`, optional `parent_id`) |
| POST | `/items/{id}/edit` | Update bullet (`content`) |
| POST | `/items/{id}/delete` | Delete bullet and its descendants |
| POST | `/items/{id}/move` | Move subtree (`section_id`, optional `parent_id`, zero-based `position` among destination siblings excluding the moved item) |

Mutation routes accept form data. The move routes return JSON confirmation; creation with `X-Inline-Create: true` returns a single item fragment. Other mutations return the editor fragment for `HX-Request: true`, and otherwise redirect to `/`. Interactive API documentation is at `/docs`. SQL statements use bound parameters, and templates escape user text. Validation errors are shown by the HTMX editor.

The scaffold is intended for local use. Authentication, CSRF protection, schema migrations, and multi-user access are future work before public deployment. Inline edits, subitem creation, and item deletion update only the affected row. Section deletion removes only that section. Adding a section inserts its card without replacing the editor.

Implementation references: [FastAPI templates](https://fastapi.tiangolo.com/advanced/templates/), [HTMX targets](https://htmx.org/attributes/hx-target/), [HTMX swaps](https://htmx.org/attributes/hx-swap/).
