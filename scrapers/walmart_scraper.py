from bs4 import BeautifulSoup
import requests
import json
import time
import random
from urllib.parse import quote_plus, urlparse
from pathlib import Path
from multiprocessing import Process, Manager, Lock, Queue
import signal
import sys
import re

# -------------- HTTP CONFIG -------------- #

# Rotating User-Agents (real browser strings)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

# Accept-Language variations
ACCEPT_LANGUAGES = [
    "en-CA,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9",
    "en-CA,en;q=0.8,fr-CA;q=0.6,fr;q=0.4",
    "en-GB,en-US;q=0.9,en;q=0.8",
]

TIMEOUT = 15  # Increased timeout
MAX_RETRIES = 3  # Retry failed requests

# -------------- PATHS -------------- #

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"

OUTPUT_FILE = RAW_DIR / "walmart_product_info.jsonl"

# -------------- GROCERY QUERIES -------------- #

GROCERY_QUERIES = [
    # Dairy
    "milk", "skim milk", "2% milk", "3.25% milk", "lactose free milk",
    "cream", "coffee cream", "whipping cream", "half and half",
    "butter", "margarine", "cheddar cheese", "mozzarella cheese",
    "shredded cheese", "cream cheese", "cottage cheese",
    "yogurt", "greek yogurt", "sour cream", "ice cream",
    # Eggs & breakfast
    "eggs", "egg whites", "bacon", "breakfast sausage", "hash browns",
    # Bakery
    "white bread", "whole wheat bread", "bagels", "english muffins",
    "tortillas", "naan", "hamburger buns", "hot dog buns",
    # Pantry staples
    "rice", "brown rice", "pasta", "spaghetti", "macaroni",
    "flour", "sugar", "brown sugar", "baking soda", "baking powder",
    "salt", "black pepper", "olive oil", "canola oil", "vegetable oil",
    "vinegar", "soy sauce", "ketchup", "mustard", "mayonnaise",
    "salad dressing", "peanut butter", "jam", "honey",
    # Canned & jarred
    "canned soup", "canned tomatoes", "canned beans",
    "canned tuna", "canned salmon", "pasta sauce",
    # Frozen
    "frozen vegetables", "frozen fruit", "frozen pizza",
    "frozen fries", "frozen chicken nuggets",
    # Meat
    "chicken breast", "chicken thighs", "whole chicken",
    "ground beef", "steak", "pork chops", "ground pork",
    "ground turkey", "ham", "sausages",
    # Produce
    "apples", "bananas", "oranges", "grapes", "strawberries",
    "blueberries", "broccoli", "cauliflower", "carrots",
    "onions", "potatoes", "sweet potatoes", "lettuce",
    "spinach", "kale", "tomatoes", "cucumbers", "bell peppers",
    # Snacks
    "potato chips", "tortilla chips", "popcorn", "crackers",
    "cookies", "chocolate", "granola bars", "nuts", "trail mix",
    # Drinks
    "coffee", "instant coffee", "tea", "orange juice",
    "apple juice", "soft drinks", "energy drinks",
    "water", "mineral water", "bottled water", "sparkling water",
]

# -------------- CONFIG -------------- #

NUM_WORKERS = 2  # Reduced workers to be less aggressive
MAX_PAGES_PER_QUERY = None
MAX_PRODUCTS_PER_QUERY = None
MAX_PRODUCT_RETRIES = 3
MAX_ROUNDS = 3

# INCREASED DELAYS to appear more human
SLEEP_PRODUCT_MIN = 1.5  # Increased from 0.2
SLEEP_PRODUCT_MAX = 3.5  # Increased from 0.6
SLEEP_PAGE_MIN = 3.0     # Increased from 0.4
SLEEP_PAGE_MAX = 6.0     # Increased from 1.2
SLEEP_QUERY_MIN = 5.0    # NEW: Delay between queries
SLEEP_QUERY_MAX = 10.0

# Global flag for graceful shutdown
shutdown_flag = False

# -------------- HELPERS -------------- #

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global shutdown_flag
    print("\n\nShutdown signal received. Finishing current tasks...")
    shutdown_flag = True

