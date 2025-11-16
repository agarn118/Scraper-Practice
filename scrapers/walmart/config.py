"""
Walmart Scraper - Shared Configuration
File: scrapers/walmart/config.py
"""
from pathlib import Path

# -------------- PATHS -------------- #

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"

OUTPUT_FILE = RAW_DIR / "walmart_product_info.jsonl"
LOCK_FILE = RAW_DIR / "walmart_scraper.lock"

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

ACCEPT_LANGUAGES = [
    "en-CA,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9",
    "en-CA,en;q=0.8,fr-CA;q=0.6,fr;q=0.4",
    "en-GB,en-US;q=0.9,en;q=0.8",
]

TIMEOUT = 15
MAX_RETRIES = 3

# -------------- SCRAPING CONFIG -------------- #

MAX_PAGES_PER_QUERY = None
MAX_PRODUCTS_PER_QUERY = None
MAX_PRODUCT_RETRIES = 3
MAX_ROUNDS = 3

# Delays (in seconds)
SLEEP_PRODUCT_MIN = 1.5
SLEEP_PRODUCT_MAX = 3.5
SLEEP_PAGE_MIN = 3.0
SLEEP_PAGE_MAX = 6.0
SLEEP_QUERY_MIN = 5.0
SLEEP_QUERY_MAX = 10.0

# -------------- GROCERY QUERIES -------------- #

ALL_QUERIES = [
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

# Split queries into 4 groups
QUERIES_PER_WORKER = len(ALL_QUERIES) // 4

WORKER_1_QUERIES = ALL_QUERIES[0:QUERIES_PER_WORKER]
WORKER_2_QUERIES = ALL_QUERIES[QUERIES_PER_WORKER:QUERIES_PER_WORKER*2]
WORKER_3_QUERIES = ALL_QUERIES[QUERIES_PER_WORKER*2:QUERIES_PER_WORKER*3]
WORKER_4_QUERIES = ALL_QUERIES[QUERIES_PER_WORKER*3:]

# Print query distribution
if __name__ == "__main__":
    print("Query Distribution:")
    print(f"Worker 1: {len(WORKER_1_QUERIES)} queries")
    print(f"Worker 2: {len(WORKER_2_QUERIES)} queries")
    print(f"Worker 3: {len(WORKER_3_QUERIES)} queries")
    print(f"Worker 4: {len(WORKER_4_QUERIES)} queries")
    print(f"Total: {len(ALL_QUERIES)} queries")