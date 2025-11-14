// script.js – minimal SmartSave frontend that reads products.json

const DATA_URL = "products.json";

let catalog = [];
let dataLoaded = false;
let dataError = null;

async function loadCatalogOnce() {
  if (dataLoaded || dataError) {
    if (dataError) throw dataError;
    return;
  }

  try {
    const res = await fetch(DATA_URL);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} when loading ${DATA_URL}`);
    }
    const json = await res.json();

    // products.json can be either:
    // { "items": [ ... ] }  or  [ ... ]
    const rawItems = Array.isArray(json) ? json : json.items || [];

    catalog = rawItems.map((item) => {
      // Normalise fields from your scraper
      const name =
        item.product_name ||
        item.title ||
        item.name ||
        "";

      let price = item.price;
      if (typeof price === "string") {
        const cleaned = price.replace(/[^0-9.,-]/g, "").replace(",", "");
        const parsed = parseFloat(cleaned);
        if (!Number.isNaN(parsed)) price = parsed;
      }

      const brand = item.brand || "";
      const img =
        item.image_url ||
        item.image ||
        null;

      const queries = Array.isArray(item.search_queries)
        ? item.search_queries
        : [];

      return {
        raw: item,
        name,
        brand,
        price: typeof price === "number" ? price : null,
        image: img,
        searchQueries: queries,
      };
    });

    dataLoaded = true;
  } catch (err) {
    dataError = err;
    throw err;
  }
}

function renderItems(list, query) {
  const resultsEl = document.getElementById("results");
  const summaryEl = document.getElementById("summary");

  if (!resultsEl || !summaryEl) return;

  if (!query) {
    summaryEl.innerHTML =
      'Type something above and hit <strong>Search</strong> to see results.';
    resultsEl.innerHTML = "";
    return;
  }

  if (!list.length) {
    summaryEl.textContent = `No products found for "${query}".`;
    resultsEl.innerHTML =
      '<div class="error">No matches – try a broader search term.</div>';
    return;
  }

  summaryEl.textContent = `${list.length} product${
    list.length !== 1 ? "s" : ""
  } found for "${query}". Sorted by lowest price.`;

  const html = list
    .map((item) => {
      const priceLabel =
        item.price != null ? `$${item.price.toFixed(2)}` : "—";

      const brand =
        item.brand && item.brand.trim()
          ? `<div class="card-brand">${escapeHtml(item.brand)}</div>`
          : "";

      const imgPart = item.image
        ? `<img src="${encodeURI(item.image)}" alt="${escapeHtml(
            item.name || "Product image"
          )}" loading="lazy" />`
        : `<span class="card-meta">No image</span>`;

      return `
        <article class="card">
          <div class="card-image-wrap">
            ${imgPart}
          </div>
          <div class="card-info">
            <div class="card-title">${escapeHtml(item.name || "Unnamed item")}</div>
            ${brand}
            <div class="card-footer">
              <div class="card-price">${priceLabel}</div>
              <div class="card-meta">${
                item.searchQueries && item.searchQueries.length
                  ? escapeHtml(item.searchQueries.join(", "))
                  : ""
              }</div>
            </div>
          </div>
        </article>
      `;
    })
    .join("");

  resultsEl.innerHTML = html;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function handleSearch(event) {
  if (event) event.preventDefault();

  const input = document.getElementById("q");
  const resultsEl = document.getElementById("results");
  const summaryEl = document.getElementById("summary");

  if (!input || !resultsEl || !summaryEl) return;

  const query = (input.value || "").trim();

  if (!query) {
    renderItems([], "");
    return;
  }

  resultsEl.innerHTML = '<div class="loading">Loading results…</div>';
  summaryEl.textContent = "Loading products…";

  try {
    await loadCatalogOnce();
  } catch (err) {
    console.error(err);
    summaryEl.textContent = "Failed to load product data.";
    resultsEl.innerHTML = `<div class="error">${
      escapeHtml(err.message || "Unknown error")
    }</div>`;
    return;
  }

  const qLower = query.toLowerCase();

  const matches = catalog
    .filter((item) => {
      const fields = [
        item.name || "",
        item.brand || "",
        ...(item.searchQueries || []),
      ];
      const haystack = fields.join(" ").toLowerCase();
      return haystack.includes(qLower);
    })
    .sort((a, b) => {
      if (a.price == null && b.price == null) return 0;
      if (a.price == null) return 1;
      if (b.price == null) return -1;
      return a.price - b.price;
    });

  renderItems(matches, query);
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("searchForm");
  if (form) {
    form.addEventListener("submit", handleSearch);
  }
});
