#!/usr/bin/env python3
"""
Advanced Product Matcher

This script reads walmart_product_info.jsonl and superstore_product_info.jsonl,
uses sophisticated matching algorithms to find the same products across stores,
and outputs matched pairs to total_products.jsonl.

Matching Strategy:
1. Exact brand + normalized title + size matching (highest confidence)
2. Brand + normalized title matching (medium confidence) 
3. Fuzzy title matching for near-duplicates (lower confidence)
4. Category-based matching for remaining products
5. Manual review suggestions for ambiguous matches

Output Format (total_products.jsonl):
Each line is a JSON object with:
- Common product fields (brand, title, description, etc.)
- walmart_offer: {...} - Walmart-specific data
- superstore_offer: {...} - Superstore-specific data
- match_confidence: "high" | "medium" | "low"
- match_method: description of how they were matched
- price_difference: absolute price difference
- price_difference_percent: percentage difference
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from difflib import SequenceMatcher
from collections import defaultdict

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"

WALMART_JSONL = RAW_DIR / "walmart_product_info.jsonl"
SUPERSTORE_JSONL = RAW_DIR / "superstore_product_info.jsonl"
OUTPUT_JSONL = RAW_DIR / "total_products.jsonl"

# Matching thresholds
FUZZY_MATCH_THRESHOLD = 0.85  # For fuzzy string matching (0.0-1.0)
MIN_TITLE_LENGTH = 5  # Minimum title length to consider
SIZE_TOLERANCE = 0.05  # 5% tolerance for size differences

# Brand aliases for cross-store matching
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
    "hersheys": {"hershey's", "hersheys", "hershey"},
    "cadbury": {"cadbury"},
    "nestle": {"nestle", "nestlé"},
    "kraft": {"kraft"},
    "kelloggs": {"kellogg's", "kelloggs"},
}

WORD_SYNONYMS = {
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
    "choc": "chocolate",
    "chocolat": "chocolate",
    "cocoa": "chocolate",
    "strawb": "strawberry",
    "straw": "strawberry",
    "van": "vanilla",
    "vanil": "vanilla",
}

STOPWORDS = {
    "and", "the", "of", "for", "in", "to", "a", "an", "with", "by", "or",
    "from", "on", "at", "is", "are", "was", "were", "be", "been", "being",
}

# -------------------------------------------------------------------
# Normalization Functions
# -------------------------------------------------------------------

def _strip_accents_lower(s: str) -> str:
    """Remove accents and lowercase."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


def _normalize_brand(brand: str) -> str:
    """Normalize brand with alias resolution."""
    if not brand:
        return ""
    
    s = _strip_accents_lower(brand)
    s = re.sub(r"[^a-z0-9]+", "", s)
    
    for canonical, aliases in BRAND_ALIASES.items():
        normalized_aliases = {re.sub(r"[^a-z0-9]+", "", _strip_accents_lower(a)) for a in aliases}
        if s in normalized_aliases:
            return canonical
    
    return s


