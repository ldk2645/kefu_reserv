from contextlib import contextmanager
from pathlib import Path
import sqlite3

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS products (
 id TEXT PRIMARY KEY, brand TEXT NOT NULL, name TEXT NOT NULL, model TEXT NOT NULL,
 sku TEXT NOT NULL UNIQUE, aliases TEXT NOT NULL DEFAULT '[]', category TEXT NOT NULL DEFAULT '',
 is_demo INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_sources (
 id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id), kind TEXT NOT NULL,
 title TEXT NOT NULL, path TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', provenance TEXT NOT NULL,
 sha256 TEXT NOT NULL, version TEXT NOT NULL DEFAULT '1', verified_status TEXT NOT NULL DEFAULT 'pending',
 is_demo INTEGER NOT NULL DEFAULT 0, imported_at TEXT NOT NULL, reviewed_at TEXT NOT NULL DEFAULT '',
 verified_by TEXT NOT NULL DEFAULT '', effective_at TEXT NOT NULL DEFAULT '', expires_at TEXT NOT NULL DEFAULT '',
 UNIQUE(product_id, sha256, kind, version)
);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES knowledge_sources(id),
 section TEXT NOT NULL, page INTEGER, content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS video_links (
 video_id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id), title TEXT NOT NULL,
 url TEXT NOT NULL, intent_tags TEXT NOT NULL, verified_status TEXT NOT NULL DEFAULT 'pending',
 official_source_name TEXT NOT NULL, official_source_url TEXT NOT NULL,
 customer_shareable INTEGER NOT NULL DEFAULT 0, is_demo INTEGER NOT NULL DEFAULT 0,
 link_status TEXT NOT NULL DEFAULT 'unknown', verified_by TEXT NOT NULL DEFAULT '',
 verified_at TEXT NOT NULL DEFAULT '', last_checked_at TEXT NOT NULL DEFAULT ''
);
PRAGMA user_version=1;
"""


class Database:
    """One connection per operation; safe for background imports and reads."""
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rows(self, query, parameters=()):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, parameters)]
