from bs4 import BeautifulSoup
import requests
import json
import time
import random

# -------------- HTTP CONFIG -------------- #

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
}

TIMEOUT = 15
SESSION = requests.Session()
BASE_URL = "https://www.realcanadiansuperstore.ca"

# -------------- CONFIG -------------- #
SLEEP_MIN = 0.3
SLEEP_MAX = 0.8
MAX_PAGES = None  # None = unlimited
QUERY_SLEEP_MIN = 1.0  # Sleep between queries
QUERY_SLEEP_MAX = 2.0

# Search queries to scrape
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


# -------------- HELPERS -------------- #

def sleep_random():
    """Random sleep between requests."""
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))


def sleep_between_queries():
    """Longer sleep between different search queries."""
    time.sleep(random.uniform(QUERY_SLEEP_MIN, QUERY_SLEEP_MAX))


def extract_products_from_json(json_data):
    """Extract product data from __NEXT_DATA__ JSON."""
    try:
        # Navigate to the product data
        page_props = json_data.get("props", {}).get("pageProps", {})
        
        # For search pages, data is in initialSearchData
        search_data = page_props.get("initialSearchData", {})
        layout = search_data.get("layout", {})
        sections = layout.get("sections", {})
        
        products = []
        
        # Look through all sections for product grids
        for section_name, section_data in sections.items():
            if not isinstance(section_data, dict):
                continue
                
            components = section_data.get("components", [])
            
            for component in components:
                if not isinstance(component, dict):
                    continue
                
                comp_id = component.get("componentId", "")
                
                # Only process productGridComponent
                if comp_id != "productGridComponent":
                    continue
                
                # The product data is directly in the component's data
                comp_data = component.get("data", {})
                product_tiles = comp_data.get("productTiles", [])
                
                if product_tiles:
                    products.extend(product_tiles)
        
        return products
        
    except Exception as e:
        print(f"Error extracting products from JSON: {e}")
        import traceback
        traceback.print_exc()
        return []


def parse_product(product_data, search_query):
    """Parse a single product tile into a clean dict."""
    try:
        # Basic info
        info = {
            "search_query": search_query,
            "product_id": product_data.get("productId", ""),
            "article_number": product_data.get("articleNumber", ""),
            "brand": product_data.get("brand", ""),
            "title": product_data.get("title", ""),
            "description": product_data.get("description", ""),
            "package_sizing": product_data.get("packageSizing", ""),
            "link": BASE_URL + product_data.get("link", "") if product_data.get("link") else "",
        }
        
        # Pricing
        pricing = product_data.get("pricing", {})
        if pricing:
            info["price"] = pricing.get("displayPrice", "")
            info["was_price"] = pricing.get("wasPrice", "")
            info["price_raw"] = pricing.get("price", "")
        
        # Deal info
        deal = product_data.get("deal", {})
        if deal:
            info["deal_type"] = deal.get("type", "")
            info["deal_text"] = deal.get("text", "")
            
        # Inventory
        inventory = product_data.get("inventoryIndicator", {})
        if inventory:
            info["inventory_status"] = inventory.get("text", "")
            
        # Badge
        badge = product_data.get("productBadge", {})
        if badge:
            info["badge"] = badge.get("text", "")
            
        # Image
        images = product_data.get("productImage", [])
        if images:
            info["image_url"] = images[0].get("largeUrl", "")
        
        # Sponsored/offer type
        info["offer_type"] = product_data.get("offerType", "")
        info["is_sponsored"] = product_data.get("isSponsored", False)
        
        return info
        
    except Exception as e:
        print(f"Error parsing product: {e}")
        return None


