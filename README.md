# Resume editor

A single-resume editor using Python 3.10+, FastAPI, SQLite, Jinja templates, and vanilla JavaScript. Edit contact details, sections, bullets, and nested sub-bullets, then download a styled A4 PDF.

## Run

```bash
./start.sh
```

The script creates `.venv`, installs missing runtime dependencies, and starts the development server on `0.0.0.0:8000` with automatic reload. Open http://127.0.0.1:8000. Stop with Ctrl+C; pass server options such as `./start.sh --port 8080`.

PDF export requires a recent Google Chrome installation on the server, discoverable through Playwright's `chrome` channel. Installing the Python dependencies does not install Chrome. Chrome 131 or newer supports the CSS page-number footer. Export uses the server's installed fonts, with Adwaita Sans, Helvetica Neue, Segoe UI, and sans-serif fallbacks; different machines may render different fallback fonts.

For manual setup, including tests:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --reload
```

SQLite initializes at `data/resume.sqlite3` and preserves saved data. Set `RESUME_DB` to override its location.

## Editing and export

The header contains `name`, `address`, `email`, and `phone`. The name sits on the left, followed by the address and a column containing email above phone. Header fields can be cleared.

Click any header field, section title, or bullet to edit. Leaving the field or pressing Enter saves; Shift+Enter inserts a line break and Escape cancels unsaved typing. Section titles appear on the left with their controls underneath, and bullets on the right, inside light gray section backgrounds.

The centered plus button adds a section. A section's plus adds a top-level bullet; a bullet's plus adds a nested sub-bullet. Empty new fields or Escape cancel creation before saving starts. Once a new entry is saving, it stays visible until the request finishes; use its trash button afterward to delete it. Trash buttons ask for confirmation and delete the selected section or bullet together with its descendants.

Drag a bullet's ⠿ handle to reorder or move its subtree. Drop at the top/bottom of a row to insert before/after, in the middle to nest, or on a section heading to append at its top level. With the handle focused, Up/Down reorder, Right nests under the previous sibling, and Left moves out one level. Section handles support dragging and Up/Down reordering. Moves save automatically.

The PDF icon on the bottom right downloads `resume.pdf` directly. It waits for pending text saves, moves, and deletions, and temporarily locks editing during export. Invalid or failed text saves block export, as do pending moves or deletions that fail while export is waiting. The PDF preserves the document layout and gray section backgrounds, hides editing controls, rulers, and the empty-resume prompt, and includes only page numbers in its footer. The globe beside PDF is a placeholder for future web export and has no action.

The editor requires JavaScript; it has no external script or CDN dependency. All requests use the browser's Fetch API.

## Schema

The implemented DDL is in `app/schema.sql`.

| Table | Columns | Purpose |
| --- | --- | --- |
| `header` | `id`, `name`, `address`, `email`, `phone` | One contact header (`id = 1`) |
| `sections` | `id`, `title`, `position` | Ordered resume sections |
| `bullets` | `id`, `section_id`, `parent_id`, `content`, `position` | Ordered bullets and nested sub-bullets |

A bullet with `parent_id = NULL` is top-level. Other bullets reference a parent. The composite foreign key `(parent_id, section_id)` keeps parent and child in the same section. Every connection enables foreign keys; section and parent deletion cascade to descendants.

Reads sort by `position, id`. Deletion may leave harmless gaps; new entries append. Moves normalize sibling positions in one transaction, reject self-parenting and descendant cycles, and update the entire subtree when moving between sections.

This app stores one resume. Multiple resumes would require a `resumes` table and resume ownership for both headers and sections. Existing databases using older table names require an explicit migration; startup only initializes the current schema.

## Routes

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/` | HTML editor |
| GET | `/api/resume` | Header and section tree with `children` arrays |
| GET | `/export.pdf` | Styled A4 PDF attachment |
| POST | `/header/{field}/edit` | Save `name`, `address`, `email`, or `phone`; accepts empty text |
| POST | `/sections` | Create section (`title`) |
| POST | `/sections/{section_id}/edit` | Save section title (`title`) |
| POST | `/sections/{section_id}/delete` | Delete section and its bullets |
| POST | `/sections/{section_id}/move` | Reorder (`position`, destination index excluding moved section) |
| POST | `/sections/{section_id}/bullets` | Create bullet (`content`, optional `parent_id`) |
| POST | `/bullets/{bullet_id}/edit` | Save bullet (`content`) |
| POST | `/bullets/{bullet_id}/delete` | Delete bullet and descendants |
| POST | `/bullets/{bullet_id}/move` | Move subtree (`section_id`, optional `parent_id`, destination `position` excluding moved bullet) |

Mutation routes accept form data. Edits, deletes, and moves return JSON confirmation. Creation with `X-Inline-Create: true` returns a section or bullet HTML fragment; other creation requests redirect to `/`. Positions are zero-based. Interactive API documentation is at `/docs`. Templates escape user text and SQL values use bound parameters.

## Tests

```bash
python -m pytest -q
```

Tests cover persistence, validation, escaping, nested bullets, reordering, invalid moves, PDF download metadata, PDF text and pagination, empty exports, browser export synchronization, recovery from failed text saves, empty-state updates after deleting or cancelling sections, and cancellation during in-flight creation. PDF and browser tests require Chrome and permission to launch browser processes. Tests use temporary databases and do not modify the saved resume.

The app is intended for local use. Authentication, CSRF protection, migrations, and multi-user access remain future work before public deployment.

PDF rendering is isolated in `app/pdf.py`; the `/export.pdf` route renders the template and returns the generated bytes as a download.
