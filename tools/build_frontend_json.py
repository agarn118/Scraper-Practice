#!/usr/bin/env python3
"""
Enhanced build_frontend_json.py - Fixed for real Walmart/Superstore data

Key fixes:
1. More aggressive brand removal from titles
2. Better handling of size variations between stores
3. Improved synonym handling for "chocolate", "partly skimmed", etc.
4. Smarter grouping that considers product type not just exact size
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# -------------------------------------------------------------------
# Config / paths
# -------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

WALMART_JSONL = RAW_DIR / "walmart_product_info.jsonl"
SUPERSTORE_JSONL = RAW_DIR / "superstore_product_info.jsonl"
OUTPUT_JSON = PROCESSED_DIR / "products.json"


# -------------------------------------------------------------------
# Enhanced normalization configuration
# -------------------------------------------------------------------

STOPWORDS = {
    "and", "the", "of", "for", "in", "to", "a", "an", "with", "by", "or",
    "from", "on", "at", "is", "are", "was", "were", "be", "been", "being",
    "bottle", "bottles", "case", "pack"
}

# Brand variations that should be treated as identical
BRAND_ALIASES = {
    "milk2go": {"milk2go", "milk 2 go", "milk2 go", "milk to go"},
    "pc": {"presidents choice", "president's choice", "presidents choice", "pc"},
    "no name": {"no name", "noname", "nn"},
    "great value": {"great value", "greatvalue", "gv"},
    "neilson": {"neilson", "nielson"},
    "dairyland": {"dairyland", "dairy land"},
    "natrel": {"natrel", "na trel"},
    "beatrice": {"beatrice"},
    "lactantia": {"lactantia"},
}

# Word equivalents in product names
WORD_SYNONYMS = {
    # Milk types - be careful with order!
    "homogenized": "wholefat",
    "homo": "wholefat",
    "partly skimmed": "lowfat",
    "part skimmed": "lowfat", 
    "part skim": "lowfat",
    "low fat": "lowfat",
    "lowfat": "lowfat",
    "skim": "nonfat",
    "skimmed": "nonfat",
    "non fat": "nonfat",
    "nonfat": "nonfat",
    "whole milk": "wholefat",
    "whole": "wholefat",
    
    # Chocolate variations
    "choc": "chocolate",
    "chocolat": "chocolate",
    "cocoa": "chocolate",
    
    # Strawberry
    "strawb": "strawberry",
    "straw": "strawberry",
    
    # Vanilla
    "van": "vanilla",
    "vanil": "vanilla",
    
    # Other
    "original": "",  # Remove this filler word
    "classic": "",
}


# -------------------------------------------------------------------
# Core normalization functions
# -------------------------------------------------------------------

def _strip_accents_lower(s: str) -> str:
    """Remove accents and lowercase."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


def _normalize_brand(brand: str) -> str:
    """
    Normalize brand with alias resolution.
    
    Examples:
        "Milk 2 Go" -> "milk2go"
        "President's Choice" -> "pc"
    """
    if not brand:
        return ""
    
    s = _strip_accents_lower(brand)
    # Remove all non-alphanumeric
    s = re.sub(r"[^a-z0-9]+", "", s)
    
    # Check aliases
    for canonical, aliases in BRAND_ALIASES.items():
        # Normalize each alias the same way
        normalized_aliases = {re.sub(r"[^a-z0-9]+", "", _strip_accents_lower(a)) for a in aliases}
        if s in normalized_aliases:
            return canonical
    
    return s


def _apply_word_synonyms(text: str) -> str:
    """
    Apply multi-word and single-word synonym replacements.
    Must be done on lowercased text with spaces.
    """
    # Multi-word synonyms first (order matters!)
    for original, replacement in sorted(WORD_SYNONYMS.items(), key=lambda x: -len(x[0])):
        # Use word boundaries
        pattern = r'\b' + re.escape(original) + r'\b'
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text


