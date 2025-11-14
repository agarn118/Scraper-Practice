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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 OPR/123.0.0.0"
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
    "bottled water",
    "sparkling water",
]


# -------------- SPEED / LIMIT CONFIG -------------- #
# These are tuned to be noticeably faster than your previous run.
# You can tweak them as needed.

# How many search pages max per query? (lower = faster)
MAX_PAGES_PER_QUERY = 5

# How many products max per query to save? (lower = faster)
MAX_PRODUCTS_PER_QUERY = 40

# Sleep ranges (seconds) – small but non-zero to avoid insta-ban
SLEEP_PRODUCT_MIN = 0.2
SLEEP_PRODUCT_MAX = 0.6
SLEEP_PAGE_MIN = 0.4
SLEEP_PAGE_MAX = 1.2

# Only run a slice of queries (by index) if you want to split runs:
# e.g. QUERY_START = 0, QUERY_END = 25   -> first 25 queries
#      QUERY_START = 25, QUERY_END = 50  -> next batch, etc.
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


def extract_product_info(product_url: str):
    """Extract product data from a Walmart product page using __NEXT_DATA__ JSON."""
    resp = SESSION.get(product_url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")

    if not script_tag or not script_tag.string:
        raise ValueError("Could not find __NEXT_DATA__ script tag")

    data = json.loads(script_tag.string)
    initial_data = data["props"]["pageProps"]["initialData"]["data"]
    product_data = initial_data["product"]
    reviews_data = initial_data.get("reviews", {})

    product_info = {
        "price": product_data["priceInfo"]["currentPrice"]["price"],
        "review_count": reviews_data.get("totalReviewCount", 0),
        "item_id": product_data["usItemId"],
        "avg_rating": reviews_data.get("averageOverallRating", 0),
        "product_name": product_data["name"],
        "brand": product_data.get("brand", ""),
        "availability": product_data["availabilityStatus"],
        "image_url": product_data["imageInfo"]["thumbnailUrl"],
        "short_description": product_data.get("shortDescription", ""),
    }

    return product_info


# -------------- MAIN -------------- #

def main():
    OUTPUT_FILE = "practice_4_product_info.jsonl"

    seen_urls = set()
    failed_queries = []  # queries that had 0 links on page 1 or search-level HTTP errors

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        # slice queries if you want smaller/faster runs
        active_queries = GROCERY_QUERIES[QUERY_START:QUERY_END]

        for idx, query in enumerate(active_queries, start=QUERY_START):
            page_number = 1
            products_for_query = 0

            print(f"\n=== ({idx}) Searching for '{query}' ===")

            while True:
                if page_number > MAX_PAGES_PER_QUERY:
                    print(f"Reached max pages ({MAX_PAGES_PER_QUERY}) for '{query}'")
                    break

                # Get links for this query + page
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

                # If page 1 has zero product links, treat as "no results" (or blocked) and log the query
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

                # Process each product link
                for link in links:
                    if link in seen_urls:
                        continue
                    seen_urls.add(link)

                    if products_for_query >= MAX_PRODUCTS_PER_QUERY:
                        print(f"Reached max products ({MAX_PRODUCTS_PER_QUERY}) for '{query}'")
                        break

                    try:
                        product_info = extract_product_info(link)
                        if product_info:
                            # Tag row with the query that found it
                            product_info["search_query"] = query
                            file.write(json.dumps(product_info, ensure_ascii=False) + "\n")
                            products_for_query += 1
                    except Exception as e:
                        # URL-level failures don't mark whole query as failed, but log them
                        print(f"Failed to process URL {link}. Error: {e}")

                    # Faster but still slightly random delay between product pages
                    sleep_between(SLEEP_PRODUCT_MIN, SLEEP_PRODUCT_MAX)

                # If we hit the per-query product limit, stop paging this query
                if products_for_query >= MAX_PRODUCTS_PER_QUERY:
                    break

                # Next search page for this query
                page_number += 1

                # Faster short delay between search pages
                sleep_between(SLEEP_PAGE_MIN, SLEEP_PAGE_MAX)

    print("\nScraping complete. Data written to wow_product_info.jsonl")

    # ---------- Log failed queries so you can re-run them later ----------
    unique_failed = sorted(set(failed_queries))
    if unique_failed:
        print("\nThe following queries had issues (no links on page 1 or HTTP errors):")
        for q in unique_failed:
            print(f" - {q}")

        # Save to a simple text file, one query per line
        with open("failed_queries.txt", "w", encoding="utf-8") as fq:
            for q in unique_failed:
                fq.write(q + "\n")

        print("\nFailed queries saved to failed_queries.txt")
        print("You can paste that list back into GROCERY_QUERIES or make a small retry script.")
    else:
        print("\nAll queries finished without being skipped on page 1 or aborted due to search errors.")


if __name__ == "__main__":
    main()
