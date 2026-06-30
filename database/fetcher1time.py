"""
Pulls the crawlfeeds/IKEA-Home-Decor-Furniture-Dataset directly from
ugging Face's datasets-server API, via the /rows endpoint, paginated. hence no file download involved

Dataset: https://huggingface.co/datasets/crawlfeeds/IKEA-Home-Decor-Furniture-Dataset
Source/attribution: Crawlfeeds.

***This is intended as a one-time pull***
"""

import json
import os
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://datasets-server.huggingface.co/rows"
DATASET = "crawlfeeds/IKEA-Home-Decor-Furniture-Dataset"
CONFIG = "default"
SPLIT = "train"
PAGE_SIZE = 100  # API max per request

CACHE_FILE = Path(__file__).resolve().parent / "fetcher1time_cache.json"

HF_TOKEN = os.getenv("HF_TOKEN")
HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}

REQUEST_TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2


def fetch_page(offset: int, length: int = PAGE_SIZE) -> dict:
    """Fetches one page of rows. Retries on transient failures since
    this hits a third-party service we don't control."""
    params = {
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "offset": offset,
        "length": length,
    }
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = requests.get(
                API_BASE,
                params=params,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            last_error = e
            print(f"  [fetch failed, attempt {attempt}/{RETRY_ATTEMPTS}: {e}]")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"Failed to fetch offset={offset} after {RETRY_ATTEMPTS} attempts") from last_error


def fetch_all_rows(force_refresh: bool = False) -> list[dict]:
    """
    Pages through the entire dataset and returns a flat list of row
    dicts (the actual product records, unwrapped from the API's
    {"row_idx": ..., "row": {...}} envelope).

    If a local cache exists, reuse it unless force_refresh is True.
    """
    if not force_refresh and CACHE_FILE.exists():
        try:
            with CACHE_FILE.open("r", encoding="utf-8") as f:
                rows = json.load(f)
            print(f"Loading cached dataset rows from {CACHE_FILE}")
            return rows
        except (OSError, json.JSONDecodeError) as e:
            print(f"  [warning] failed to read cache {CACHE_FILE}: {e}. Refetching from Hugging Face.")

    all_rows: list[dict] = []
    offset = 0

    while True:
        page = fetch_page(offset)
        rows = page.get("rows", [])
        if not rows:
            break

        all_rows.extend(r["row"] for r in rows)

        total = page.get("num_rows_total", "?")
        print(f"  fetched {len(all_rows)} / {total} rows")

        offset += PAGE_SIZE
        if offset >= page.get("num_rows_total", offset):
            break

        # polite API citizen
        time.sleep(0.3)

    try:
        with CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(all_rows, f, ensure_ascii=False)
        print(f"Saved fetched dataset rows to cache at {CACHE_FILE}")
    except OSError as e:
        print(f"  [warning] failed to write cache {CACHE_FILE}: {e}")

    return all_rows


if __name__ == "__main__":
    rows = fetch_all_rows()
    print(f"\nTotal rows fetched: {len(rows)}")
    #testing
    if rows:
        print("Sample row keys:", list(rows[0].keys()))
        print("Sample product_name:", rows[0].get("product_name"))
