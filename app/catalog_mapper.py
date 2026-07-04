"""
Searching the catalog for the keywords from the prompt
if 
"""

from __future__ import annotations

import re
import sqlite3

from config import DB_PATH

# ---------------------------------------------------------------------------
# Category list — loaded once at startup via load_categories()
# ---------------------------------------------------------------------------
_catalog_categories: list[str] = []


def load_categories(db_path: str = DB_PATH) -> None:
    """Call once at app startup to populate the category list from the DB."""
    global _catalog_categories
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT DISTINCT category FROM decor_items WHERE category IS NOT NULL"
        ).fetchall()
        conn.close()
        _catalog_categories = [r[0] for r in rows if r[0]]
    except Exception as e:
        print(f"[category_mapper] Could not load categories: {e}")
        _catalog_categories = []


def _tokenise(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


# hardcoded categories
_KEYWORD_HINTS: dict[str, list[str]] = {
    "rug":       ["Rugs", "Carpets"],
    "carpet":    ["Rugs", "Carpets"],
    "lamp":      ["Lighting", "Table Lamps", "Floor Lamps"],
    "light":     ["Lighting"],
    "lighting":  ["Lighting"],
    "vase":      ["Vases"],
    "cushion":   ["Cushions", "Pillows"],
    "pillow":    ["Cushions", "Pillows"],
    "mirror":    ["Mirrors", "Wall Decor"],
    "art":       ["Wall Art", "Wall Decor"],
    "plant":     ["Plants", "Planters"],
    "planter":   ["Planters", "Plants"],
    "candle":    ["Candles", "Candle Holders"],
    "clock":     ["Clocks", "Wall Decor"],
    "shelf":     ["Shelves", "Storage"],
    "throw":     ["Throws", "Blankets"],
    "blanket":   ["Throws", "Blankets"],
    "curtain":   ["Curtains", "Window Treatments"],
    "frame":     ["Picture Frames", "Wall Decor"],
}


def map_to_categories(raw_phrase: str, max_matches: int = 2) -> list[str]:
    """
    Resolution order:
    1. Keyword hints — first method
    2. Token overlap - entire catalog is searched, if hints fail :(
    """
    if not raw_phrase:
        return []

    tokens = _tokenise(raw_phrase)

    # hints
    hint_matches: list[str] = []
    for keyword, categories in _KEYWORD_HINTS.items():
        if keyword in tokens:
            for cat in categories:
                if cat in _catalog_categories and cat not in hint_matches:
                    hint_matches.append(cat)
    if hint_matches:
        return hint_matches[:max_matches]

    # backup: Token overlap
    if not _catalog_categories:
        return []

    scored: list[tuple[float, str]] = []
    for cat in _catalog_categories:
        cat_tokens = _tokenise(cat)
        if not cat_tokens:
            continue
        overlap = len(tokens & cat_tokens) / len(tokens | cat_tokens)
        if overlap > 0:
            scored.append((overlap, cat))

    scored.sort(reverse=True)
    return [cat for _, cat in scored[:max_matches]]