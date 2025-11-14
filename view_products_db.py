#!/usr/bin/env python3
"""
view_products_db.py

Simple helper to inspect the products.db SQLite database that we
populate from jsonl_to_sqlite.py.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("products.db")


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database file not found: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # How many rows do we have?
    cur.execute("SELECT COUNT(*) AS n FROM product_prices")
    row = cur.fetchone()
    total = row["n"] if row is not None else 0
    print(f"Total rows in product_prices: {total}")

    if total == 0:
        print("No data yet — did you run jsonl_to_sqlite.py?")
        conn.close()
        return

    # Show the last 10 inserted rows (by primary key id)
    print("\nLast 10 rows (newest first):")
    cur.execute(
        """
        SELECT
            id,
            scraped_at,
            item_id,
            product_name,
            brand,
            price,
            availability,
            review_count,
            avg_rating,
            image_url
        FROM product_prices
        ORDER BY id DESC
        LIMIT 10
        """
    )

    for i, r in enumerate(cur.fetchall(), start=1):
        print(f"\nRow {i}:")
        print(f"  id           = {r['id']}")
        print(f"  scraped_at   = {r['scraped_at']}")
        print(f"  item_id      = {r['item_id']}")
        print(f"  product_name = {r['product_name']}")
        print(f"  brand        = {r['brand']}")
        print(f"  price        = {r['price']}")
        print(f"  availability = {r['availability']}")
        print(f"  review_count = {r['review_count']}")
        print(f"  avg_rating   = {r['avg_rating']}")
        print(f"  image_url    = {r['image_url']}")

    conn.close()


if __name__ == "__main__":
    main()