def sleep_between(low: float, high: float) -> None:
    """Randomized sleep with occasional longer pauses."""
    base_sleep = random.uniform(low, high)
    # 10% chance of taking an extra long break (simulate human distraction)
    if random.random() < 0.1:
        base_sleep *= random.uniform(2, 4)
        print(f"  [Taking extended break: {base_sleep:.1f}s]")
    time.sleep(base_sleep)

def get_random_headers(referer=None):
    """Generate realistic browser headers."""
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "User-Agent": random.choice(USER_AGENTS),
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }
    
    if referer:
        headers["Referer"] = referer
    
    return headers

def create_session():
    """Create a session with realistic settings."""
    session = requests.Session()
    
    # Set connection pool size
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=10,
        pool_maxsize=20,
        max_retries=0  # We handle retries manually
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    return session

def load_existing_products(output_file):
    """Load already scraped product IDs and URLs from the output file."""
    existing_ids = set()
    existing_urls = set()
    
    if not output_file.exists():
        return existing_ids, existing_urls
    
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        if "product_id" in data and data["product_id"]:
                            existing_ids.add(str(data["product_id"]))
                        if "link" in data and data["link"]:
                            existing_urls.add(data["link"])
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"Warning: Could not load existing products: {e}")
    
    return existing_ids, existing_urls

def extract_total_results(soup):
    """Extract total number of results from search page."""
    try:
        # Look for "Results for 'query' (95)" pattern
        results_text = soup.find(string=re.compile(r"Results for.*\(\d+\)"))
        if results_text:
            match = re.search(r"\((\d+)\)", results_text)
            if match:
                return int(match.group(1))
    except:
        pass
    
    return None

def make_request_with_retry(session, url, headers, max_retries=MAX_RETRIES):
    """Make HTTP request with retry logic and better error handling."""
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            # Add jitter to retry delays
            if attempt > 0:
                retry_delay = random.uniform(5, 15) * (attempt + 1)
                print(f"  [Retry {attempt + 1}/{max_retries} after {retry_delay:.1f}s]")
                time.sleep(retry_delay)
            
            resp = session.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
            
            # Check for common blocking indicators
            if resp.status_code == 403:
                print(f"  [403 Forbidden - likely blocked by anti-bot]")
                raise requests.exceptions.HTTPError("403 Forbidden - Bot detection")
            
            if resp.status_code == 429:
                print(f"  [429 Too Many Requests - rate limited]")
                retry_after = int(resp.headers.get('Retry-After', 60))
                time.sleep(min(retry_after, 120))
                continue
            
            # Check for CAPTCHA or verification page
            if 'captcha' in resp.url.lower() or 'verify' in resp.url.lower():
                print(f"  [CAPTCHA/Verification page detected]")
                raise requests.exceptions.HTTPError("CAPTCHA required")
            
            # Check for empty or blocked content
            if len(resp.content) < 1000:
                print(f"  [Suspiciously small response: {len(resp.content)} bytes]")
                if attempt < max_retries - 1:
                    continue
            
            resp.raise_for_status()
            return resp
            
        except requests.exceptions.Timeout as e:
            last_exception = e
            print(f"  [Timeout on attempt {attempt + 1}]")
        except requests.exceptions.ConnectionError as e:
            last_exception = e
            print(f"  [Connection error on attempt {attempt + 1}]")
        except requests.exceptions.HTTPError as e:
            last_exception = e
            if attempt >= max_retries - 1:
                raise
        except Exception as e:
            last_exception = e
            print(f"  [Unexpected error: {e}]")
    
    raise last_exception if last_exception else Exception("Max retries exceeded")

def get_product_links(session, query: str, page_number: int = 1):
    """Fetch product links for a search query and total result count."""
    encoded_query = quote_plus(query)
    search_url = f"https://www.walmart.ca/en/search?q={encoded_query}&page={page_number}"
    
    # Use referer for page 2+
    referer = f"https://www.walmart.ca/en/search?q={encoded_query}&page={page_number-1}" if page_number > 1 else None
    headers = get_random_headers(referer=referer)
    
    resp = make_request_with_retry(session, search_url, headers)
    
    # Add small delay to mimic reading the page
    time.sleep(random.uniform(0.5, 1.5))
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Extract total results on first page
    total_results = None
    if page_number == 1:
        total_results = extract_total_results(soup)
    
    # Debug: Save HTML to check what we're getting
    if page_number == 1:
        debug_file = RAW_DIR / f"debug_search_{query.replace(' ', '_')}.html"
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"  [Debug: Saved search page HTML to {debug_file}]")
    
    links = soup.find_all("a", href=True)
    
    product_links = []
    for link in links:
        href = link["href"]
        if "wapcrs/track" in href:
            continue
        if "/ip" in href or "/ip/" in href:
            if href.startswith("http"):
                full_url = href
            else:
                full_url = "https://www.walmart.ca" + href
            # Remove duplicates
            if full_url not in product_links:
                product_links.append(full_url)
    
    return product_links, total_results

