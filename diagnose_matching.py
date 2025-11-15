#!/usr/bin/env python3
"""
diagnose_matching.py

Diagnostic tool to understand why products aren't matching across stores.
Run this to see what's happening with your normalization.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Import the normalization functions from your build script
# Adjust the path if needed
sys.path.insert(0, str(Path(__file__).parent))

# Copy the normalization functions here for standalone use
import re
import unicodedata

def _strip_accents_lower(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()

def _normalize_brand(brand: str) -> str:
    if not brand:
        return ""
    s = _strip_accents_lower(brand)
    s = re.sub(r"[^a-z0-9\s]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    
    # Brand aliases
    BRAND_ALIASES = {
        "pc": {"presidents choice", "president's choice", "presidents choice", "pc"},
        "no name": {"no name", "noname", "nn"},
        "milk2go": {"milk2go", "milk 2 go", "milk2 go"},
    }
    
    for canonical, aliases in BRAND_ALIASES.items():
        if s in aliases:
            return canonical
    
    return s

def _remove_size_tokens(text: str) -> str:
    patterns = [
        r"\b\d+(?:\.\d+)?\s*(?:ml|l|litre|litres|g|kg|oz|fl\s*oz|lb|lbs)\b",
        r"\b\d+\s*[x×]\s*\d+(?:\.\d+)?\s*(?:ml|l|litre|litres|g|kg|oz|fl\s*oz|lb|lbs)\b",
        r"\b\d+\s*(?:pack|pk|count|ct|bottle|bottles|can|cans|carton|cartons|bag|bags)\b",
    ]
    s = text
    for pat in patterns:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _normalize_title_core(title: str, brand: str) -> str:
    STOPWORDS = {"and", "the", "of", "for", "in", "to", "a", "an", "with"}
    
    if not title:
        return ""
    
    s = _strip_accents_lower(title)
    s = re.sub(r"[^a-z0-9%\s]+", " ", s)
    
    # Remove brand
    if brand:
        brand_normalized = _normalize_brand(brand)
        brand_pattern = re.escape(_strip_accents_lower(brand))
        s = re.sub(rf"\b{brand_pattern}\b", " ", s)
        if brand_normalized:
            s = re.sub(rf"\b{brand_normalized}\b", " ", s)
    
    s = _remove_size_tokens(s)
    
    tokens = re.findall(r"[a-z0-9%]+", s)
    filtered = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    
    if not filtered:
        return ""
    
    filtered.sort()
    return " ".join(filtered)

def _make_key(brand: str, title: str) -> str:
    brand_key = _normalize_brand(brand)
    title_key = _normalize_title_core(title, brand)
    return f"{brand_key}|||{title_key}"


def diagnose_files(walmart_path: Path, superstore_path: Path, sample_size: int = 20):
    """Analyze matching between files."""
    
    print("=" * 80)
    print("PRODUCT MATCHING DIAGNOSTIC")
    print("=" * 80)
    
    # Load samples from each store
    walmart_products = []
    superstore_products = []
    
    print("\n📦 Loading Walmart products...")
    if walmart_path.exists():
        with walmart_path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= sample_size:
                    break
                try:
                    walmart_products.append(json.loads(line.strip()))
                except:
                    pass
        print(f"   Loaded {len(walmart_products)} samples")
    else:
        print(f"   ❌ File not found: {walmart_path}")
    
    print("\n📦 Loading Superstore products...")
    if superstore_path.exists():
        with superstore_path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= sample_size:
                    break
                try:
                    superstore_products.append(json.loads(line.strip()))
                except:
                    pass
        print(f"   Loaded {len(superstore_products)} samples")
    else:
        print(f"   ❌ File not found: {superstore_path}")
    
    # Show sample products with their keys
    print("\n" + "=" * 80)
    print("WALMART SAMPLES")
    print("=" * 80)
    for i, p in enumerate(walmart_products[:5], 1):
        brand = p.get("brand", "")
        title = p.get("title", "")
        match_key = _make_key(brand, title)
        
        print(f"\n{i}. Original:")
        print(f"   Brand: {brand}")
        print(f"   Title: {title}")
        print(f"   Match Key: {match_key}")
    
    print("\n" + "=" * 80)
    print("SUPERSTORE SAMPLES")
    print("=" * 80)
    for i, p in enumerate(superstore_products[:5], 1):
        brand = p.get("brand", "")
        title = p.get("title", "")
        match_key = _make_key(brand, title)
        
        print(f"\n{i}. Original:")
        print(f"   Brand: {brand}")
        print(f"   Title: {title}")
        print(f"   Match Key: {match_key}")
    
    # Find potential matches
    print("\n" + "=" * 80)
    print("LOOKING FOR MATCHES")
    print("=" * 80)
    
    walmart_keys = {_make_key(p.get("brand", ""), p.get("title", "")): p 
                    for p in walmart_products}
    superstore_keys = {_make_key(p.get("brand", ""), p.get("title", "")): p 
                       for p in superstore_products}
    
    matches = set(walmart_keys.keys()) & set(superstore_keys.keys())
    
    print(f"\n✅ Found {len(matches)} matches in sample of {sample_size}")
    
    if matches:
        print("\n🎯 Example matches:")
        for i, key in enumerate(list(matches)[:3], 1):
            w = walmart_keys[key]
            s = superstore_keys[key]
            print(f"\n{i}. Match Key: {key}")
            print(f"   Walmart:    {w.get('brand')} - {w.get('title')}")
            print(f"   Superstore: {s.get('brand')} - {s.get('title')}")
    
    # Analyze why things don't match
    print("\n" + "=" * 80)
    print("ANALYSIS: Why products don't match")
    print("=" * 80)
    
    # Count brand mismatches
    walmart_brands = defaultdict(int)
    superstore_brands = defaultdict(int)
    
    for p in walmart_products:
        brand = _normalize_brand(p.get("brand", ""))
        if brand:
            walmart_brands[brand] += 1
    
    for p in superstore_products:
        brand = _normalize_brand(p.get("brand", ""))
        if brand:
            superstore_brands[brand] += 1
    
    common_brands = set(walmart_brands.keys()) & set(superstore_brands.keys())
    
    print(f"\n📊 Brand overlap:")
    print(f"   Walmart unique brands: {len(walmart_brands)}")
    print(f"   Superstore unique brands: {len(superstore_brands)}")
    print(f"   Common brands: {len(common_brands)}")
    
    if common_brands:
        print(f"\n   Common brands: {', '.join(sorted(common_brands)[:10])}")


if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data" / "raw"
    
    walmart_file = DATA_DIR / "walmart_product_info.jsonl"
    superstore_file = DATA_DIR / "superstore_product_info.jsonl"
    
    # Check if files exist
    if not walmart_file.exists() or not superstore_file.exists():
        print("❌ Error: Could not find JSONL files")
        print(f"   Looking for:")
        print(f"   - {walmart_file}")
        print(f"   - {superstore_file}")
        sys.exit(1)
    
    # Run diagnostics
    diagnose_files(walmart_file, superstore_file, sample_size=100)
    
    print("\n" + "=" * 80)
    print("💡 RECOMMENDATIONS:")
    print("=" * 80)
    print("1. Check if brands are spelled the same across stores")
    print("2. Look for title differences (e.g., '2%' vs 'Partly Skimmed')")
    print("3. Consider adding more brand aliases to BRAND_ALIASES")
    print("4. If stores use completely different product naming, may need fuzzy matching")