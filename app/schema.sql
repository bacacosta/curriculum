CREATE TABLE IF NOT EXISTS header (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT ''
);
INSERT OR IGNORE INTO header (id) VALUES (1);
CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
    position INTEGER NOT NULL CHECK (position >= 0)
);
CREATE TABLE IF NOT EXISTS bullets (
    id INTEGER PRIMARY KEY,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    parent_id INTEGER,
    content TEXT NOT NULL CHECK (length(trim(content)) BETWEEN 1 AND 5000),
    position INTEGER NOT NULL CHECK (position >= 0),
    UNIQUE (id, section_id),
    CHECK (parent_id IS NULL OR parent_id != id),
    FOREIGN KEY (parent_id, section_id) REFERENCES bullets(id, section_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS bullets_siblings ON bullets(section_id, parent_id, position, id);
CREATE INDEX IF NOT EXISTS sections_order ON sections(position, id);
