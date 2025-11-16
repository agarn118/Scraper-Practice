#!/usr/bin/env python3
"""
Master scraper that runs both store scrapers in sequence.
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRAPERS_DIR = BASE_DIR / "scrapers"
DATA_RAW_DIR = BASE_DIR / "data" / "raw"

SUPERSTORE_SCRAPER = SCRAPERS_DIR / "superstore_scraper.py"
WALMART_SCRAPER = SCRAPERS_DIR / "walmart_scraper.py"

SUPERSTORE_OUTPUT = DATA_RAW_DIR / "superstore_product_info.jsonl"
WALMART_OUTPUT = DATA_RAW_DIR / "walmart_product_info.jsonl"


def count_lines(file_path):
    """Count lines in a JSONL file."""
    if not file_path.exists():
        return 0
    with open(file_path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def run_scraper(script_path, name):
    """Run a scraper script."""
    print(f"\n{'='*70}")
    print(f"RUNNING {name}")
    print(f"{'='*70}\n")
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            cwd=SCRAPERS_DIR  # Run from scrapers directory
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {name} failed with error code {e.returncode}")
        return False
    except Exception as e:
        print(f"\n❌ Error running {name}: {e}")
        return False


def print_summary():
    """Print final summary statistics."""
    print("\n" + "="*70)
    print("SCRAPING SUMMARY")
    print("="*70)
    
    superstore_count = count_lines(SUPERSTORE_OUTPUT)
    walmart_count = count_lines(WALMART_OUTPUT)
    
    print(f"\n📊 Products scraped:")
    print(f"  Superstore: {superstore_count:,} products")
    print(f"  Walmart:    {walmart_count:,} products")
    print(f"  Total:      {superstore_count + walmart_count:,} products")
    
    print(f"\n📁 Output files:")
    print(f"  {SUPERSTORE_OUTPUT}")
    print(f"  {WALMART_OUTPUT}")


def main():
    print("\n" + "="*70)
    print("MASTER GROCERY SCRAPER")
    print("="*70)
    print("\nThis will scrape both Superstore and Walmart in sequence.")
    
    # Ensure data directory exists
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    # Ensure scrapers exist
    if not SUPERSTORE_SCRAPER.exists():
        print(f"\n❌ Superstore scraper not found: {SUPERSTORE_SCRAPER}")
        return
    
    if not WALMART_SCRAPER.exists():
        print(f"\n❌ Walmart scraper not found: {WALMART_SCRAPER}")
        return
    
    # Step 1: Run Superstore scraper
    print("\n[1/2] Starting Superstore scraper...")
    if not run_scraper(SUPERSTORE_SCRAPER, "SUPERSTORE SCRAPER"):
        print("\n⚠️  Superstore scraper failed, but continuing...")
    else:
        print(f"\n✅ Superstore scraper completed: {count_lines(SUPERSTORE_OUTPUT):,} products")
    
    # Step 2: Run Walmart scraper
    print("\n[2/2] Starting Walmart scraper...")
    if not run_scraper(WALMART_SCRAPER, "WALMART SCRAPER"):
        print("\n⚠️  Walmart scraper failed.")
    else:
        print(f"\n✅ Walmart scraper completed: {count_lines(WALMART_OUTPUT):,} products")
    
    # Step 3: Print summary
    print_summary()
    
    print("\n" + "="*70)
    print("SCRAPING COMPLETE!")
    print("="*70)
    print("\n📌 Next steps:")
    print("  1. Run: python tools/build_frontend_json.py")
    print("     This merges the data and detects duplicates across stores")
    print("\n  2. Run: python app.py")
    print("     This starts the web interface")


if __name__ == "__main__":
    main()