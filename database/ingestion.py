"""
Main ingestion script for the decor product catalog.

Pulls data directly from the Hugging Face datasets-server API (no file
download — see fetch_dataset.py) and ingests it into catalog.db.

Usage:
    python ingest_catalog.py

Source: crawlfeeds/IKEA-Home-Decor-Furniture-Dataset (Hugging Face),
licensed CC-BY-NC-4.0. Attribution: Crawlfeeds.

What this does, per row:
    1. Parse the messy `measurements` string into width/height/depth/diameter
    2. Build a clean description from summary + features (strip MRP noise)
    3. Generate style tags via local Ollama model (skipped if unchanged
        from a previous run, to avoid re-tagging on every refresh)
    4. Generate/refresh the embedding (skipped if source text unchanged)
    5. Upsert into decor_items, keyed on product_url
    6. After all rows: deactivate any catalog item not touched this run
        (soft delete — keeps history instead of destroying rows)
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone

from db_schema import get_connection
from dimensions import parse_measurements
from tagger import generate_style_tags
from embeddings import build_embedding_text, embed_text, text_hash
from fetcher1time import fetch_all_rows

DB_PATH = "catalog.db"


def clean_description(summary: str, features: str) -> str:
    """
    Builds a clean description from the dataset's `summary` and `features`
    fields. `features` in the source data is itself pipe-delimited
    (e.g. "MRP Rs.298 (incl. tax) | A comforting scent... | Suitable when...").
    We strip the MRP line (redundant with our price column) and join the rest.
    """
    parts = []
    if summary:
        parts.append(summary.strip())

    if features:
        feature_lines = [f.strip() for f in features.split("|")]
        feature_lines = [f for f in feature_lines if f and not f.lower().startswith("mrp")]
        parts.extend(feature_lines)

    return " ".join(parts).strip()


def upsert_item(cursor: sqlite3.Cursor, item: dict, now: str) -> None:
    cursor.execute("""
        INSERT INTO decor_items (
            name, category, category_broad, retailer, source_url, image_url,
            price, currency, width_cm, height_cm, depth_cm, diameter_cm, color,
            description, material, style_tags, embedding, embedding_source_hash,
            in_stock, last_seen_at, first_seen_at, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(source_url) DO UPDATE SET
            price = excluded.price,
            in_stock = excluded.in_stock,
            last_seen_at = excluded.last_seen_at,
            -- only overwrite enrichment fields if they were actually
            -- recomputed this run (non-null); otherwise keep existing
            style_tags = COALESCE(excluded.style_tags, decor_items.style_tags),
            embedding = COALESCE(excluded.embedding, decor_items.embedding),
            embedding_source_hash = COALESCE(excluded.embedding_source_hash, decor_items.embedding_source_hash),
            is_active = 1
    """, (
        item["name"], item["category"], item["category_broad"], item["retailer"],
        item["source_url"], item["image_url"], item["price"], item["currency"],
        item["width_cm"], item["height_cm"], item["depth_cm"], item["diameter_cm"],
        item["color"], item["description"], item["material"],
        item["style_tags"], item["embedding"], item["embedding_source_hash"],
        item["in_stock"], now, now,
    ))


def get_existing_hash(cursor: sqlite3.Cursor, source_url: str) -> str | None:
    """Checks if this item already has a stored embedding hash, so we can
    skip re-tagging/re-embedding when nothing relevant has changed."""
    row = cursor.execute(
        "SELECT embedding_source_hash FROM decor_items WHERE source_url = ?",
        (source_url,),
    ).fetchone()
    return row[0] if row else None


def process_row(cursor: sqlite3.Cursor, row: dict) -> dict:
    dims = parse_measurements(row.get("measurements"))
    description = clean_description(row.get("summary", ""), row.get("features", ""))

    source_url = row["product_url"]
    existing_hash = get_existing_hash(cursor, source_url)

    # Decide whether enrichment (style tags + embedding) needs to (re)run.
    # We hash on name+description+material since that's what feeds both
    # the tagger and the embedder — if none of that changed, skip both
    # the Ollama call and the embedding call entirely.
    material = row.get("material_and_care", "")
    enrichment_source = f"{row['product_name']}|{description}|{material}"
    current_hash = text_hash(enrichment_source)

    style_tags = None
    embedding_bytes = None
    embedding_hash = None

    if current_hash != existing_hash:
        tags = generate_style_tags(row["product_name"], description, material)
        style_tags = json.dumps(tags)

        embedding_text = build_embedding_text(description, tags)
        embedding_bytes = embed_text(embedding_text)
        embedding_hash = current_hash
    # else: leave as None, COALESCE in the upsert keeps the existing values

    # The HF API returns price as a native int64 already — no string
    # parsing needed here, unlike the CSV path this replaces.
    price = row.get("price")
    price = float(price) if price is not None else None

    return {
        "name": row["product_name"],
        "category": row.get("category_3") or row.get("category_2") or "uncategorized",
        "category_broad": row.get("category_2"),
        "retailer": "IKEA",
        "source_url": source_url,
        "image_url": row.get("primary_image"),
        "price": price,
        "currency": row.get("currency", "INR"),
        "width_cm": dims.width_cm,
        "height_cm": dims.height_cm,
        "depth_cm": dims.depth_cm,
        "diameter_cm": dims.diameter_cm,
        "color": None,  # not a clean separate field in source; could be
                        # parsed from product_name suffix later if needed
        "description": description,
        "material": material,
        "style_tags": style_tags,
        "embedding": embedding_bytes,
        "embedding_source_hash": embedding_hash,
        "in_stock": 1,
    }


def deactivate_stale_items(cursor: sqlite3.Cursor, run_started_at: str) -> int:
    cursor.execute("""
        UPDATE decor_items
        SET is_active = 0
        WHERE last_seen_at < ? AND is_active = 1
    """, (run_started_at,))
    return cursor.rowcount


def ingest(force_refresh: bool = False) -> None:
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()

    run_started_at = datetime.now(timezone.utc).isoformat()
    processed = 0
    skipped = 0

    print("Loading dataset rows...")
    rows = fetch_all_rows(force_refresh=force_refresh)
    source = "Hugging Face" if force_refresh or not rows else "cache"
    print(f"Loaded {len(rows)} rows from {source}. Starting ingestion...\n")

    for row in rows:
        try:
            item = process_row(cursor, row)
            upsert_item(cursor, item, datetime.now(timezone.utc).isoformat())
            processed += 1
            if processed % 25 == 0:
                conn.commit()  # periodic commit so a crash mid-run
                                # doesn't lose all progress
                print(f"  ...{processed} items processed")
        except Exception as e:
            skipped += 1
            print(f"  [skipped row, error: {e}] -> {row.get('product_name', '?')}")

    conn.commit()
    deactivated = deactivate_stale_items(cursor, run_started_at)
    conn.commit()

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Deactivated: {deactivated}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest decor catalog rows into SQLite.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force refetching dataset rows from Hugging Face and update the local cache.",
    )
    args = parser.parse_args()
    ingest(force_refresh=args.refresh)
