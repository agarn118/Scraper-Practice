from bs4 import BeautifulSoup
import requests
import json
import time
import random
from urllib.parse import quote_plus

# -------------- HTTP CONFIG (session + headers) -------------- #

HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 OPR/123.0.0.0",
}

TIMEOUT = 10  # seconds
SESSION = requests.Session()


# -------------- SEARCH QUERIES -------------- #

GROCERY_QUERIES = [
    # Dairy
    "milk",
    "skim milk",
    "2% milk",
    "3.25% milk",
    "lactose free milk",
    "cream",
    "coffee cream",
    "whipping cream",
    "half and half",
    "butter",
    "margarine",
    "cheddar cheese",
    "mozzarella cheese",
    "shredded cheese",
    "cream cheese",
    "cottage cheese",
    "yogurt",
    "greek yogurt",
    "sour cream",
    "ice cream",

    # Eggs & breakfast
    "eggs",
    "egg whites",
    "bacon",
    "breakfast sausage",
    "hash browns",

    # Bakery
    "white bread",
    "whole wheat bread",
    "bagels",
    "english muffins",
    "tortillas",
    "naan",
    "hamburger buns",
    "hot dog buns",

    # Pantry staples
    "rice",
    "brown rice",
    "pasta",
    "spaghetti",
    "macaroni",
    "flour",
    "sugar",
    "brown sugar",
    "baking soda",
    "baking powder",
    "salt",
    "black pepper",
    "olive oil",
    "canola oil",
    "vegetable oil",
    "vinegar",
    "soy sauce",
    "ketchup",
    "mustard",
    "mayonnaise",
    "salad dressing",
    "peanut butter",
    "jam",
    "honey",

    # Canned & jarred
    "canned soup",
    "canned tomatoes",
    "canned beans",
    "canned tuna",
    "canned salmon",
    "pasta sauce",

    # Frozen
    "frozen vegetables",
    "frozen fruit",
    "frozen pizza",
    "frozen fries",
    "frozen chicken nuggets",

    # Meat
    "chicken breast",
    "chicken thighs",
    "whole chicken",
    "ground beef",
    "steak",
    "pork chops",
    "ground pork",
    "ground turkey",
    "ham",
    "sausages",

    # Produce
    "apples",
    "bananas",
    "oranges",
    "grapes",
    "strawberries",
    "blueberries",
    "broccoli",
    "cauliflower",
    "carrots",
    "onions",
    "potatoes",
    "sweet potatoes",
    "lettuce",
    "spinach",
    "kale",
    "tomatoes",
    "cucumbers",
    "bell peppers",

    # Snacks
    "potato chips",
    "tortilla chips",
    "popcorn",
    "crackers",
    "cookies",
    "chocolate",
    "granola bars",
    "nuts",
    "trail mix",

    # Drinks
    "coffee",
    "instant coffee",
    "tea",
    "orange juice",
    "apple juice",
    "soft drinks",
    "energy drinks",
    "water",
    "mineral water",
    "bottled water",
    "sparkling water",
]


# -------------- SPEED / LIMIT CONFIG -------------- #

MAX_PAGES_PER_QUERY = None       # None = no explicit page cap
MAX_PRODUCTS_PER_QUERY = None    # None = no explicit product cap
MAX_PRODUCT_RETRIES = 3

SLEEP_PRODUCT_MIN = 0.2
SLEEP_PRODUCT_MAX = 0.6
SLEEP_PAGE_MIN = 0.4
SLEEP_PAGE_MAX = 1.2

QUERY_START = 0
QUERY_END = len(GROCERY_QUERIES)


# -------------- HELPERS -------------- #

def sleep_between(low: float, high: float) -> None:
    """Randomized short sleep between actions."""
    time.sleep(random.uniform(low, high))


