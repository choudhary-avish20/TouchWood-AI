"""
Retrieval layer for the decor catalog.

Two-stage retrieval over catalog.db:
  1. Structured filtering (SQL) — hard constraints: category, price range,
     dimension limits, in-stock/active. Cheap, exact, no model calls.
  2. Embedding similarity (numpy) — ranks the filtered shortlist against
     the user's theme/style query using the same all-MiniLM-L6-v2 model
     and embedding-text convention used at index time in embeddings.py.

Usage:
    from retrieval import RetrievalQuery, retrieve

    query = RetrievalQuery(
        categories=["Vases", "Lighting"],
        max_price=2000,
        style_text="cozy, warm, a bit rustic",
        style_tags=["rustic", "scandinavian"],
        max_width_cm=40,
    )
    results = retrieve(query, top_k=8)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import numpy as np

from database.db_schema import get_connection
from database.embeddings import build_embedding_text, embed_text, embedding_from_bytes

DB_PATH = "data/catalog.db"


@dataclass
class RetrievalQuery:
    """Mirrors the fields in the room-state object built by the
    extraction layer. All fields optional — only supply what the user
    actually gave ; absent fields simply skip that filter.
    """

    categories: list[str] | None = None        # hard filter: category IN (...)
    min_price: float | None = None
    max_price: float | None = None
    max_width_cm: float | None = None
    max_height_cm: float | None = None
    max_depth_cm: float | None = None
    max_diameter_cm: float | None = None
    style_tags: list[str] = field(default_factory=list)   # soft signal, fed into embedding text
    style_text: str | None = None                          # free-form theme description, e.g. "cozy, warm, rustic"
    exclude_ids: list[int] = field(default_factory=list)   # e.g. items already recommended this session


@dataclass
class RetrievedItem:
    id: int
    name: str
    category: str
    retailer: str
    price: float | None
    currency: str
    width_cm: float | None
    height_cm: float | None
    depth_cm: float | None
    diameter_cm: float | None
    description: str | None
    style_tags: list[str]
    image_url: str | None
    source_url: str
    score: float  # cosine similarity to the query, 0 if no style query given


_SELECT_COLUMNS = """
    id, name, category, retailer, price, currency,
    width_cm, height_cm, depth_cm, diameter_cm,
    description, style_tags, image_url, source_url, embedding
"""


def _build_filter_sql(query: RetrievalQuery) -> tuple[str, list]:
    """Builds the WHERE clause + params for the structured-filter stage."""
    clauses = ["is_active = 1", "in_stock = 1"]
    params: list = []

    if query.categories:
        placeholders = ",".join("?" for _ in query.categories)
        clauses.append(f"category IN ({placeholders})")
        params.extend(query.categories)

    if query.min_price is not None:
        clauses.append("(price IS NULL OR price >= ?)")
        params.append(query.min_price)

    if query.max_price is not None:
        clauses.append("(price IS NULL OR price <= ?)")
        params.append(query.max_price)

    # Dimension limits: NULL dimensions are treated as "fits" rather than
    # excluded, since a lot of catalog rows are missing one or more of
    # these (e.g. a vase has diameter but no width/depth) and we don't
    # want to drop otherwise-valid items over missing metadata.
    if query.max_width_cm is not None:
        clauses.append("(width_cm IS NULL OR width_cm <= ?)")
        params.append(query.max_width_cm)

    if query.max_height_cm is not None:
        clauses.append("(height_cm IS NULL OR height_cm <= ?)")
        params.append(query.max_height_cm)

    if query.max_depth_cm is not None:
        clauses.append("(depth_cm IS NULL OR depth_cm <= ?)")
        params.append(query.max_depth_cm)

    if query.max_diameter_cm is not None:
        clauses.append("(diameter_cm IS NULL OR diameter_cm <= ?)")
        params.append(query.max_diameter_cm)

    if query.exclude_ids:
        placeholders = ",".join("?" for _ in query.exclude_ids)
        clauses.append(f"id NOT IN ({placeholders})")
        params.extend(query.exclude_ids)

    where_sql = " AND ".join(clauses)
    return where_sql, params


def _row_to_item(row: sqlite3.Row, score: float) -> RetrievedItem:
    import json

    raw_tags = row["style_tags"]
    try:
        tags = json.loads(raw_tags) if raw_tags else []
    except (json.JSONDecodeError, TypeError):
        tags = []

    return RetrievedItem(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        retailer=row["retailer"],
        price=row["price"],
        currency=row["currency"],
        width_cm=row["width_cm"],
        height_cm=row["height_cm"],
        depth_cm=row["depth_cm"],
        diameter_cm=row["diameter_cm"],
        description=row["description"],
        style_tags=tags,
        image_url=row["image_url"],
        source_url=row["source_url"],
        score=score,
    )


def retrieve(
    query: RetrievalQuery,
    top_k: int = 8,
    db_path: str = DB_PATH,
    conn: sqlite3.Connection | None = None,
) -> list[RetrievedItem]:
    """
    Runs the two-stage retrieval and returns up to `top_k` items, ranked
    by semantic similarity when a style query is given, or by price
    (ascending, nulls last) when there's no style signal to rank on.
    """
    owns_conn = conn is None
    if conn is None:
        conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row

    where_sql, params = _build_filter_sql(query)
    sql = f"SELECT {_SELECT_COLUMNS} FROM decor_items WHERE {where_sql}"
    rows = conn.execute(sql, params).fetchall()

    if owns_conn:
        conn.close()

    if not rows:
        return []

    has_style_query = bool(query.style_text or query.style_tags)

    if not has_style_query:
        # No semantic signal to rank on — fall back to price ascending,
        # treating NULL price as "rank last" rather than first.
        ranked = sorted(
            rows,
            key=lambda r: (r["price"] is None, r["price"] if r["price"] is not None else 0),
        )
        return [_row_to_item(r, score=0.0) for r in ranked[:top_k]]

    # Embedding similarity stage. Build the query text the same way
    # items were embedded (style tags stated plainly + free text), so
    # the query lands in the same semantic neighborhood as catalog text.
    query_text = build_embedding_text(query.style_text, query.style_tags)
    query_vec = embedding_from_bytes(embed_text(query_text))

    candidate_rows = [r for r in rows if r["embedding"] is not None]
    skipped = [r for r in rows if r["embedding"] is None]  # no embedding yet — push to the end

    if candidate_rows:
        matrix = np.stack([embedding_from_bytes(r["embedding"]) for r in candidate_rows])
        # Embeddings are stored pre-normalized (see embeddings.py), so
        # cosine similarity reduces to a plain dot product.
        scores = matrix @ query_vec
        order = np.argsort(-scores)
        ranked = [(candidate_rows[i], float(scores[i])) for i in order]
    else:
        ranked = []

    ranked.extend((r, 0.0) for r in skipped)

    return [_row_to_item(r, score) for r, score in ranked[:top_k]]


if __name__ == "__main__":
    q = RetrievalQuery(
        categories=["Vases"],
        max_price=2000,
        style_text="cozy, warm, a bit rustic",
        style_tags=["rustic", "scandinavian"],
    )
    results = retrieve(q, top_k=5)
    for item in results:
        print(f"{item.score:.3f}  {item.name}  ({item.category}, {item.price} {item.currency})")