def _extract_size_info(text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Extract size and unit from text, converting to standard units.
    
    Returns: (size_in_standard_unit, standard_unit) or (None, None)
    
    Examples:
        "310 ml" -> (0.31, "l")
        "4 L" -> (4.0, "l")  
        "6 x 310ml" -> (1.86, "l")  # total volume
        "250g" -> (0.25, "kg")
    """
    if not text:
        return (None, None)
    
    text_lower = _strip_accents_lower(text)
    
    # Pattern 1: Multi-pack like "6 x 310 ml" or "12x200ml"
    multi_match = re.search(
        r'(\d+)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(ml|l|g|kg|oz|lb)s?\b',
        text_lower
    )
    if multi_match:
        count = float(multi_match.group(1))
        size_each = float(multi_match.group(2))
        unit = multi_match.group(3)
        
        total_size = count * size_each
        
        # Normalize to standard units
        if unit in ["ml"]:
            return (total_size / 1000, "l")
        elif unit in ["l"]:
            return (total_size, "l")
        elif unit in ["g"]:
            return (total_size / 1000, "kg")
        elif unit in ["kg"]:
            return (total_size, "kg")
        elif unit in ["oz"]:
            return (total_size * 0.0295735, "l")  # fl oz to liters
        elif unit in ["lb"]:
            return (total_size * 0.453592, "kg")
    
    # Pattern 2: Single size like "310 ml" or "4 L"
    single_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(ml|l|litre|litres|g|kg|gram|grams|oz|lb)s?\b',
        text_lower
    )
    if single_match:
        size = float(single_match.group(1))
        unit = single_match.group(2)
        
        # Normalize to standard units
        if unit in ["ml"]:
            return (size / 1000, "l")
        elif unit in ["l", "litre", "litres"]:
            return (size, "l")
        elif unit in ["g", "gram", "grams"]:
            return (size / 1000, "kg")
        elif unit in ["kg"]:
            return (size, "kg")
        elif unit in ["oz"]:
            return (size * 0.0295735, "l")
        elif unit in ["lb"]:
            return (size * 0.453592, "kg")
    
    return (None, None)


def _remove_size_tokens(text: str) -> str:
    """Remove all size/quantity information from text."""
    patterns = [
        # Volume: 310ml, 4 L, 1.89 litres, etc.
        r'\b\d+(?:\.\d+)?\s*(?:ml|l|litre|litres|liter|liters)\b',
        # Weight: 250g, 2 kg, etc.
        r'\b\d+(?:\.\d+)?\s*(?:g|grams?|kg|kilograms?|oz|ounces?|lb|lbs|pounds?)\b',
        # Multi-pack: 6 x 310ml, 12x200 ml
        r'\b\d+\s*[x×]\s*\d+(?:\.\d+)?\s*(?:ml|l|g|kg|oz|lb)s?\b',
        # Packs/counts: 12 pack, 6pk, 24 count, case
        r'\b\d+\s*(?:pack|pk|count|ct|case|bottle|bottles|can|cans)\b',
        # Imperial volumes
        r'\b\d+(?:\.\d+)?\s*(?:fl\s*oz|fluid\s*ounce)\b',
        # Price per unit indicators
        r'\$\d+(?:\.\d+)?/\d+(?:ml|l|g|kg)',
    ]
    
    s = text
    for pat in patterns:
        s = re.sub(pat, ' ', s, flags=re.IGNORECASE)
    
    # Clean up multiple spaces
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _normalize_milk_percentage(text: str) -> str:
    """
    Normalize milk percentages to avoid parsing errors.
    E.g., "3.25%" should stay as "3.25%" not become "325" or "25"
    """
    # Protect decimal percentages by converting to words temporarily
    text = re.sub(r'\b3\.25%', 'threepointtwentyfivepercent', text)
    text = re.sub(r'\b3\.25\s*%', 'threepointtwentyfivepercent', text)
    text = re.sub(r'\b3\.25\s+percent', 'threepointtwentyfivepercent', text)
    
    # Also normalize common milk fat percentages
    text = re.sub(r'\b0%', 'zeropercentmilk', text)
    text = re.sub(r'\b1%', 'onepercentmilk', text)
    text = re.sub(r'\b2%', 'twopercentmilk', text)
    
    return text


def _denormalize_milk_percentage(text: str) -> str:
    """Convert milk percentage codes back to standard form."""
    text = text.replace('threepointtwentyfivepercent', 'wholefat')
    text = text.replace('zeropercentmilk', 'nonfat')
    text = text.replace('onepercentmilk', 'lowfat1')
    text = text.replace('twopercentmilk', 'lowfat2')
    return text


def _normalize_title_core(title: str, brand: str) -> str:
    """
    Extract the core essence of a product title for matching.
    
    This is the CRITICAL function for detecting duplicates across stores.
    
    Process:
    1. Lowercase and strip accents
    2. Protect milk percentages from being mangled
    3. Remove the brand from title (aggressively)
    4. Apply word synonyms (partly skimmed -> lowfat, etc.)
    5. Remove all size information
    6. Remove stopwords
    7. Sort remaining tokens (order-independent matching)
    """
    if not title:
        return ""
    
    s = _strip_accents_lower(title)
    
    # FIRST: Protect milk percentages before any other processing
    s = _normalize_milk_percentage(s)
    
    # Remove brand from title (try multiple variations)
    if brand:
        brand_norm = _normalize_brand(brand)
        
        # Remove exact brand as-is
        brand_escaped = re.escape(_strip_accents_lower(brand))
        s = re.sub(rf'\b{brand_escaped}\b', ' ', s)
        
        # Remove normalized brand
        if brand_norm:
            s = re.sub(rf'\b{brand_norm}\b', ' ', s)
        
        # Also try removing brand with spaces/hyphens as just letters
        # e.g. "milk2go" or "milk 2 go" both become "milk2go"
        brand_nospace = re.sub(r'[^a-z0-9]+', '', _strip_accents_lower(brand))
        if brand_nospace:
            s = re.sub(rf'\b{brand_nospace}\b', ' ', s)
    
    # Apply word synonyms BEFORE removing other tokens
    s = _apply_word_synonyms(s)
    
    # Remove size information
    s = _remove_size_tokens(s)
    
    # Convert milk percentage codes to final form
    s = _denormalize_milk_percentage(s)
    
    # Keep only alphanumeric (no % anymore since we converted them)
    s = re.sub(r'[^a-z0-9\s]+', ' ', s)
    
    # Tokenize
    tokens = re.findall(r'[a-z0-9]+', s)
    
    # Filter stopwords and single chars
    filtered = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    
    # Also remove pure numbers (these are usually size remnants)
    filtered = [t for t in filtered if not t.isdigit()]
    
    if not filtered:
        return ""
    
    # Sort for order-independent matching
    filtered.sort()
    return " ".join(filtered)


def _get_size_category(size: Optional[float], unit: Optional[str]) -> str:
    """
    Categorize size into buckets for smarter matching.
    
    This allows us to distinguish between single-serve, family-size, etc.
    without requiring exact size matches.
    """
    if size is None or unit is None:
        return "unknown"
    
    if unit == "l":
        if size < 0.5:
            return "single"  # < 500ml
        elif size < 2.5:
            return "medium"  # 500ml - 2.5L
        else:
            return "large"   # > 2.5L
    elif unit == "kg":
        if size < 0.5:
            return "small"
        elif size < 2.0:
            return "medium"
        else:
            return "large"
    
    return "unknown"


def _make_match_key(brand: str, title: str, package_sizing: Optional[str]) -> str:
    """
    Create matching key for products.
    
    Strategy: Use brand + title core + EXACT size to avoid merging different variants.
    """
    brand_key = _normalize_brand(brand)
    title_key = _normalize_title_core(title, brand)
    
    # Extract EXACT size from title OR package_sizing
    combined_text = f"{title} {package_sizing or ''}"
    size, unit = _extract_size_info(combined_text)
    
    # Use exact size to keep different pack sizes separate
    if size is not None and unit:
        size_key = f"{size:.3f}{unit}"
    else:
        size_key = "unknown"
    
    return f"{brand_key}|||{title_key}|||{size_key}"


# -------------------------------------------------------------------
# JSONL loader
# -------------------------------------------------------------------

def _parse_price_numeric(obj: Dict[str, Any]) -> Optional[float]:
    """Extract numeric price from various fields."""
    val = obj.get("price_numeric")
    if isinstance(val, (int, float)):
        return float(val)
    
    raw = obj.get("price_raw") or obj.get("price")
    if not raw:
        return None
    
    s = str(raw).strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def load_jsonl(path: Path, store_id: str) -> Iterable[Dict[str, Any]]:
    """Load and normalize JSONL data from a file."""
    if not path.exists():
        print(f"[WARN] Input file for {store_id} not found: {path}")
        return
    
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[WARN] Skipping bad JSON in {path.name} line {line_num}: {e}")
                continue
            
            obj["store"] = store_id
            
            # Normalize link
            link = obj.get("link") or obj.get("product_url")
            if link:
                obj["link"] = link
                obj["product_url"] = link
            
            # Ensure numeric price
            if "price_numeric" not in obj or obj["price_numeric"] is None:
                obj["price_numeric"] = _parse_price_numeric(obj)
            
            yield obj


# -------------------------------------------------------------------
# Product grouping
# -------------------------------------------------------------------

def _first_non_empty(items: List[Dict[str, Any]], field_names: List[str], default: Any = None) -> Any:
    """Get first non-empty value from a list of fields across items."""
    for field in field_names:
        for obj in items:
            val = obj.get(field)
            if val not in (None, "", []):
                return val
    return default


def build_products() -> List[Dict[str, Any]]:
    """
    Build merged products with enhanced duplicate detection.
    """
    # Load all products
    groups: Dict[str, List[Dict[str, Any]]] = {}
    
    sources = [
        ("walmart", WALMART_JSONL),
        ("superstore", SUPERSTORE_JSONL),
    ]
    
    total_loaded = 0
    
    for store_id, path in sources:
        for obj in load_jsonl(path, store_id):
            brand = obj.get("brand") or ""
            title = obj.get("title") or obj.get("product_name") or ""
            package_sizing = obj.get("package_sizing")
            
            if not title:
                continue
            
            match_key = _make_match_key(brand, title, package_sizing)
            groups.setdefault(match_key, []).append(obj)
            total_loaded += 1
    
    print(f"Loaded {total_loaded} raw store-level products")
    print(f"Formed {len(groups)} logical product groups")
    
    # Build products from groups
    products: List[Dict[str, Any]] = []
    
    for idx, (match_key, objs) in enumerate(groups.items(), start=1):
        # Product-level fields - prefer longer/more descriptive values
        brand = _first_non_empty(objs, ["brand"], default="")
        
        # For title, prefer the longer one (usually more descriptive)
        titles = [obj.get("title") or obj.get("product_name") for obj in objs if obj.get("title") or obj.get("product_name")]
        title = max(titles, key=len) if titles else ""
        
        description = _first_non_empty(objs, ["description", "short_description"], default="")
        package_sizing = _first_non_empty(objs, ["package_sizing"], default=None)
        image_url = _first_non_empty(objs, ["image_url"], default=None)
        
        # Collect search queries
        search_query_set = {str(o["search_query"]) for o in objs if o.get("search_query")}
        
        # Deduplicate offers per store
        offer_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        
        for obj in objs:
            store = obj.get("store") or "unknown"
            product_id = (
                obj.get("product_id")
                or obj.get("item_id")
                or obj.get("article_number")
                or ""
            )
            key_offer = (store, str(product_id))
            
            if key_offer in offer_map:
                continue
            
            store_name = "Walmart" if store == "walmart" else "Real Canadian Superstore"
            
            offer = {
                "store": store,
                "store_name": store_name,
                "product_id": obj.get("product_id") or obj.get("item_id"),
                "article_number": obj.get("article_number") or obj.get("item_id"),
                "price": obj.get("price"),
                "price_raw": obj.get("price_raw"),
                "price_numeric": obj.get("price_numeric"),
                "inventory_status": obj.get("inventory_status") or obj.get("availability"),
                "link": obj.get("link"),
                "image_url": obj.get("image_url"),
                "offer_type": obj.get("offer_type"),
                "is_sponsored": bool(obj.get("is_sponsored", False)),
                "review_count": obj.get("review_count"),
                "avg_rating": obj.get("avg_rating"),
            }
            
            offer_map[key_offer] = offer
        
        offers = list(offer_map.values())
        if not offers:
            continue
        
        # Calculate minimum price
        min_price: Optional[float] = None
        for offer in offers:
            pn = offer.get("price_numeric")
            if isinstance(pn, (int, float)):
                pn = float(pn)
                if min_price is None or pn < min_price:
                    min_price = pn
        
        min_price_display = f"${min_price:.2f}" if min_price is not None else None
        
        product = {
            "id": idx,
            "brand": brand,
            "title": title,
            "description": description,
            "package_sizing": package_sizing,
            "image_url": image_url,
            "search_queries": sorted(search_query_set),
            "offers": offers,
            "store_count": len(offers),
            "min_price": min_price,
            "min_price_display": min_price_display,
        }
        
        products.append(product)
    
    # Sort by title, then brand
    products.sort(key=lambda p: (
        _strip_accents_lower(p.get("title", "")),
        _strip_accents_lower(p.get("brand", ""))
    ))
    
    print(f"Built {len(products)} merged products")
    
    # Report on multi-store products
    multi_store = sum(1 for p in products if p["store_count"] > 1)
    print(f"  - {multi_store} products available at multiple stores")
    print(f"  - {len(products) - multi_store} products at single store only")
    
    return products


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    products = build_products()
    payload = {"items": products}
    
    OUTPUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    print(f"\nWrote {len(products)} products to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()