def _apply_word_synonyms(text: str) -> str:
    """Apply word synonym replacements."""
    for original, replacement in sorted(WORD_SYNONYMS.items(), key=lambda x: -len(x[0])):
        pattern = r'\b' + re.escape(original) + r'\b'
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _extract_size_info(text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Extract size and unit from text, converting to standard units.
    Returns: (size_in_standard_unit, standard_unit) or (None, None)
    """
    if not text:
        return (None, None)
    
    text_lower = _strip_accents_lower(text)
    
    # Multi-pack: "6 x 310 ml"
    multi_match = re.search(
        r'(\d+)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(ml|l|g|kg|oz|lb)s?\b',
        text_lower
    )
    if multi_match:
        count = float(multi_match.group(1))
        size_each = float(multi_match.group(2))
        unit = multi_match.group(3)
        total_size = count * size_each
        
        if unit in ["ml"]:
            return (total_size / 1000, "l")
        elif unit in ["l"]:
            return (total_size, "l")
        elif unit in ["g"]:
            return (total_size / 1000, "kg")
        elif unit in ["kg"]:
            return (total_size, "kg")
        elif unit in ["oz"]:
            return (total_size * 0.0295735, "l")
        elif unit in ["lb"]:
            return (total_size * 0.453592, "kg")
    
    # Single size: "310 ml"
    single_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(ml|l|litre|litres|g|kg|gram|grams|oz|lb)s?\b',
        text_lower
    )
    if single_match:
        size = float(single_match.group(1))
        unit = single_match.group(2)
        
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
    """Remove size information from text."""
    patterns = [
        r'\b\d+(?:\.\d+)?\s*(?:ml|l|litre|litres|liter|liters)\b',
        r'\b\d+(?:\.\d+)?\s*(?:g|grams?|kg|kilograms?|oz|ounces?|lb|lbs|pounds?)\b',
        r'\b\d+\s*[x×]\s*\d+(?:\.\d+)?\s*(?:ml|l|g|kg|oz|lb)s?\b',
        r'\b\d+\s*(?:pack|pk|count|ct|case|bottle|bottles|can|cans)\b',
        r'\b\d+(?:\.\d+)?\s*(?:fl\s*oz|fluid\s*ounce)\b',
        r'\$\d+(?:\.\d+)?/\d+(?:ml|l|g|kg)',
    ]
    
    s = text
    for pat in patterns:
        s = re.sub(pat, ' ', s, flags=re.IGNORECASE)
    
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _normalize_milk_percentage(text: str) -> str:
    """Protect milk percentages from being mangled."""
    text = re.sub(r'\b3\.25%', 'threepointtwentyfivepercent', text)
    text = re.sub(r'\b3\.25\s*%', 'threepointtwentyfivepercent', text)
    text = re.sub(r'\b0%', 'zeropercentmilk', text)
    text = re.sub(r'\b1%', 'onepercentmilk', text)
    text = re.sub(r'\b2%', 'twopercentmilk', text)
    return text


def _denormalize_milk_percentage(text: str) -> str:
    """Convert milk percentage codes back."""
    text = text.replace('threepointtwentyfivepercent', 'wholefat')
    text = text.replace('zeropercentmilk', 'nonfat')
    text = text.replace('onepercentmilk', 'lowfat1')
    text = text.replace('twopercentmilk', 'lowfat2')
    return text


def normalize_title_for_matching(title: str, brand: str) -> str:
    """
    Normalize title for matching across stores.
    Returns a cleaned, order-independent representation.
    """
    if not title or len(title) < MIN_TITLE_LENGTH:
        return ""
    
    s = _strip_accents_lower(title)
    s = _normalize_milk_percentage(s)
    
    # Remove brand
    if brand:
        brand_norm = _normalize_brand(brand)
        brand_escaped = re.escape(_strip_accents_lower(brand))
        s = re.sub(rf'\b{brand_escaped}\b', ' ', s)
        
        if brand_norm:
            s = re.sub(rf'\b{brand_norm}\b', ' ', s)
        
        brand_nospace = re.sub(r'[^a-z0-9]+', '', _strip_accents_lower(brand))
        if brand_nospace:
            s = re.sub(rf'\b{brand_nospace}\b', ' ', s)
    
    s = _apply_word_synonyms(s)
    s = _remove_size_tokens(s)
    s = _denormalize_milk_percentage(s)
    s = re.sub(r'[^a-z0-9\s]+', ' ', s)
    
    tokens = re.findall(r'[a-z0-9]+', s)
    filtered = [t for t in tokens if t not in STOPWORDS and len(t) > 1 and not t.isdigit()]
    
    if not filtered:
        return ""
    
    filtered.sort()
    return " ".join(filtered)


def fuzzy_similarity(s1: str, s2: str) -> float:
    """Calculate similarity between two strings (0.0 to 1.0)."""
    return SequenceMatcher(None, s1, s2).ratio()


def sizes_compatible(size1: Tuple[Optional[float], Optional[str]], 
                     size2: Tuple[Optional[float], Optional[str]]) -> bool:
    """
    Check if two sizes are compatible (same or within tolerance).
    """
    val1, unit1 = size1
    val2, unit2 = size2
    
    # If either is None, consider compatible
    if val1 is None or val2 is None:
        return True
    
    # Must have same unit
    if unit1 != unit2:
        return False
    
    # Allow tolerance for measurement differences
    diff = abs(val1 - val2)
    avg = (val1 + val2) / 2
    
    if avg == 0:
        return val1 == val2
    
    return diff / avg <= SIZE_TOLERANCE


# -------------------------------------------------------------------
# Data Loading
# -------------------------------------------------------------------

def load_products(filepath: Path, store_name: str) -> List[Dict[str, Any]]:
    """Load products from JSONL file."""
    products = []
    
    if not filepath.exists():
        print(f"⚠️  File not found: {filepath}")
        return products
    
    with filepath.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                obj = json.loads(line)
                obj["_store"] = store_name  # Add store identifier
                obj["_line_num"] = line_num
                products.append(obj)
            except json.JSONDecodeError as e:
                print(f"⚠️  Bad JSON in {filepath.name} line {line_num}: {e}")
    
    return products


def parse_price(obj: Dict[str, Any]) -> Optional[float]:
    """Extract numeric price from product object."""
    # Try price_numeric first
    if "price_numeric" in obj and obj["price_numeric"] is not None:
        try:
            return float(obj["price_numeric"])
        except (ValueError, TypeError):
            pass
    
    # Try price_raw
    price_raw = obj.get("price_raw") or obj.get("price")
    if price_raw:
        s = str(price_raw).strip().replace("$", "").replace(",", "")
        try:
            return float(s)
        except ValueError:
            pass
    
    return None


# -------------------------------------------------------------------
# Matching Algorithms
# -------------------------------------------------------------------

def create_match_key(product: Dict[str, Any]) -> Tuple[str, str, Tuple[Optional[float], Optional[str]]]:
    """
    Create a matching key for a product.
    Returns: (normalized_brand, normalized_title, size_info)
    """
    brand = product.get("brand") or ""
    title = product.get("title") or product.get("product_name") or ""
    
    norm_brand = _normalize_brand(brand)
    norm_title = normalize_title_for_matching(title, brand)
    
    # Extract size from title and package_sizing
    combined = f"{title} {product.get('package_sizing', '')}"
    size_info = _extract_size_info(combined)
    
    return (norm_brand, norm_title, size_info)


def exact_match(walmart_products: List[Dict], superstore_products: List[Dict]) -> Tuple[List[Tuple], Set[int], Set[int]]:
    """
    Find exact matches based on brand + title + size.
    Returns: (matches, walmart_matched_indices, superstore_matched_indices)
    """
    matches = []
    walmart_matched = set()
    superstore_matched = set()
    
    # Index Superstore products by match key
    superstore_index = defaultdict(list)
    for idx, product in enumerate(superstore_products):
        brand, title, size = create_match_key(product)
        if brand and title:  # Must have both
            key = (brand, title, size)
            superstore_index[key].append(idx)
    
    # Find Walmart products with exact matches
    for wm_idx, wm_product in enumerate(walmart_products):
        brand, title, size = create_match_key(wm_product)
        
        if not brand or not title:
            continue
        
        key = (brand, title, size)
        
        if key in superstore_index:
            for ss_idx in superstore_index[key]:
                if ss_idx not in superstore_matched:
                    matches.append((wm_idx, ss_idx, "high", "exact_brand_title_size"))
                    walmart_matched.add(wm_idx)
                    superstore_matched.add(ss_idx)
                    break  # Only match once
    
    return matches, walmart_matched, superstore_matched


def brand_title_match(walmart_products: List[Dict], superstore_products: List[Dict],
                     walmart_matched: Set[int], superstore_matched: Set[int]) -> Tuple[List[Tuple], Set[int], Set[int]]:
    """
    Find matches based on brand + title (ignoring size differences).
    Only considers products not already matched.
    """
    matches = []
    new_walmart_matched = set()
    new_superstore_matched = set()
    
    # Index unmatched Superstore products by brand + title
    superstore_index = defaultdict(list)
    for idx, product in enumerate(superstore_products):
        if idx in superstore_matched:
            continue
        
        brand = _normalize_brand(product.get("brand") or "")
        title = normalize_title_for_matching(
            product.get("title") or product.get("product_name") or "",
            product.get("brand") or ""
        )
        
        if brand and title:
            key = (brand, title)
            superstore_index[key].append(idx)
    
    # Find Walmart products with brand+title matches
    for wm_idx, wm_product in enumerate(walmart_products):
        if wm_idx in walmart_matched:
            continue
        
        brand = _normalize_brand(wm_product.get("brand") or "")
        title = normalize_title_for_matching(
            wm_product.get("title") or wm_product.get("product_name") or "",
            wm_product.get("brand") or ""
        )
        
        if not brand or not title:
            continue
        
        key = (brand, title)
        
        if key in superstore_index:
            for ss_idx in superstore_index[key]:
                if ss_idx not in superstore_matched and ss_idx not in new_superstore_matched:
                    matches.append((wm_idx, ss_idx, "medium", "brand_title_different_size"))
                    new_walmart_matched.add(wm_idx)
                    new_superstore_matched.add(ss_idx)
                    break
    
    return matches, new_walmart_matched, new_superstore_matched


def fuzzy_match(walmart_products: List[Dict], superstore_products: List[Dict],
               walmart_matched: Set[int], superstore_matched: Set[int]) -> Tuple[List[Tuple], Set[int], Set[int]]:
    """
    Find fuzzy matches based on title similarity.
    OPTIMIZED: Uses brand indexing + early termination + progress tracking.
    Only considers products not already matched.
    """
    matches = []
    new_walmart_matched = set()
    new_superstore_matched = set()
    
    # Get unmatched products
    unmatched_walmart = [(idx, p) for idx, p in enumerate(walmart_products) if idx not in walmart_matched]
    unmatched_superstore = [(idx, p) for idx, p in enumerate(superstore_products) if idx not in superstore_matched]
    
    print(f"   Fuzzy matching {len(unmatched_walmart)} Walmart × {len(unmatched_superstore)} Superstore products...")
    
    # OPTIMIZATION 1: Index Superstore products by brand
    ss_by_brand = defaultdict(list)
    ss_no_brand = []
    
    for ss_idx, ss_product in unmatched_superstore:
        ss_brand = _normalize_brand(ss_product.get("brand") or "")
        ss_title = normalize_title_for_matching(
            ss_product.get("title") or ss_product.get("product_name") or "",
            ss_product.get("brand") or ""
        )
        
        if not ss_title:
            continue
        
        if ss_brand:
            ss_by_brand[ss_brand].append((ss_idx, ss_product, ss_title))
        else:
            ss_no_brand.append((ss_idx, ss_product, ss_title))
    
    total_comparisons = 0
    skipped_comparisons = 0
    matches_found = 0
    
    # For progress tracking
    progress_interval = max(1, len(unmatched_walmart) // 10)  # Report every 10%
    
    # For each unmatched Walmart product
    for progress_idx, (wm_idx, wm_product) in enumerate(unmatched_walmart):
        # Progress indicator
        if progress_idx % progress_interval == 0:
            pct = (progress_idx / len(unmatched_walmart)) * 100
            print(f"      Progress: {pct:.0f}% ({progress_idx}/{len(unmatched_walmart)}) - {matches_found} matches found", end='\r')
        
        wm_brand = _normalize_brand(wm_product.get("brand") or "")
        wm_title = normalize_title_for_matching(
            wm_product.get("title") or wm_product.get("product_name") or "",
            wm_product.get("brand") or ""
        )
        
        if not wm_title:
            continue
        
        # Get candidate pool: same brand + no-brand products
        candidates = []
        if wm_brand:
            candidates = ss_by_brand.get(wm_brand, [])
            # Only add no-brand if we don't have many same-brand candidates
            if len(candidates) < 100:
                candidates.extend(ss_no_brand[:50])  # Limit no-brand checks
            
            # Track skipped comparisons
            total_ss = len(unmatched_superstore)
            skipped_comparisons += total_ss - len(candidates)
        else:
            # No brand: check all, but limit to reasonable number
            candidates = ss_no_brand + [item for items in ss_by_brand.values() for item in items]
            candidates = candidates[:500]  # Cap at 500 comparisons per product
        
        best_match = None
        best_similarity = 0.0
        
        for ss_idx, ss_product, ss_title in candidates:
            if ss_idx in superstore_matched or ss_idx in new_superstore_matched:
                continue
            
            total_comparisons += 1
            
            # OPTIMIZATION 2: Quick length check before expensive comparison
            len_diff = abs(len(wm_title) - len(ss_title))
            if len_diff > max(len(wm_title), len(ss_title)) * 0.5:
                continue  # Titles too different in length
            
            # Calculate similarity
            similarity = fuzzy_similarity(wm_title, ss_title)
            
            if similarity >= FUZZY_MATCH_THRESHOLD and similarity > best_similarity:
                best_similarity = similarity
                best_match = ss_idx
                
                # OPTIMIZATION 3: Early termination if we find a perfect match
                if similarity >= 0.98:
                    break
        
        if best_match is not None:
            matches.append((wm_idx, best_match, "low", f"fuzzy_match_{best_similarity:.2f}"))
            new_walmart_matched.add(wm_idx)
            new_superstore_matched.add(best_match)
            matches_found += 1
    
    print(f"\n   Completed: {total_comparisons:,} comparisons (saved {skipped_comparisons:,})")
    
    return matches, new_walmart_matched, new_superstore_matched


def category_match(walmart_products: List[Dict], superstore_products: List[Dict],
                  walmart_matched: Set[int], superstore_matched: Set[int]) -> Tuple[List[Tuple], Set[int], Set[int]]:
    """
    Match products within same category/search query using relaxed criteria.
    This is a final attempt to find matches for remaining products.
    """
    matches = []
    new_walmart_matched = set()
    new_superstore_matched = set()
    
    # Group unmatched products by category
    wm_by_category = defaultdict(list)
    ss_by_category = defaultdict(list)
    
    for idx, product in enumerate(walmart_products):
        if idx not in walmart_matched:
            category = product.get("search_query", "").lower()
            if category:
                wm_by_category[category].append((idx, product))
    
    for idx, product in enumerate(superstore_products):
        if idx not in superstore_matched:
            category = product.get("search_query", "").lower()
            if category:
                ss_by_category[category].append((idx, product))
    
    # Match within categories
    for category in wm_by_category.keys():
        if category not in ss_by_category:
            continue
        
        wm_items = wm_by_category[category]
        ss_items = ss_by_category[category]
        
        for wm_idx, wm_product in wm_items:
            if wm_idx in new_walmart_matched:
                continue
            
            wm_brand = _normalize_brand(wm_product.get("brand") or "")
            wm_title = normalize_title_for_matching(
                wm_product.get("title") or "",
                wm_product.get("brand") or ""
            )
            
            if not wm_title:
                continue
            
            # Find best match in same category
            best_match = None
            best_score = 0.0
            
            for ss_idx, ss_product in ss_items:
                if ss_idx in superstore_matched or ss_idx in new_superstore_matched:
                    continue
                
                ss_brand = _normalize_brand(ss_product.get("brand") or "")
                ss_title = normalize_title_for_matching(
                    ss_product.get("title") or "",
                    ss_product.get("brand") or ""
                )
                
                if not ss_title:
                    continue
                
                # Calculate score
                title_sim = fuzzy_similarity(wm_title, ss_title)
                brand_match = 1.0 if (not wm_brand or not ss_brand or wm_brand == ss_brand) else 0.0
                
                # Combined score (weighted)
                score = (title_sim * 0.7) + (brand_match * 0.3)
                
                if score > 0.7 and score > best_score:  # Lower threshold for category matching
                    best_score = score
                    best_match = ss_idx
            
            if best_match is not None:
                matches.append((wm_idx, best_match, "low", f"category_match_{best_score:.2f}"))
                new_walmart_matched.add(wm_idx)
                new_superstore_matched.add(best_match)
    
    return matches, new_walmart_matched, new_superstore_matched


# -------------------------------------------------------------------
# Output Generation
# -------------------------------------------------------------------

def create_matched_product(walmart_product: Dict, superstore_product: Dict,
                          confidence: str, method: str) -> Dict[str, Any]:
    """
    Create a unified product record from a matched pair.
    """
    # Use the longer/more descriptive title
    wm_title = walmart_product.get("title") or walmart_product.get("product_name") or ""
    ss_title = superstore_product.get("title") or superstore_product.get("product_name") or ""
    title = max([wm_title, ss_title], key=len) if wm_title or ss_title else ""
    
    # Use first non-empty description
    description = (
        walmart_product.get("description") or 
        walmart_product.get("short_description") or
        superstore_product.get("description") or ""
    )
    
    # Common fields
    brand = walmart_product.get("brand") or superstore_product.get("brand") or ""
    
    # Image URL - prefer the one with better quality
    image_url = superstore_product.get("image_url") or walmart_product.get("image_url")
    
    # Calculate price difference
    wm_price = parse_price(walmart_product)
    ss_price = parse_price(superstore_product)
    
    price_difference = None
    price_difference_percent = None
    cheaper_store = None
    
    if wm_price is not None and ss_price is not None:
        price_difference = abs(wm_price - ss_price)
        avg_price = (wm_price + ss_price) / 2
        if avg_price > 0:
            price_difference_percent = (price_difference / avg_price) * 100
        
        if wm_price < ss_price - 0.01:  # Account for rounding
            cheaper_store = "walmart"
        elif ss_price < wm_price - 0.01:
            cheaper_store = "superstore"
        else:
            cheaper_store = "same"
    
    # Build the matched product
    matched = {
        # Common fields
        "brand": brand,
        "title": title,
        "description": description,
        "package_sizing": superstore_product.get("package_sizing") or walmart_product.get("package_sizing"),
        "image_url": image_url,
        
        # Match metadata
        "match_confidence": confidence,
        "match_method": method,
        "price_difference": round(price_difference, 2) if price_difference is not None else None,
        "price_difference_percent": round(price_difference_percent, 2) if price_difference_percent is not None else None,
        "cheaper_store": cheaper_store,
        
        # Store-specific offers
        "walmart_offer": {
            "store": "walmart",
            "store_name": "Walmart",
            "product_id": walmart_product.get("product_id") or walmart_product.get("item_id"),
            "article_number": walmart_product.get("article_number") or walmart_product.get("item_id"),
            "price": walmart_product.get("price"),
            "price_raw": walmart_product.get("price_raw"),
            "price_numeric": wm_price,
            "inventory_status": walmart_product.get("inventory_status") or walmart_product.get("availability"),
            "link": walmart_product.get("link") or walmart_product.get("product_url"),
            "image_url": walmart_product.get("image_url"),
            "review_count": walmart_product.get("review_count"),
            "avg_rating": walmart_product.get("avg_rating"),
            "search_query": walmart_product.get("search_query"),
            "offer_type": "OG",
            "is_sponsored": False,
        },
        
        "superstore_offer": {
            "store": "superstore",
            "store_name": "Real Canadian Superstore",
            "product_id": superstore_product.get("product_id"),
            "article_number": superstore_product.get("article_number"),
            "price": superstore_product.get("price"),
            "price_raw": superstore_product.get("price_raw"),
            "price_numeric": ss_price,
            "inventory_status": superstore_product.get("inventory_status"),
            "link": superstore_product.get("link"),
            "image_url": superstore_product.get("image_url"),
            "badge": superstore_product.get("badge"),
            "search_query": superstore_product.get("search_query"),
            "offer_type": superstore_product.get("offer_type", "OG"),
            "is_sponsored": superstore_product.get("is_sponsored", False),
        },
    }
    
    return matched


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main():
    print("\n" + "="*70)
    print("ADVANCED PRODUCT MATCHER")
    print("="*70)
    print("\nThis script finds matching products between Walmart and Superstore")
    print("using multi-stage matching algorithms.\n")
    
    # Ensure output directory exists
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load products
    print("📂 Loading product data...")
    walmart_products = load_products(WALMART_JSONL, "walmart")
    superstore_products = load_products(SUPERSTORE_JSONL, "superstore")
    
    print(f"   Walmart: {len(walmart_products):,} products")
    print(f"   Superstore: {len(superstore_products):,} products")
    
    if not walmart_products or not superstore_products:
        print("\n❌ Cannot proceed without data from both stores")
        return
    
    # Stage 1: Exact matching (brand + title + size)
    print("\n🔍 Stage 1: Exact matching (brand + title + size)...")
    exact_matches, walmart_matched, superstore_matched = exact_match(
        walmart_products, superstore_products
    )
    print(f"   Found {len(exact_matches):,} exact matches")
    
    # Stage 2: Brand + title matching (different sizes)
    print("\n🔍 Stage 2: Brand + title matching (ignoring size)...")
    brand_title_matches, new_wm_matched, new_ss_matched = brand_title_match(
        walmart_products, superstore_products,
        walmart_matched, superstore_matched
    )
    walmart_matched.update(new_wm_matched)
    superstore_matched.update(new_ss_matched)
    print(f"   Found {len(brand_title_matches):,} brand+title matches")
    
    # Stage 3: Fuzzy matching
    print("\n🔍 Stage 3: Fuzzy matching (similar titles)...")
    fuzzy_matches, new_wm_matched, new_ss_matched = fuzzy_match(
        walmart_products, superstore_products,
        walmart_matched, superstore_matched
    )
    walmart_matched.update(new_wm_matched)
    superstore_matched.update(new_ss_matched)
    print(f"   Found {len(fuzzy_matches):,} fuzzy matches")
    
    # Stage 4: Category-based matching
    print("\n🔍 Stage 4: Category-based matching (same search query)...")
    category_matches, new_wm_matched, new_ss_matched = category_match(
        walmart_products, superstore_products,
        walmart_matched, superstore_matched
    )
    walmart_matched.update(new_wm_matched)
    superstore_matched.update(new_ss_matched)
    print(f"   Found {len(category_matches):,} category matches")
    
    # Combine all matches
    all_matches = exact_matches + brand_title_matches + fuzzy_matches + category_matches
    
    print(f"\n📊 Total matches: {len(all_matches):,}")
    print(f"   High confidence: {len(exact_matches):,}")
    print(f"   Medium confidence: {len(brand_title_matches):,}")
    print(f"   Low confidence: {len(fuzzy_matches) + len(category_matches):,}")
    
    # Generate output
    print(f"\n💾 Writing matches to {OUTPUT_JSONL}...")
    
    matched_products = []
    for wm_idx, ss_idx, confidence, method in all_matches:
        matched = create_matched_product(
            walmart_products[wm_idx],
            superstore_products[ss_idx],
            confidence,
            method
        )
        matched_products.append(matched)
    
    # Sort by price difference (largest first) for easier review
    matched_products.sort(
        key=lambda x: x.get("price_difference") or 0,
        reverse=True
    )
    
    # Write output
    with OUTPUT_JSONL.open("w", encoding="utf-8") as f:
        for product in matched_products:
            f.write(json.dumps(product, ensure_ascii=False) + "\n")
    
    print(f"   ✅ Wrote {len(matched_products):,} matched products")
    
    # Statistics
    print("\n" + "="*70)
    print("MATCHING STATISTICS")
    print("="*70)
    
    print(f"\n📈 Match rate:")
    wm_rate = (len(walmart_matched) / len(walmart_products)) * 100 if walmart_products else 0
    ss_rate = (len(superstore_matched) / len(superstore_products)) * 100 if superstore_products else 0
    print(f"   Walmart: {len(walmart_matched):,}/{len(walmart_products):,} ({wm_rate:.1f}%)")
    print(f"   Superstore: {len(superstore_matched):,}/{len(superstore_products):,} ({ss_rate:.1f}%)")
    
    # Unmatched products
    unmatched_wm = len(walmart_products) - len(walmart_matched)
    unmatched_ss = len(superstore_products) - len(superstore_matched)
    print(f"\n📉 Unmatched products:")
    print(f"   Walmart: {unmatched_wm:,}")
    print(f"   Superstore: {unmatched_ss:,}")
    
    # Price comparison stats
    if matched_products:
        cheaper_walmart = sum(1 for p in matched_products if p.get("cheaper_store") == "walmart")
        cheaper_superstore = sum(1 for p in matched_products if p.get("cheaper_store") == "superstore")
        same_price = sum(1 for p in matched_products if p.get("cheaper_store") == "same")
        
        print(f"\n💰 Price comparison:")
        print(f"   Cheaper at Walmart: {cheaper_walmart:,} ({cheaper_walmart/len(matched_products)*100:.1f}%)")
        print(f"   Cheaper at Superstore: {cheaper_superstore:,} ({cheaper_superstore/len(matched_products)*100:.1f}%)")
        print(f"   Same price: {same_price:,} ({same_price/len(matched_products)*100:.1f}%)")
        
        # Average price difference
        price_diffs = [p.get("price_difference", 0) for p in matched_products if p.get("price_difference")]
        if price_diffs:
            avg_diff = sum(price_diffs) / len(price_diffs)
            max_diff = max(price_diffs)
            print(f"\n💵 Price differences:")
            print(f"   Average: ${avg_diff:.2f}")
            print(f"   Maximum: ${max_diff:.2f}")
        
        # Sample matches
        print(f"\n📋 Sample matches (top 5 by price difference):")
        for i, product in enumerate(matched_products[:5], 1):
            wm_price = product["walmart_offer"].get("price_numeric")
            ss_price = product["superstore_offer"].get("price_numeric")
            diff = product.get("price_difference", 0)
            diff_pct = product.get("price_difference_percent", 0)
            
            print(f"\n{i}. {product['brand']} - {product['title'][:60]}")
            if wm_price and ss_price:
                print(f"   Walmart: ${wm_price:.2f}")
                print(f"   Superstore: ${ss_price:.2f}")
                print(f"   Difference: ${diff:.2f} ({diff_pct:.1f}%)")
            print(f"   Confidence: {product['match_confidence']} ({product['match_method']})")
    
    # Save unmatched products for review
    if unmatched_wm > 0 or unmatched_ss > 0:
        unmatched_file = RAW_DIR / "unmatched_products.jsonl"
        
        print(f"\n📄 Writing unmatched products to {unmatched_file}...")
        
        with unmatched_file.open("w", encoding="utf-8") as f:
            # Write Walmart unmatched products
            for idx, p in enumerate(walmart_products):
                if idx not in walmart_matched:
                    unmatched_record = {
                        "store": "walmart",
                        "brand": p.get("brand", ""),
                        "title": p.get("title", ""),
                        "price": p.get("price", ""),
                        "price_numeric": parse_price(p),
                        "search_query": p.get("search_query", ""),
                        "link": p.get("link", ""),
                        "image_url": p.get("image_url", ""),
                        "product_id": p.get("product_id", ""),
                        "article_number": p.get("article_number", ""),
                        "package_sizing": p.get("package_sizing", ""),
                    }
                    f.write(json.dumps(unmatched_record, ensure_ascii=False) + "\n")
            
            # Write Superstore unmatched products
            for idx, p in enumerate(superstore_products):
                if idx not in superstore_matched:
                    unmatched_record = {
                        "store": "superstore",
                        "brand": p.get("brand", ""),
                        "title": p.get("title", ""),
                        "price": p.get("price", ""),
                        "price_numeric": parse_price(p),
                        "search_query": p.get("search_query", ""),
                        "link": p.get("link", ""),
                        "image_url": p.get("image_url", ""),
                        "product_id": p.get("product_id", ""),
                        "article_number": p.get("article_number", ""),
                        "package_sizing": p.get("package_sizing", ""),
                    }
                    f.write(json.dumps(unmatched_record, ensure_ascii=False) + "\n")
        
        print(f"   ✅ Wrote {unmatched_wm + unmatched_ss:,} unmatched products")
        print(f"   Review these for potential manual matching")
    
    # Match quality breakdown
    if matched_products:
        print(f"\n🎯 Match quality breakdown:")
        match_methods = defaultdict(int)
        for p in matched_products:
            method = p.get("match_method", "unknown")
            match_methods[method] += 1
        
        for method, count in sorted(match_methods.items(), key=lambda x: x[1], reverse=True):
            print(f"   {method}: {count:,} ({count/len(matched_products)*100:.1f}%)")
    
    print("\n" + "="*70)
    print("MATCHING COMPLETE!")
    print("="*70)
    print(f"\n✅ Output saved to: {OUTPUT_JSONL}")
    print(f"✅ Total matched products: {len(matched_products):,}")
    print(f"\n💡 Next step: Run build_frontend_json.py to prepare data for the frontend")
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()