"""
Database schema setup for the decor product catalog.

Run this once to create catalog.db, or call ensure_schema(conn) from
the ingestion script to make sure the table exists before inserting.
"""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS decor_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- core identity
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,        -- maps to category_3 (specific), e.g. 'Vases'
    category_broad  TEXT,                  -- maps to category_2 (grouping), e.g. 'Vases & bowls'
    retailer        TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    image_url       TEXT,

    -- structured filter fields (hard constraints)
    price           REAL,
    currency        TEXT DEFAULT 'INR',    -- dataset is INR-only (IKEA India)
    width_cm        REAL,
    height_cm       REAL,
    depth_cm        REAL,                  -- maps to source's "Length"
    diameter_cm     REAL,                  -- many items report diameter, not width/depth
    color           TEXT,                  -- primary color, simplified

    -- semantic fields (what gets embedded)
    description     TEXT,                  -- raw product description
    material        TEXT,                  -- from material_and_care, cleaned
    style_tags      TEXT,                  -- JSON array as text: '["minimalist","mid-century"]'

    -- embedding cache (computed once at index time)
    embedding       BLOB,                  -- serialized vector, e.g. float32 numpy array
    embedding_source_hash TEXT,            -- hash of text that produced `embedding`;
                                            -- lets refresh runs skip re-embedding unchanged items

    -- freshness / lifecycle
    in_stock        INTEGER DEFAULT 1,     -- boolean as 0/1
    last_seen_at    TEXT NOT NULL,         -- ISO timestamp, updated every refresh run
    first_seen_at   TEXT NOT NULL,
    is_active       INTEGER DEFAULT 1      -- soft-delete flag, see refresh logic below
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_source_url ON decor_items(source_url);
CREATE INDEX IF NOT EXISTS idx_category ON decor_items(category);
CREATE INDEX IF NOT EXISTS idx_price ON decor_items(price);
CREATE INDEX IF NOT EXISTS idx_active ON decor_items(is_active);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def get_connection(db_path: str = "catalog.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout= 30.0)
    ensure_schema(conn)
    return conn


if __name__ == "__main__":
    conn = get_connection("catalog.db")
    print("Schema ready at catalog.db")
    conn.close()