def _fmt_price(v):
    """Format a numeric price."""
    if v is None:
        return None, None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None, None
    return f"${f:.2f}", f"{f:.2f}"

def extract_product_info(session, product_url: str):
    """Extract product data from Walmart product page."""
    headers = get_random_headers(referer="https://www.walmart.ca/en/search")
    
    resp = make_request_with_retry(session, product_url, headers)
    
    # Mimic reading product page
    time.sleep(random.uniform(0.5, 2.0))
    
    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    
    if not script_tag or not script_tag.string:
        # Debug: Save HTML
        debug_file = RAW_DIR / f"debug_product_{urlparse(product_url).path.split('/')[-1]}.html"
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"  [Debug: Saved product page HTML to {debug_file}]")
        raise ValueError("Could not find __NEXT_DATA__ script tag")
    
    data = json.loads(script_tag.string)
    initial_data = data["props"]["pageProps"]["initialData"]["data"]
    product_data = initial_data["product"]
    reviews_data = initial_data.get("reviews", {}) or {}
    
    price_info = product_data.get("priceInfo", {}) or {}
    curr = price_info.get("currentPrice") or {}
    price_val = curr.get("price")
    
    was_price_val = None
    was = price_info.get("wasPrice") or price_info.get("comparisonPrice") or {}
    if isinstance(was, dict):
        was_price_val = was.get("price")
    
    price_str, price_raw = _fmt_price(price_val)
    was_price_str, _ = _fmt_price(was_price_val)
    
    us_item_id = product_data.get("usItemId")
    sku_id = product_data.get("skuId")
    title = product_data.get("name") or ""
    brand = product_data.get("brand") or ""
    availability = product_data.get("availabilityStatus") or ""
    image_url = (product_data.get("imageInfo") or {}).get("thumbnailUrl")
    short_desc = product_data.get("shortDescription") or ""
    
    package_sizing = (
        product_data.get("size")
        or (product_data.get("productAttributes") or {}).get("size")
    )
    
    product_info = {
        "product_id": us_item_id,
        "article_number": us_item_id or sku_id,
        "brand": brand,
        "title": title,
        "description": short_desc,
        "package_sizing": package_sizing,
        "link": product_url,
        "price": price_str if price_str is not None else price_val,
        "was_price": was_price_str,
        "price_raw": price_raw,
        "inventory_status": availability,
        "image_url": image_url,
        "offer_type": "OG",
        "is_sponsored": False,
        "price_numeric": float(price_raw) if price_raw else None,
        "review_count": reviews_data.get("totalReviewCount", 0),
        "avg_rating": reviews_data.get("averageOverallRating"),
    }
    
    return product_info

