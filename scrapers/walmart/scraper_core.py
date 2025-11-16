"""
Walmart Scraper - Core Functions
File: scrapers/walmart/scraper_core.py
"""
from bs4 import BeautifulSoup
import requests
import json
import time
import random
from urllib.parse import quote_plus, urlparse
import re
import platform
import config

# Windows-compatible file locking
if platform.system() == 'Windows':
    import msvcrt
    HAS_FCNTL = False
else:
    import fcntl
    HAS_FCNTL = True

# -------------- HELPER FUNCTIONS -------------- #

def sleep_between(low: float, high: float) -> None:
    """Randomized sleep with occasional longer pauses."""
    base_sleep = random.uniform(low, high)
    # 10% chance of extra long break
    if random.random() < 0.1:
        base_sleep *= random.uniform(2, 4)
        print(f"  [Extended break: {base_sleep:.1f}s]")
    time.sleep(base_sleep)

def get_random_headers(referer=None):
    """Generate realistic browser headers."""
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": random.choice(config.ACCEPT_LANGUAGES),
        "User-Agent": random.choice(config.USER_AGENTS),
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
    
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=10,
        pool_maxsize=20,
        max_retries=0
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    return session

def load_existing_products():
    """Load already scraped product IDs and URLs."""
    existing_ids = set()
    existing_urls = set()
    
    if not config.OUTPUT_FILE.exists():
        return existing_ids, existing_urls
    
    try:
        with open(config.OUTPUT_FILE, "r", encoding="utf-8") as f:
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

def write_product_to_file(product_data):
    """Thread-safe write to output file using file locking (Windows & Unix compatible)."""
    max_attempts = 5
    attempt = 0
    
    while attempt < max_attempts:
        try:
            with open(config.OUTPUT_FILE, "a", encoding="utf-8") as f:
                if HAS_FCNTL:
                    # Unix/Linux/Mac file locking
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        f.write(json.dumps(product_data, ensure_ascii=False) + "\n")
                        f.flush()
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                else:
                    # Windows file locking
                    msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                    try:
                        f.write(json.dumps(product_data, ensure_ascii=False) + "\n")
                        f.flush()
                    finally:
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            return True
            
        except (IOError, OSError) as e:
            # File might be locked by another worker, retry
            attempt += 1
            if attempt < max_attempts:
                time.sleep(random.uniform(0.1, 0.3))
            else:
                print(f"Error writing to file after {max_attempts} attempts: {e}")
                return False
        except Exception as e:
            print(f"Unexpected error writing to file: {e}")
            return False
    
    return False

def extract_total_results(soup):
    """Extract total number of results from search page."""
    try:
        results_text = soup.find(string=re.compile(r"Results for.*\(\d+\)"))
        if results_text:
            match = re.search(r"\((\d+)\)", results_text)
            if match:
                return int(match.group(1))
    except:
        pass
    return None

def make_request_with_retry(session, url, headers):
    """Make HTTP request with retry logic."""
    last_exception = None
    
    for attempt in range(config.MAX_RETRIES):
        try:
            if attempt > 0:
                retry_delay = random.uniform(5, 15) * (attempt + 1)
                print(f"  [Retry {attempt + 1}/{config.MAX_RETRIES} after {retry_delay:.1f}s]")
                time.sleep(retry_delay)
            
            resp = session.get(url, headers=headers, timeout=config.TIMEOUT, allow_redirects=True)
            
            if resp.status_code == 403:
                print(f"  [403 Forbidden - likely blocked]")
                raise requests.exceptions.HTTPError("403 Forbidden")
            
            if resp.status_code == 429:
                print(f"  [429 Too Many Requests - rate limited]")
                retry_after = int(resp.headers.get('Retry-After', 60))
                time.sleep(min(retry_after, 120))
                continue
            
            if 'captcha' in resp.url.lower() or 'verify' in resp.url.lower():
                print(f"  [CAPTCHA/Verification detected]")
                raise requests.exceptions.HTTPError("CAPTCHA required")
            
            if len(resp.content) < 1000:
                print(f"  [Small response: {len(resp.content)} bytes]")
                if attempt < config.MAX_RETRIES - 1:
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
            if attempt >= config.MAX_RETRIES - 1:
                raise
        except Exception as e:
            last_exception = e
            print(f"  [Error: {e}]")
    
    raise last_exception if last_exception else Exception("Max retries exceeded")

def get_product_links(session, query: str, page_number: int = 1):
    """Fetch product links for a search query."""
    encoded_query = quote_plus(query)
    search_url = f"https://www.walmart.ca/en/search?q={encoded_query}&page={page_number}"
    
    referer = f"https://www.walmart.ca/en/search?q={encoded_query}&page={page_number-1}" if page_number > 1 else None
    headers = get_random_headers(referer=referer)
    
    resp = make_request_with_retry(session, search_url, headers)
    time.sleep(random.uniform(0.5, 1.5))
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    total_results = None
    if page_number == 1:
        total_results = extract_total_results(soup)
    
    # Debug: Save first page HTML
    if page_number == 1:
        debug_file = config.RAW_DIR / f"debug_search_{query.replace(' ', '_')}.html"
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(resp.text)
    
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
    time.sleep(random.uniform(0.5, 2.0))
    
    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    
    if not script_tag or not script_tag.string:
        debug_file = config.RAW_DIR / f"debug_product_{urlparse(product_url).path.split('/')[-1]}.html"
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(resp.text)
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