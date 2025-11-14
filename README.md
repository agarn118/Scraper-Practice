# SmartSave – Local Walmart Product Browser

SmartSave is a small end-to-end demo that:

1. Scrapes product data from **Walmart.ca (looking for more websites in the future)**
2. Normalizes it into a clean `products.json` file
3. Serves a **searchable, fuzzy-matching product browser** via a simple Flask app

You can type things like `milk`, `cheese`, or even typo-heavy queries like `millk`, and the UI returns relevant products, sorted by best match, then price. Clicking a product opens a modal with details and a button to view the item on Walmart’s site.

---

## Features

- **Local Walmart catalog** from your own scraped data
- **Client-side fuzzy search**
  - Exact matches on name, brand, category
  - Substring matches
  - Simple Levenshtein-based typo tolerance (`millk` → *milk*)
  - Sorted by relevance score, then by lowest price
- **Static, fast frontend**
  - Responsive grid of product cards
  - Nice glassy modal with image, description, rating, etc.
---

## Tech Stack

- **Backend / server**
  - [Python](https://www.python.org/)
  - [Flask](https://flask.palletsprojects.com/) – for serving the static frontend + `products.json`
- **Scraping / data**
  - Playwright-based Walmart scraper (e.g. `walmart_scraper.py`)
  - Raw JSONL: `product_info.jsonl`
  - Normalized JSON: `products.json`
  - Optional SQLite: `jsonl_to_sqlite.py`, `view_products_db.py`
- **Frontend**
  - Vanilla HTML (`index.html`)
  - CSS (`style.css`)
  - JavaScript (`script.js`)

---

## Repository Structure

├── app.py                 # Flask app that serves index.html, script.js, style.css, products.json
├── build_frontend_json.py # Normalizes product_info.jsonl → products.json
├── walmart_scraper.py     # Scraper that hits Walmart.ca and writes product_info.jsonl
├── jsonl_to_sqlite.py     # (optional) Convert JSONL to SQLite DB
├── view_products_db.py    # (optional) SQLite viewer / helper
├── product_info.jsonl     # Raw scraped product data (one JSON per line)
├── products.json          # Cleaned & deduplicated products for frontend
├── index.html             # SmartSave UI shell
├── style.css              # Styling for layout, cards, modal, etc.
└── script.js              # Client-side search, scoring, modal logic