def get_product_links(query: str, page_number: int = 1):
    """Fetch product links for a search query + page, skipping tracking/ad URLs."""
    encoded_query = quote_plus(query)
    search_url = f"https://www.walmart.ca/en/search?q={encoded_query}&page={page_number}"

    resp = SESSION.get(search_url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.find_all("a", href=True)

    product_links = []

    for link in links:
        href = link["href"]

        # Skip tracking/ad links like /wapcrs/track...
        if "wapcrs/track" in href:
            continue

        if "/ip" in href:
            if href.startswith("http"):
                full_url = href
            else:
                full_url = "https://www.walmart.ca" + href
            product_links.append(full_url)

    return product_links


def _fmt_price(v):
    """Format a numeric price like 4.29 -> ('$4.29', '4.29')."""
    if v is None:
        return None, None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None, None
    return f"${f:.2f}", f"{f:.2f}"


def extract_product_info(product_url: str):
    """
    Extract product data from a Walmart product page using __NEXT_DATA__ JSON.

    Output is shaped to match the Superstore scraper schema as closely as
    possible, while still keeping the old walmart-specific fields for
    backwards compatibility.
    """
    resp = SESSION.get(product_url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")

    if not script_tag or not script_tag.string:
        raise ValueError("Could not find __NEXT_DATA__ script tag")

    data = json.loads(script_tag.string)
    initial_data = data["props"]["pageProps"]["initialData"]["data"]
    product_data = initial_data["product"]
    reviews_data = initial_data.get("reviews", {}) or {}

    # --- price handling ---
    price_info = product_data.get("priceInfo", {}) or {}
    curr = price_info.get("currentPrice") or {}
    price_val = curr.get("price")

    was_price_val = None
    was = price_info.get("wasPrice") or price_info.get("comparisonPrice") or {}
    if isinstance(was, dict):
        was_price_val = was.get("price")

    price_str, price_raw = _fmt_price(price_val)
    was_price_str, _ = _fmt_price(was_price_val)

    # --- basic fields ---
    us_item_id = product_data.get("usItemId")
    sku_id = product_data.get("skuId")
    title = product_data.get("name") or ""
    brand = product_data.get("brand") or ""
    availability = product_data.get("availabilityStatus") or ""
    image_url = (product_data.get("imageInfo") or {}).get("thumbnailUrl")
    short_desc = product_data.get("shortDescription") or ""

    # Walmart doesn't always expose neat size strings; grab anything reasonable.
    package_sizing = (
        product_data.get("size")
        or (product_data.get("productAttributes") or {}).get("size")
    )

    inventory_status = availability

    product_info = {
        # ---------- Superstore-style common schema ----------
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
        "inventory_status": inventory_status,
        "image_url": image_url,
        "offer_type": "OG",
        "is_sponsored": False,

        # ---------- Extra / backwards-compatible fields ----------
        "price_numeric": float(price_raw) if price_raw else None,
        "review_count": reviews_data.get("totalReviewCount", 0),
        "item_id": us_item_id,
        "avg_rating": reviews_data.get("averageOverallRating"),
        "product_name": title,
        "availability": availability,
        "short_description": short_desc,
        "product_url": product_url,
    }

    return product_info


def run_round(
    queries,
    file,
    seen_urls,
    product_retry_counts,
    failed_urls_final,
    round_num: int,
):
    """
    Run one scraping round over the given list of queries.

    Returns a list of queries that 'failed' at either:
      - SEARCH level:
          * 0 product links on page 1  (blocked / no results)
          * HTTP/other exception when fetching search results
      - PRODUCT level:
          * At least one product URL failed but hasn't yet hit MAX_PRODUCT_RETRIES
    """
    failed_queries = []

    for query in queries:
        page_number = 1
        products_for_query = 0
        query_had_retryable_product_failures = False

        print(f"\n=== [Round {round_num}] Searching for '{query}' ===")

        while True:
            if MAX_PAGES_PER_QUERY is not None and page_number > MAX_PAGES_PER_QUERY:
                print(f"Reached max pages cap ({MAX_PAGES_PER_QUERY}) for '{query}'")
                break

            try:
                links = get_product_links(query, page_number)
            except requests.HTTPError as e:
                print(f"HTTP error for search '{query}' page {page_number}: {e}")
                failed_queries.append(query)
                break
            except Exception as e:
                print(f"Unexpected error for search '{query}' page {page_number}: {e}")
                failed_queries.append(query)
                break

            if not links:
                if page_number == 1:
                    print(
                        f"No product links for '{query}' on page 1. "
                        "No results or blocked; skipping this query."
                    )
                    failed_queries.append(query)
                    break
                else:
                    print(f"No more results for '{query}' on page {page_number}")
                    break

            print(f"Query '{query}', page {page_number}, found {len(links)} links")

            for link in links:
                if link in seen_urls or link in failed_urls_final:
                    continue

                if (
                    MAX_PRODUCTS_PER_QUERY is not None
                    and products_for_query >= MAX_PRODUCTS_PER_QUERY
                ):
                    print(
                        f"Reached max products cap ({MAX_PRODUCTS_PER_QUERY}) for '{query}'"
                    )
                    break

                try:
                    product_info = extract_product_info(link)
                    if product_info:
                        # ----- IMPORTANT CHANGE HERE -----
                        # Build a new dict with search_query first,
                        # then all the product_info fields.
                        row = {"search_query": query}
                        row.update(product_info)

                        file.write(json.dumps(row, ensure_ascii=False) + "\n")
                        products_for_query += 1
                        seen_urls.add(link)

                except Exception as e:
                    print(f"Failed to process URL {link}. Error: {e}")

                    current_count = product_retry_counts.get(link, 0) + 1
                    product_retry_counts[link] = current_count

                    if current_count >= MAX_PRODUCT_RETRIES:
                        failed_urls_final.add(link)
                        print(
                            f"Giving up on URL after {current_count} failures: {link}"
                        )
                    else:
                        query_had_retryable_product_failures = True

                sleep_between(SLEEP_PRODUCT_MIN, SLEEP_PRODUCT_MAX)

            if (
                MAX_PRODUCTS_PER_QUERY is not None
                and products_for_query >= MAX_PRODUCTS_PER_QUERY
            ):
                break

            page_number += 1
            sleep_between(SLEEP_PAGE_MIN, SLEEP_PAGE_MAX)

        if query_had_retryable_product_failures:
            failed_queries.append(query)

    return sorted(set(failed_queries))


# -------------- MAIN -------------- #

def main():
    OUTPUT_FILE = "walmart_v2_product_info.jsonl"

    seen_urls = set()
    product_retry_counts = {}
    failed_urls_final = set()

    base_queries = GROCERY_QUERIES[QUERY_START:QUERY_END]

    print(f"Starting scrape with {len(base_queries)} base queries...")

    remaining_failed = []
    round_num = 1

    with open(OUTPUT_FILE, "a", encoding="utf-8") as file:
        current_queries = list(base_queries)

        while current_queries:
            print(f"\n##### ROUND {round_num} – {len(current_queries)} queries #####")

            failed_this_round = run_round(
                current_queries,
                file,
                seen_urls,
                product_retry_counts,
                failed_urls_final,
                round_num,
            )

            if not failed_this_round:
                remaining_failed = []
                break

            failed_set = sorted(set(failed_this_round))

            if set(failed_set) == set(current_queries):
                print("\nNo further progress on failing queries; stopping retries.")
                remaining_failed = failed_set
                break

            print(
                f"\nWill retry {len(failed_set)} failed queries in the next round:"
            )
            for q in failed_set:
                print(f" - {q}")

            current_queries = failed_set
            round_num += 1

    print(f"\nScraping complete. Data written to {OUTPUT_FILE}")

    if remaining_failed:
        print(
            "\nThe following queries are still failing after retries "
            "(no links on page 1, search-level errors, or too many product-level failures):"
        )
        for q in remaining_failed:
            print(f" - {q}")

        with open("failed_queries.txt", "w", encoding="utf-8") as fq:
            for q in remaining_failed:
                fq.write(q + "\n")

        print("\nFailed queries saved to failed_queries.txt")
    else:
        print("\nAll queries completed without persistent search-level failures.")

    if failed_urls_final:
        print(
            f"\nThere are {len(failed_urls_final)} product URLs that failed "
            f"{MAX_PRODUCT_RETRIES} times and were skipped permanently."
        )
        with open("failed_urls.txt", "w", encoding="utf-8") as fu:
            for url in sorted(failed_urls_final):
                fu.write(url + "\n")
        print("Permanently failed product URLs saved to failed_urls.txt")


if __name__ == "__main__":
    main()
