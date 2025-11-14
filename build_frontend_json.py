#!/usr/bin/env python3
"""
build_frontend_json.py

Read the raw JSONL scraped data (check_p.jsonl) and build a clean
products.json file for the frontend.

- De-duplicates products by item_id (or product_name as fallback)
- Merges multiple search_query values into a list search_queries
- Keeps the other fields as-is
"""

from __future__ import annotations
import json
from pathlib import Path


INPUT_JSONL = Path("product_info.jsonl")
OUTPUT_JSON = Path("products.json")


def load_jsonl(path: Path):
    """Yield JSON objects from a .jsonl file, skipping empty/bad lines."""
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[WARN] Skipping bad JSON on line {line_num}: {e}")


def build_products():
    """
    Build a dict of products keyed by item_id (fallback: product_name).
    If the same product appears multiple times under different queries,
    we merge the search_query into a list search_queries.
    """
    products_by_key = {}

    for obj in load_jsonl(INPUT_JSONL):
        item_id = obj.get("item_id")
        name = obj.get("product_name") or obj.get("name")

        if not item_id and not name:
            continue

        key = item_id or name

        # Pull out the search query used to find this product
        q = obj.pop("search_query", None)

        if key not in products_by_key:
            # First time we see this product
            if q:
                obj["search_queries"] = [q]
            else:
                obj["search_queries"] = []
            products_by_key[key] = obj
        else:
            # Merge with existing record
            existing = products_by_key[key]

            # Merge search queries into a unique list
            if q:
                existing_queries = set(existing.get("search_queries") or [])
                existing_queries.add(q)
                existing["search_queries"] = sorted(existing_queries)

    return list(products_by_key.values())


def main():
    if not INPUT_JSONL.exists():
        raise SystemExit(f"Input file not found: {INPUT_JSONL}")

    print(f"Reading from {INPUT_JSONL} ...")
    products = build_products()
    print(f"Built {len(products)} unique products")

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    # Wrap in {"items": [...]} so the frontend can do data.items
    payload = {"items": products}

    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(products)} products to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
