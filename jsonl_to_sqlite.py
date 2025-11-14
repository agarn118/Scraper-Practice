#!/usr/bin/env python3
"""
jsonl_to_sqlite.py

Read a .jsonl file containing scraped product data and append it to a
SQLite database, keeping historical data from previous runs.

Usage (from your project folder):

    python jsonl_to_sqlite.py --jsonl product_info.jsonl
    python jsonl_to_sqlite.py --jsonl wow_product_info.jsonl --db products.db
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_DB_PATH = Path("products.db")
DEFAULT_JSONL_PATH = Path("product_info.jsonl")


# ---------------------- DB SETUP ---------------------- #

def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a connection to the SQLite database."""
    conn = sqlite3.connect(str(db_path))
    # Make rows come back as dict-like if you ever read them
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Create / update the product_prices table.

    Columns:
      - id           : primary key
      - scraped_at   : timestamp the row was inserted (UTC)
      - item_id
      - product_name
      - brand
      - price
      - review_count
      - avg_rating
      - availability
      - image_url
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS product_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scraped_at TEXT NOT NULL DEFAULT (datetime('now')),
            item_id TEXT,
            product_name TEXT,
            brand TEXT,
            price REAL,
            review_count INTEGER,
            avg_rating REAL,
            availability TEXT,
            image_url TEXT
        )
        """
    )

    # If table already existed from an older version without image_url,
    # try to add the column. This will fail harmlessly if it already exists.
    try:
        conn.execute("ALTER TABLE product_prices ADD COLUMN image_url TEXT")
    except sqlite3.OperationalError:
        # Column already exists or table is in old shape; that's fine.
        pass

    # If you later want faster lookups by item_id:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_product_prices_item_id
        ON product_prices (item_id)
        """
    )

    conn.commit()


# ---------------------- HELPERS ---------------------- #

def parse_price(value: Any) -> Optional[float]:
    """Convert the 'price' field from JSON into a float, if possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    # If it's a string like "4.6" or "$4.60"
    text = str(value).strip()
    text = text.replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def to_int_or_none(value: Any) -> Optional[int]:
    """Convert to int if possible, otherwise None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float_or_none(value: Any) -> Optional[float]:
    """Convert to float if possible, otherwise None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_image_url(obj: Dict[str, Any]) -> Optional[str]:
    """
    Get the image URL from the JSON object.

    Tries a few possible key names in case the scraper uses different ones.
    """
    return (
        obj.get("image_url")
        or obj.get("image")
        or obj.get("imageUrl")
        or None
    )


def insert_product(conn: sqlite3.Connection, obj: Dict[str, Any]) -> None:
    """
    Insert one product JSON object into the database.

    Any missing keys just become NULL in SQLite.
    scraped_at uses the DEFAULT (datetime('now')) on each insert.
    """
    image_url = extract_image_url(obj)

    conn.execute(
        """
        INSERT INTO product_prices (
            item_id,
            product_name,
            brand,
            price,
            review_count,
            avg_rating,
            availability,
            image_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            obj.get("item_id"),
            obj.get("product_name"),
            obj.get("brand"),
            parse_price(obj.get("price")),
            to_int_or_none(obj.get("review_count")),
            to_float_or_none(obj.get("avg_rating")),
            obj.get("availability"),
            image_url,
        ),
    )


# ---------------------- MAIN IMPORT LOGIC ---------------------- #

def import_jsonl_to_sqlite(jsonl_path: Path, db_path: Path) -> None:
    """
    Read a .jsonl file line by line and append each JSON object
    into the SQLite database.
    """
    if not jsonl_path.exists():
        raise FileNotFoundError(f"JSONL file not found: {jsonl_path}")

    conn = get_connection(db_path)
    try:
        ensure_schema(conn)

        with jsonl_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue  # skip blank lines

                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"[WARN] Skipping line {line_no}: invalid JSON ({e})")
                    continue

                if not isinstance(obj, dict):
                    print(f"[WARN] Skipping line {line_no}: JSON is not an object")
                    continue

                insert_product(conn, obj)

        conn.commit()
        print(f"Imported data from {jsonl_path} into {db_path}")
    finally:
        conn.close()


# ---------------------- CLI ENTRYPOINT ---------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append scraped .jsonl product data into a SQLite database."
    )
    parser.add_argument(
        "--jsonl",
        type=str,
        default=str(DEFAULT_JSONL_PATH),
        help="Path to the .jsonl file (default: product_info.jsonl)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help="Path to the SQLite DB file (default: products.db)",
    )

    args = parser.parse_args()
    jsonl_path = Path(args.jsonl)
    db_path = Path(args.db)

    import_jsonl_to_sqlite(jsonl_path, db_path)


if __name__ == "__main__":
    main()
