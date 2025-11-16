#!/usr/bin/env python3
"""
build_frontend_json.py - Reads matched and unmatched products

This script:
1. Reads total_products.jsonl (matched pairs from both stores)
2. Reads unmatched_products.jsonl (single-store products)
3. Combines them into products.json for the frontend
4. Each product has offers from one or both stores

Output format:
{
  "items": [
    {
      "id": 1,
      "brand": "Milk2Go",
      "title": "Strawberry Milk 310mL",
      "description": "...",
      "image_url": "...",
      "offers": [
        { "store": "walmart", "price": "$2.38", ... },
        { "store": "superstore", "price": "$1.99", ... }
      ],
      "store_count": 2,
      "min_price": 1.99,
      "min_price_display": "$1.99"
    }
  ]
}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


# -------------------------------------------------------------------
# Config / paths
# -------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

TOTAL_PRODUCTS_JSONL = RAW_DIR / "total_products.jsonl"  # Matched pairs
UNMATCHED_PRODUCTS_JSONL = RAW_DIR / "unmatched_products.jsonl"  # Single-store items
OUTPUT_JSON = PROCESSED_DIR / "products.json"


# -------------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------------

def parse_price_numeric(price_value: Any) -> Optional[float]:
    """Extract numeric price from various formats."""
    if price_value is None:
        return None
    
    if isinstance(price_value, (int, float)):
        return float(price_value)
    
    # String format: "$2.38" or "2.38"
    s = str(price_value).strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def load_matched_products() -> List[Dict[str, Any]]:
    """
    Load matched product pairs from total_products.jsonl.
    Each line has walmart_offer and superstore_offer.
    """
    products = []
    
    if not TOTAL_PRODUCTS_JSONL.exists():
        print(f"⚠️  Matched products file not found: {TOTAL_PRODUCTS_JSONL}")
        return products
    
    with TOTAL_PRODUCTS_JSONL.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                matched = json.loads(line)
                
                # Extract common fields
                brand = matched.get("brand", "")
                title = matched.get("title", "")
                description = matched.get("description", "")
                image_url = matched.get("image_url", "")
                package_sizing = matched.get("package_sizing", "")
                
                # Build offers array from both stores
                offers = []
                
                # Walmart offer
                walmart_offer = matched.get("walmart_offer", {})
                if walmart_offer:
                    offers.append({
                        "store": "walmart",
                        "store_name": "Walmart",
                        "product_id": walmart_offer.get("product_id"),
                        "article_number": walmart_offer.get("article_number"),
                        "price": walmart_offer.get("price"),
                        "price_raw": walmart_offer.get("price_raw"),
                        "price_numeric": walmart_offer.get("price_numeric"),
                        "inventory_status": walmart_offer.get("inventory_status"),
                        "link": walmart_offer.get("link"),
                        "image_url": walmart_offer.get("image_url"),
                        "review_count": walmart_offer.get("review_count"),
                        "avg_rating": walmart_offer.get("avg_rating"),
                        "offer_type": walmart_offer.get("offer_type", "OG"),
                        "is_sponsored": walmart_offer.get("is_sponsored", False),
                    })
                
                # Superstore offer
                superstore_offer = matched.get("superstore_offer", {})
                if superstore_offer:
                    offers.append({
                        "store": "superstore",
                        "store_name": "Real Canadian Superstore",
                        "product_id": superstore_offer.get("product_id"),
                        "article_number": superstore_offer.get("article_number"),
                        "price": superstore_offer.get("price"),
                        "price_raw": superstore_offer.get("price_raw"),
                        "price_numeric": superstore_offer.get("price_numeric"),
                        "inventory_status": superstore_offer.get("inventory_status"),
                        "link": superstore_offer.get("link"),
                        "image_url": superstore_offer.get("image_url"),
                        "offer_type": superstore_offer.get("offer_type", "OG"),
                        "is_sponsored": superstore_offer.get("is_sponsored", False),
                    })
                
                # Calculate min price
                min_price = None
                for offer in offers:
                    price = offer.get("price_numeric")
                    if isinstance(price, (int, float)):
                        if min_price is None or price < min_price:
                            min_price = price
                
                # Search queries (use from either store)
                search_queries = []
                if walmart_offer.get("search_query"):
                    search_queries.append(walmart_offer["search_query"])
                if superstore_offer.get("search_query"):
                    search_queries.append(superstore_offer["search_query"])
                
                product = {
                    "brand": brand,
                    "title": title,
                    "description": description,
                    "package_sizing": package_sizing,
                    "image_url": image_url,
                    "search_queries": list(set(search_queries)),  # Deduplicate
                    "offers": offers,
                    "store_count": len(offers),
                    "min_price": min_price,
                    "min_price_display": f"${min_price:.2f}" if min_price else None,
                    "match_confidence": matched.get("match_confidence"),
                    "cheaper_store": matched.get("cheaper_store"),
                }
                
                products.append(product)
                
            except json.JSONDecodeError as e:
                print(f"⚠️  Bad JSON in {TOTAL_PRODUCTS_JSONL.name} line {line_num}: {e}")
    
    return products


def load_unmatched_products() -> List[Dict[str, Any]]:
    """
    Load unmatched products from unmatched_products.jsonl.
    Each line is a single product from one store.
    """
    products = []
    
    if not UNMATCHED_PRODUCTS_JSONL.exists():
        print(f"⚠️  Unmatched products file not found: {UNMATCHED_PRODUCTS_JSONL}")
        return products
    
    with UNMATCHED_PRODUCTS_JSONL.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                unmatched = json.loads(line)
                
                store = unmatched.get("store", "unknown")
                store_name = "Walmart" if store == "walmart" else "Real Canadian Superstore"
                
                # Build single offer
                offer = {
                    "store": store,
                    "store_name": store_name,
                    "product_id": unmatched.get("product_id"),
                    "article_number": unmatched.get("article_number"),
                    "price": unmatched.get("price"),
                    "price_numeric": unmatched.get("price_numeric"),
                    "inventory_status": unmatched.get("inventory_status"),
                    "link": unmatched.get("link"),
                    "image_url": unmatched.get("image_url"),
                    "offer_type": "OG",
                    "is_sponsored": False,
                }
                
                price_numeric = parse_price_numeric(offer["price_numeric"])
                
                product = {
                    "brand": unmatched.get("brand", ""),
                    "title": unmatched.get("title", ""),
                    "description": "",
                    "package_sizing": unmatched.get("package_sizing", ""),
                    "image_url": unmatched.get("image_url", ""),
                    "search_queries": [unmatched.get("search_query", "")] if unmatched.get("search_query") else [],
                    "offers": [offer],
                    "store_count": 1,
                    "min_price": price_numeric,
                    "min_price_display": f"${price_numeric:.2f}" if price_numeric else None,
                }
                
                products.append(product)
                
            except json.JSONDecodeError as e:
                print(f"⚠️  Bad JSON in {UNMATCHED_PRODUCTS_JSONL.name} line {line_num}: {e}")
    
    return products


def build_frontend_json():
    """
    Combine matched and unmatched products into single frontend JSON.
    """
    print("\n" + "="*70)
    print("BUILDING FRONTEND JSON")
    print("="*70)
    
    # Load matched products (products available at both stores)
    print("\n📂 Loading matched products...")
    matched_products = load_matched_products()
    print(f"   Loaded {len(matched_products):,} matched products")
    
    # Load unmatched products (products at single store only)
    print("\n📂 Loading unmatched products...")
    unmatched_products = load_unmatched_products()
    print(f"   Loaded {len(unmatched_products):,} unmatched products")
    
    # Combine all products
    all_products = matched_products + unmatched_products
    
    # Assign IDs
    for idx, product in enumerate(all_products, start=1):
        product["id"] = idx
    
    # Sort by title (case-insensitive)
    all_products.sort(key=lambda p: p.get("title", "").lower())
    
    print(f"\n📊 Summary:")
    print(f"   Total products: {len(all_products):,}")
    print(f"   Multi-store products: {len(matched_products):,}")
    print(f"   Single-store products: {len(unmatched_products):,}")
    
    # Count by store
    walmart_count = sum(1 for p in all_products if any(o["store"] == "walmart" for o in p["offers"]))
    superstore_count = sum(1 for p in all_products if any(o["store"] == "superstore" for o in p["offers"]))
    
    print(f"\n🏪 Store coverage:")
    print(f"   Walmart: {walmart_count:,} products")
    print(f"   Superstore: {superstore_count:,} products")
    
    # Write output
    print(f"\n💾 Writing to {OUTPUT_JSON}...")
    
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    output = {"items": all_products}
    
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"   ✅ Wrote {len(all_products):,} products")
    
    # Sample products
    print(f"\n📋 Sample products:")
    for i, product in enumerate(all_products[:3], 1):
        stores = ", ".join([o["store_name"] for o in product["offers"]])
        print(f"\n{i}. {product['brand']} - {product['title'][:60]}")
        print(f"   Price: {product['min_price_display']}")
        print(f"   Available at: {stores}")
    
    print("\n" + "="*70)
    print("FRONTEND JSON BUILD COMPLETE!")
    print("="*70)
    print(f"\n✅ Output: {OUTPUT_JSON}")
    print(f"✅ Ready to serve via Flask app!")
    print("\n" + "="*70 + "\n")


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main():
    build_frontend_json()


if __name__ == "__main__":
    main()