def scrape_query(query, seen_product_ids):
    """Scrape all products for a given search query."""
    
    query_products = []
    page = 1
    
    print(f"\n{'='*60}")
    print(f"Scraping query: '{query}'")
    print(f"{'='*60}")
    
    while True:
        if MAX_PAGES and page > MAX_PAGES:
            print(f"  Reached max page limit ({MAX_PAGES})")
            break
            
        search_url = f"{BASE_URL}/search?search-bar={query}&page={page}"
        print(f"  Page {page}: {search_url}")
        
        try:
            response = SESSION.get(search_url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            
        except requests.RequestException as e:
            print(f"    ✗ Error fetching page {page}: {e}")
            break
        
        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find __NEXT_DATA__ script
        script_tag = soup.find("script", id="__NEXT_DATA__")
        
        if not script_tag or not script_tag.string:
            print(f"    ✗ No __NEXT_DATA__ found on page {page}")
            break
        
        # Parse JSON
        try:
            json_data = json.loads(script_tag.string)
        except json.JSONDecodeError as e:
            print(f"    ✗ JSON decode error on page {page}: {e}")
            break
        
        # Extract products from JSON
        products = extract_products_from_json(json_data)
        
        if not products:
            print(f"    ✗ No products found on page {page}")
            if page == 1:
                print("    This might mean no results for this query")
            break
        
        print(f"    Found {len(products)} products on page")
        
        # Parse and collect unique products
        new_products = 0
        for product_data in products:
            product_id = product_data.get("productId", "")
            
            if product_id in seen_product_ids:
                continue
            
            parsed = parse_product(product_data, query)
            if parsed:
                query_products.append(parsed)
                seen_product_ids.add(product_id)
                new_products += 1
        
        print(f"    ✓ Added {new_products} new products")
        
        # Check if there are more pages
        try:
            page_props = json_data.get("props", {}).get("pageProps", {})
            search_data = page_props.get("initialSearchData", {})
            layout = search_data.get("layout", {})
            sections = layout.get("sections", {})
            
            has_more = False
            for section_data in sections.values():
                if isinstance(section_data, dict):
                    for component in section_data.get("components", []):
                        if isinstance(component, dict):
                            comp_data = component.get("data", {})
                            pagination = comp_data.get("pagination", {})
                            has_more = pagination.get("hasMore", False)
                            if has_more:
                                break
                if has_more:
                    break
            
            if not has_more:
                print(f"    No more pages available")
                break
                
        except Exception as e:
            print(f"    Could not determine if more pages exist: {e}")
            if new_products == 0:
                break
        
        page += 1
        sleep_random()
    
    print(f"  Query complete: {len(query_products)} products for '{query}'")
    return query_products


# -------------- MAIN -------------- #

def main():
    OUTPUT_FILE = "superstore_product_info.jsonl"
    
    print("\n" + "="*60)
    print("REAL CANADIAN SUPERSTORE SCRAPER")
    print("="*60)
    print(f"Total queries to scrape: {len(GROCERY_QUERIES)}")
    print(f"Output file: {OUTPUT_FILE}")
    print("="*60)
    
    all_products = []
    seen_product_ids = set()
    
    # Scrape each query
    for idx, query in enumerate(GROCERY_QUERIES, 1):
        print(f"\n[Query {idx}/{len(GROCERY_QUERIES)}]")
        
        query_products = scrape_query(query, seen_product_ids)
        all_products.extend(query_products)
        
        print(f"  Running total: {len(all_products)} unique products")
        
        # Save progress after each query
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for product in all_products:
                f.write(json.dumps(product, ensure_ascii=False) + "\n")
        
        print(f"  ✓ Progress saved to {OUTPUT_FILE}")
        
        # Sleep between queries (except after the last one)
        if idx < len(GROCERY_QUERIES):
            sleep_between_queries()
    
    # Final summary
    print("\n" + "="*60)
    print("SCRAPING COMPLETE!")
    print("="*60)
    print(f"Total unique products: {len(all_products)}")
    print(f"Total queries scraped: {len(GROCERY_QUERIES)}")
    print(f"Output saved to: {OUTPUT_FILE}")
    
    # Print category breakdown
    print("\nCategory breakdown:")
    query_counts = {}
    for product in all_products:
        query = product.get("search_query", "unknown")
        query_counts[query] = query_counts.get(query, 0) + 1
    
    for query, count in sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {query}: {count} products")
    
    # Print sample products
    print("\nSample products:")
    for i, product in enumerate(all_products[:5], 1):
        print(f"\n{i}. {product['brand']} - {product['title']}")
        print(f"   Price: {product.get('price', 'N/A')}")
        print(f"   Query: {product.get('search_query', 'N/A')}")


if __name__ == "__main__":
    main()