def worker_process(worker_id, queries, seen_urls, seen_product_ids, product_retry_counts, 
                   failed_urls_final, file_lock, output_file, stats_queue, round_num):
    """Worker process that scrapes assigned queries and returns failed queries."""
    global shutdown_flag
    
    session = create_session()
    local_seen = set()
    products_scraped = 0
    failed_queries = []
    query_stats = {}
    
    print(f"[Worker {worker_id}] [Round {round_num}] Starting with {len(queries)} queries")
    
    try:
        for query_idx, query in enumerate(queries):
            if shutdown_flag:
                print(f"[Worker {worker_id}] Shutdown requested, stopping...")
                break
                
            page_number = 1
            products_for_query = 0
            query_had_errors = False
            query_had_retryable_failures = False
            expected_total = None
            
            print(f"[Worker {worker_id}] [Round {round_num}] [{query_idx+1}/{len(queries)}] Searching '{query}'")
            
            # Delay between queries (simulate human browsing)
            if query_idx > 0:
                sleep_between(SLEEP_QUERY_MIN, SLEEP_QUERY_MAX)
            
            while True:
                if shutdown_flag:
                    break
                    
                if MAX_PAGES_PER_QUERY is not None and page_number > MAX_PAGES_PER_QUERY:
                    break
                
                try:
                    links, total_results = get_product_links(session, query, page_number)
                    
                    if page_number == 1 and total_results is not None:
                        expected_total = total_results
                        print(f"[Worker {worker_id}] Query '{query}' has {expected_total} total results")
                        
                except requests.exceptions.HTTPError as e:
                    if "403" in str(e) or "CAPTCHA" in str(e):
                        print(f"[Worker {worker_id}] ⚠ BLOCKED for '{query}' - Anti-bot detection triggered")
                        query_had_errors = True
                        failed_queries.append(query)
                        break
                    print(f"[Worker {worker_id}] HTTP error for '{query}' page {page_number}: {e}")
                    query_had_errors = True
                    failed_queries.append(query)
                    break
                except Exception as e:
                    print(f"[Worker {worker_id}] Unexpected error for '{query}' page {page_number}: {e}")
                    query_had_errors = True
                    failed_queries.append(query)
                    break
                
                if not links:
                    if page_number == 1:
                        print(f"[Worker {worker_id}] ⚠ No products found for '{query}' - possible blocking")
                        failed_queries.append(query)
                        query_had_errors = True
                    break
                
                print(f"[Worker {worker_id}] Query '{query}', page {page_number}, found {len(links)} links")
                
                for link_idx, link in enumerate(links):
                    if shutdown_flag:
                        break
                        
                    if link in seen_urls or link in failed_urls_final:
                        continue
                    
                    if MAX_PRODUCTS_PER_QUERY is not None and products_for_query >= MAX_PRODUCTS_PER_QUERY:
                        break
                    
                    # Progress indicator every 5 products
                    if link_idx > 0 and link_idx % 5 == 0:
                        print(f"[Worker {worker_id}]   Processing product {link_idx + 1}/{len(links)}...")
                    
                    try:
                        product_info = extract_product_info(session, link)
                        if product_info:
                            product_id = str(product_info.get("product_id", ""))
                            
                            if product_id and product_id in seen_product_ids:
                                print(f"[Worker {worker_id}] Skipping duplicate product ID: {product_id}")
                                continue
                            
                            row = {"search_query": query}
                            row.update(product_info)
                            
                            with file_lock:
                                with open(output_file, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                            
                            products_for_query += 1
                            products_scraped += 1
                            local_seen.add(link)
                            seen_urls[link] = True
                            
                            if product_id:
                                seen_product_ids[product_id] = True
                            
                    except requests.exceptions.HTTPError as e:
                        if "403" in str(e) or "CAPTCHA" in str(e):
                            print(f"[Worker {worker_id}] ⚠ BLOCKED - Stopping to avoid further detection")
                            query_had_errors = True
                            failed_queries.append(query)
                            break
                        
                        if hasattr(e, 'response') and e.response and e.response.status_code == 404:
                            failed_urls_final[link] = True
                        else:
                            current_count = product_retry_counts.get(link, 0) + 1
                            product_retry_counts[link] = current_count
                            if current_count >= MAX_PRODUCT_RETRIES:
                                failed_urls_final[link] = True
                            else:
                                query_had_retryable_failures = True
                                
                    except Exception as e:
                        print(f"[Worker {worker_id}] Failed URL {link}: {type(e).__name__}")
                        current_count = product_retry_counts.get(link, 0) + 1
                        product_retry_counts[link] = current_count
                        if current_count >= MAX_PRODUCT_RETRIES:
                            failed_urls_final[link] = True
                        else:
                            query_had_retryable_failures = True
                    
                    sleep_between(SLEEP_PRODUCT_MIN, SLEEP_PRODUCT_MAX)
                
                if query_had_errors:
                    break
                
                if MAX_PRODUCTS_PER_QUERY is not None and products_for_query >= MAX_PRODUCTS_PER_QUERY:
                    break
                
                if shutdown_flag:
                    break
                    
                page_number += 1
                sleep_between(SLEEP_PAGE_MIN, SLEEP_PAGE_MAX)
            
            query_stats[query] = {
                'expected': expected_total,
                'scraped': products_for_query
            }
            
            if expected_total is not None and products_for_query < expected_total:
                print(f"[Worker {worker_id}] ⚠ Query '{query}': got {products_for_query}/{expected_total} products")
                if not query_had_errors:
                    query_had_retryable_failures = True
            
            if query_had_retryable_failures and not query_had_errors:
                failed_queries.append(query)
    
    finally:
        stats_queue.put({
            'worker_id': worker_id,
            'round': round_num,
            'products_scraped': products_scraped,
            'unique_products': len(local_seen),
            'failed_queries': failed_queries,
            'query_stats': query_stats
        })
        
        print(f"[Worker {worker_id}] [Round {round_num}] Completed. Scraped {products_scraped} products")
        session.close()

def run_round(queries, seen_urls, seen_product_ids, product_retry_counts, 
              failed_urls_final, file_lock, output_file, round_num):
    """Run one parallel scraping round and return failed queries."""
    
    queries_per_worker = len(queries) // NUM_WORKERS
    query_chunks = []
    
    for i in range(NUM_WORKERS):
        start_idx = i * queries_per_worker
        if i == NUM_WORKERS - 1:
            end_idx = len(queries)
        else:
            end_idx = (i + 1) * queries_per_worker
        query_chunks.append(queries[start_idx:end_idx])
    
    manager = Manager()
    stats_queue = manager.Queue()
    
    processes = []
    
    for i in range(NUM_WORKERS):
        if not query_chunks[i]:
            continue
            
        p = Process(
            target=worker_process,
            args=(i+1, query_chunks[i], seen_urls, seen_product_ids, 
                  product_retry_counts, failed_urls_final, file_lock, 
                  output_file, stats_queue, round_num)
        )
        p.start()
        processes.append(p)
    
    for p in processes:
        p.join()
    
    all_failed_queries = []
    total_products_this_round = 0
    all_query_stats = {}
    
    while not stats_queue.empty():
        stats = stats_queue.get()
        print(f"\n[Worker {stats['worker_id']}] [Round {round_num}] Stats:")
        print(f"  - Products scraped: {stats['products_scraped']}")
        print(f"  - Unique products: {stats['unique_products']}")
        print(f"  - Failed queries: {len(stats['failed_queries'])}")
        
        total_products_this_round += stats['products_scraped']
        all_failed_queries.extend(stats['failed_queries'])
        all_query_stats.update(stats['query_stats'])
    
    print(f"\n{'='*70}")
    print("QUERY COMPLETION SUMMARY")
    print(f"{'='*70}")
    for query, stats in sorted(all_query_stats.items()):
        if stats['expected'] is not None:
            percentage = (stats['scraped'] / stats['expected'] * 100) if stats['expected'] > 0 else 0
            status = "✓" if percentage >= 95 else "⚠"
            print(f"{status} '{query}': {stats['scraped']}/{stats['expected']} ({percentage:.1f}%)")
        else:
            print(f"? '{query}': {stats['scraped']} products (total unknown)")
    
    unique_failed = []
    seen_failed = set()
    for q in all_failed_queries:
        if q not in seen_failed:
            unique_failed.append(q)
            seen_failed.add(q)
    
    return unique_failed, total_products_this_round

def main():
    global shutdown_flag
    
    signal.signal(signal.SIGINT, signal_handler)
    
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print(f"WALMART ENHANCED ANTI-DETECTION SCRAPER - {NUM_WORKERS} Workers")
    print("="*70)
    print("⚠ IMPORTANT: Walmart has strong anti-bot protection")
    print("⚠ This scraper uses enhanced techniques but may still be blocked")
    print("⚠ Debug HTML files will be saved to help diagnose issues")
    print("="*70)
    
    print("Loading existing products from file...")
    existing_ids, existing_urls = load_existing_products(OUTPUT_FILE)
    print(f"Found {len(existing_ids)} existing product IDs")
    print(f"Found {len(existing_urls)} existing URLs")
    
    print("="*70)
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Total queries: {len(GROCERY_QUERIES)}")
    print(f"Max rounds: {MAX_ROUNDS}")
    print(f"Delays: {SLEEP_PRODUCT_MIN}-{SLEEP_PRODUCT_MAX}s per product")
    print(f"        {SLEEP_PAGE_MIN}-{SLEEP_PAGE_MAX}s per page")
    print(f"        {SLEEP_QUERY_MIN}-{SLEEP_QUERY_MAX}s between queries")
    print("="*70)
    print("Press Ctrl+C to stop gracefully")
    print("="*70)
    
    manager = Manager()
    seen_urls = manager.dict()
    seen_product_ids = manager.dict()
    product_retry_counts = manager.dict()
    failed_urls_final = manager.dict()
    file_lock = manager.Lock()
    
    for url in existing_urls:
        seen_urls[url] = True
    for pid in existing_ids:
        seen_product_ids[pid] = True
    
    current_queries = list(GROCERY_QUERIES)
    round_num = 1
    overall_start_time = time.time()
    
    while current_queries and round_num <= MAX_ROUNDS and not shutdown_flag:
        print("\n" + "="*70)
        print(f"ROUND {round_num} - {len(current_queries)} queries to process")
        print("="*70)
        
        round_start_time = time.time()
        
        failed_queries, products_scraped = run_round(
            current_queries, 
            seen_urls,
            seen_product_ids,
            product_retry_counts,
            failed_urls_final,
            file_lock, 
            OUTPUT_FILE,
            round_num
        )
        
        round_elapsed = time.time() - round_start_time
        
        print("\n" + "-"*70)
        print(f"ROUND {round_num} COMPLETE")
        print(f"Time: {round_elapsed/60:.1f} minutes")
        print(f"Products scraped this round: {products_scraped}")
        print(f"Total unique products: {len(seen_product_ids)}")
        print(f"Failed queries: {len(failed_queries)}")
        print("-"*70)
        
        if not failed_queries:
            print("\n✓ All queries completed successfully!")
            break
        
        if shutdown_flag:
            print("\n⚠ Shutdown requested")
            break
            
        if set(failed_queries) == set(current_queries):
            print("\n⚠ No progress made on failing queries. Stopping retries.")
            print(f"Permanently failed queries: {len(failed_queries)}")
            for q in failed_queries[:20]:
                print(f"  - {q}")
            if len(failed_queries) > 20:
                print(f"  ... and {len(failed_queries) - 20} more")
            break
        
        if round_num < MAX_ROUNDS:
            print(f"\nWill retry {len(failed_queries)} failed queries in round {round_num + 1}:")
            for q in failed_queries[:10]:
                print(f"  - {q}")
            if len(failed_queries) > 10:
                print(f"  ... and {len(failed_queries) - 10} more")
            
            current_queries = failed_queries
            round_num += 1
        else:
            print(f"\n⚠ Reached maximum rounds ({MAX_ROUNDS})")
            print(f"Remaining failed queries: {len(failed_queries)}")
            break
    
    total_elapsed = time.time() - overall_start_time
    
    print("\n" + "="*70)
    print("SCRAPING COMPLETE")
    print("="*70)
    print(f"Total rounds: {round_num}")
    print(f"Total unique products: {len(seen_product_ids)}")
    print(f"Total unique URLs: {len(seen_urls)}")
    print(f"Total failed URLs (permanent): {len(failed_urls_final)}")
    print(f"Total time: {total_elapsed/60:.1f} minutes")
    print(f"Output file: {OUTPUT_FILE}")
    
    if len(seen_product_ids) == 0:
        print("\n" + "!"*70)
        print("⚠ WARNING: NO PRODUCTS WERE SCRAPED")
        print("!"*70)
        print("\nPossible reasons:")
        print("1. Walmart detected the bot and blocked all requests")
        print("2. Website structure has changed")
        print("3. CAPTCHA is being triggered")
        print("\nCheck the debug HTML files in the data/raw/ folder")
        print("Look for files like 'debug_search_milk.html'")
        print("\nSuggestions:")
        print("- Try running with NUM_WORKERS = 1 (single worker)")
        print("- Increase delays even more")
        print("- Consider using a proxy service")
        print("- Try scraping during off-peak hours")
    
    print("="*70)

if __name__ == "__main__":
    main()