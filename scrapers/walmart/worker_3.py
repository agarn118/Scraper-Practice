import sys
import signal
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import scraper_core

# ============================================================
# WORKER CONFIGURATION - CHANGE THESE FOR EACH WORKER
# ============================================================

WORKER_ID = 3  # Change to 2, 3, 4 for other workers
QUERIES = config.WORKER_1_QUERIES  # Change to WORKER_2_QUERIES, etc.

# ============================================================

shutdown_flag = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global shutdown_flag
    print(f"\n[Worker {WORKER_ID}] Shutdown signal received...")
    shutdown_flag = True

def run_worker():
    """Main worker function."""
    global shutdown_flag
    
    # Setup
    signal.signal(signal.SIGINT, signal_handler)
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print(f"WALMART SCRAPER - WORKER {WORKER_ID}")
    print("="*70)
    
    # Load existing products
    print(f"[Worker {WORKER_ID}] Loading existing products...")
    existing_ids, existing_urls = scraper_core.load_existing_products()
    seen_product_ids = set(existing_ids)
    seen_urls = set(existing_urls)
    print(f"[Worker {WORKER_ID}] Found {len(seen_product_ids)} existing product IDs")
    print(f"[Worker {WORKER_ID}] Found {len(seen_urls)} existing URLs")
    
    print("="*70)
    print(f"[Worker {WORKER_ID}] Assigned {len(QUERIES)} queries")
    print(f"[Worker {WORKER_ID}] Output: {config.OUTPUT_FILE}")
    print(f"[Worker {WORKER_ID}] Delays: {config.SLEEP_PRODUCT_MIN}-{config.SLEEP_PRODUCT_MAX}s per product")
    print("="*70)
    print(f"[Worker {WORKER_ID}] Press Ctrl+C to stop gracefully")
    print("="*70)
    
    # Create session
    session = scraper_core.create_session()
    
    # Tracking
    products_scraped = 0
    failed_queries = []
    product_retry_counts = {}
    failed_urls_final = set()
    
    # Process queries
    round_num = 1
    current_queries = list(QUERIES)
    start_time = time.time()
    
    while current_queries and round_num <= config.MAX_ROUNDS and not shutdown_flag:
        print(f"\n[Worker {WORKER_ID}] ===== ROUND {round_num} - {len(current_queries)} queries =====\n")
        
        round_failed_queries = []
        
        for query_idx, query in enumerate(current_queries):
            if shutdown_flag:
                break
            
            print(f"[Worker {WORKER_ID}] [{query_idx+1}/{len(current_queries)}] Query: '{query}'")
            
            # Delay between queries
            if query_idx > 0:
                scraper_core.sleep_between(config.SLEEP_QUERY_MIN, config.SLEEP_QUERY_MAX)
            
            page_number = 1
            products_for_query = 0
            query_had_errors = False
            query_had_retryable_failures = False
            expected_total = None
            
            while True:
                if shutdown_flag:
                    break
                
                if config.MAX_PAGES_PER_QUERY and page_number > config.MAX_PAGES_PER_QUERY:
                    break
                
                try:
                    links, total_results = scraper_core.get_product_links(session, query, page_number)
                    
                    if page_number == 1 and total_results:
                        expected_total = total_results
                        print(f"[Worker {WORKER_ID}]   Total results: {expected_total}")
                    
                except Exception as e:
                    print(f"[Worker {WORKER_ID}]   Error getting links: {type(e).__name__}")
                    query_had_errors = True
                    round_failed_queries.append(query)
                    break
                
                if not links:
                    if page_number == 1:
                        print(f"[Worker {WORKER_ID}]   ⚠ No products found (possible blocking)")
                        query_had_errors = True
                        round_failed_queries.append(query)
                    break
                
                print(f"[Worker {WORKER_ID}]   Page {page_number}: {len(links)} links found")
                
                # Process each product link
                for link_idx, link in enumerate(links):
                    if shutdown_flag:
                        break
                    
                    # Skip if already seen or failed
                    if link in seen_urls or link in failed_urls_final:
                        continue
                    
                    if config.MAX_PRODUCTS_PER_QUERY and products_for_query >= config.MAX_PRODUCTS_PER_QUERY:
                        break
                    
                    try:
                        product_info = scraper_core.extract_product_info(session, link)
                        
                        if product_info:
                            product_id = str(product_info.get("product_id", ""))
                            
                            # Skip if already have this product
                            if product_id and product_id in seen_product_ids:
                                continue
                            
                            # Prepare data
                            row = {"search_query": query}
                            row.update(product_info)
                            
                            # Write to file (thread-safe)
                            if scraper_core.write_product_to_file(row):
                                products_scraped += 1
                                products_for_query += 1
                                seen_urls.add(link)
                                
                                if product_id:
                                    seen_product_ids.add(product_id)
                                
                                # Progress update every 5 products
                                if products_scraped % 5 == 0:
                                    print(f"[Worker {WORKER_ID}]   ✓ Scraped {products_scraped} products so far")
                        
                    except Exception as e:
                        error_type = type(e).__name__
                        
                        if "403" in str(e) or "CAPTCHA" in str(e):
                            print(f"[Worker {WORKER_ID}]   ⚠ BLOCKED - Stopping")
                            query_had_errors = True
                            round_failed_queries.append(query)
                            break
                        
                        # Track retries
                        current_count = product_retry_counts.get(link, 0) + 1
                        product_retry_counts[link] = current_count
                        
                        if current_count >= config.MAX_PRODUCT_RETRIES:
                            failed_urls_final.add(link)
                        else:
                            query_had_retryable_failures = True
                    
                    # Delay between products
                    scraper_core.sleep_between(config.SLEEP_PRODUCT_MIN, config.SLEEP_PRODUCT_MAX)
                
                if query_had_errors:
                    break
                
                if config.MAX_PRODUCTS_PER_QUERY and products_for_query >= config.MAX_PRODUCTS_PER_QUERY:
                    break
                
                if shutdown_flag:
                    break
                
                # Next page
                page_number += 1
                scraper_core.sleep_between(config.SLEEP_PAGE_MIN, config.SLEEP_PAGE_MAX)
            
            # Check if query incomplete
            if expected_total and products_for_query < expected_total:
                print(f"[Worker {WORKER_ID}]   ⚠ Incomplete: {products_for_query}/{expected_total}")
                if not query_had_errors:
                    query_had_retryable_failures = True
            
            # Mark for retry if needed
            if query_had_retryable_failures and not query_had_errors:
                round_failed_queries.append(query)
        
        # Round complete
        print(f"\n[Worker {WORKER_ID}] ----- Round {round_num} Complete -----")
        print(f"[Worker {WORKER_ID}] Products scraped this round: {products_scraped}")
        print(f"[Worker {WORKER_ID}] Failed queries: {len(round_failed_queries)}")
        
        # Check if we should retry
        if not round_failed_queries:
            print(f"[Worker {WORKER_ID}] ✓ All queries completed!")
            break
        
        if shutdown_flag:
            break
        
        # Check for progress
        if set(round_failed_queries) == set(current_queries):
            print(f"[Worker {WORKER_ID}] ⚠ No progress made, stopping retries")
            break
        
        # Prepare next round
        if round_num < config.MAX_ROUNDS:
            print(f"[Worker {WORKER_ID}] Will retry {len(round_failed_queries)} queries in round {round_num + 1}")
            current_queries = list(set(round_failed_queries))  # Deduplicate
            round_num += 1
        else:
            print(f"[Worker {WORKER_ID}] ⚠ Max rounds reached")
            break
    
    # Final statistics
    elapsed = time.time() - start_time
    
    print("\n" + "="*70)
    print(f"[Worker {WORKER_ID}] SCRAPING COMPLETE")
    print("="*70)
    print(f"[Worker {WORKER_ID}] Total rounds: {round_num}")
    print(f"[Worker {WORKER_ID}] Total products scraped: {products_scraped}")
    print(f"[Worker {WORKER_ID}] Time elapsed: {elapsed/60:.1f} minutes")
    print(f"[Worker {WORKER_ID}] Output file: {config.OUTPUT_FILE}")
    print("="*70)
    
    session.close()

if __name__ == "__main__":
    run_worker()