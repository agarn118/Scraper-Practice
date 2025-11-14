from bs4 import BeautifulSoup
import requests
import json
import time
import random
from urllib.parse import quote_plus

HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 OPR/123.0.0.0"
}

# ------------------ SEARCH QUERIES ------------------ #
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


def get_product_links(query: str, page_number: int = 1):
    """Fetch product links for a search query + page, skipping tracking/ad URLs."""
    encoded_query = quote_plus(query)
    search_url = f"https://www.walmart.ca/en/search?q={encoded_query}&page={page_number}"

    response = requests.get(search_url, headers=HEADERS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
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
    response = requests.get(product_url, headers=HEADERS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
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


def main():
    OUTPUT_FILE = "wow_product_info.jsonl"
    MAX_PAGES_PER_QUERY = 10  # safety cap so it doesn't go wild

    seen_urls = set()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        for query in GROCERY_QUERIES:
            page_number = 1
            print(f"\n=== Searching for '{query}' ===")

            while True:
                if page_number > MAX_PAGES_PER_QUERY:
                    print(f"Reached max pages for '{query}'")
                    break

                # Get links for this query + page
                try:
                    links = get_product_links(query, page_number)
                except requests.HTTPError as e:
                    print(f"HTTP error for search '{query}' page {page_number}: {e}")
                    # move on to next query instead of killing the whole script
                    break
                except Exception as e:
                    print(f"Unexpected error for search '{query}' page {page_number}: {e}")
                    break

                # If page 1 has zero product links, treat as "no results" (or blocked) and skip this query
                if not links:
                    if page_number == 1:
                        print(
                            f"No product links for '{query}' on page 1. "
                            "No results or blocked; skipping this query."
                        )
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

                    try:
                        product_info = extract_product_info(link)
                        if product_info:
                            # Tag row with the query that found it
                            product_info["search_query"] = query
                            file.write(json.dumps(product_info, ensure_ascii=False) + "\n")
                    except Exception as e:
                        print(f"Failed to process URL {link}. Error: {e}")

                    # Small pause between product page requests
                    time.sleep(random.uniform(1.0, 2.5))

                # Next search page for this query
                page_number += 1

                # Slightly longer pause between search pages
                time.sleep(random.uniform(2.0, 4.0))

    print("\nScraping complete. Data written to wow_product_info.jsonl")


if __name__ == "__main__":
    main()
