// SmartSave frontend – fuzzy search + relevance + product detail modal

(function () {
  const searchForm = document.getElementById("searchForm");
  const searchInput = document.getElementById("searchInput");
  const summaryEl = document.getElementById("summary");
  const resultsEl = document.getElementById("results");

  // Detail modal elements
  const overlayEl = document.getElementById("detailOverlay");
  const overlayBackdrop = overlayEl.querySelector(".detail-backdrop");
  const closeBtn = document.getElementById("detailClose");
  const detailImage = document.getElementById("detailImage");
  const detailTitle = document.getElementById("detailTitle");
  const detailBrand = document.getElementById("detailBrand");
  const detailPrice = document.getElementById("detailPrice");
  const detailUnit = document.getElementById("detailUnit");
  const detailRating = document.getElementById("detailRating");
  const detailCategory = document.getElementById("detailCategory");
  const detailExternalLink = document.getElementById("detailExternalLink");

  let allProducts = [];

  // ---------- Helpers ----------

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function parsePrice(value) {
    if (typeof value === "number") return value;
    if (!value) return NaN;
    const cleaned = String(value).replace(/[^\d.,]/g, "").replace(",", ".");
    const num = parseFloat(cleaned);
    return Number.isFinite(num) ? num : NaN;
  }

  function getTitle(p) {
    return p.title || p.product_name || p.name || "";
  }

  function getBrand(p) {
    return p.brand || "";
  }

  function getCategory(p) {
    return p.category || "";
  }

  function getImage(p) {
    return p.image || p.image_url || "";
  }

  function getUrl(p) {
    return p.url || p.product_url || p.link || "";
  }

  function getRating(p) {
    return p.avg_rating || p.rating || null;
  }

  function getReviewCount(p) {
    return p.review_count || p.num_reviews || p.reviews || null;
  }

  // Levenshtein distance for typo tolerance
  function levenshtein(a, b) {
    a = a.toLowerCase();
    b = b.toLowerCase();
    const m = a.length;
    const n = b.length;
    if (!m) return n;
    if (!n) return m;

    const dp = new Array(n + 1);
    for (let j = 0; j <= n; j++) dp[j] = j;

    for (let i = 1; i <= m; i++) {
      let prev = i;
      for (let j = 1; j <= n; j++) {
        const temp = dp[j];
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        dp[j] = Math.min(dp[j] + 1, prev + 1, dp[j - 1] + cost);
        prev = temp;
      }
    }
    return dp[n];
  }

  // Score a product for a query (higher is better)
  function scoreProduct(product, query, terms) {
    const title = getTitle(product).toLowerCase();
    const brand = getBrand(product).toLowerCase();
    const category = getCategory(product).toLowerCase();

    const haystack = `${title} ${brand} ${category}`.trim();
    if (!haystack) return 0;

    let score = 0;

    // Whole-query matches
    if (title.includes(query)) score += 40;
    if (brand.includes(query)) score += 25;
    if (category.includes(query)) score += 10;

    const words = haystack.split(/\s+/);

    for (const term of terms) {
      if (!term) continue;

      if (title.includes(term)) score += 25;
      if (brand.includes(term)) score += 15;
      if (category.includes(term)) score += 10;

      // Fuzzy match against each word
      let best = Infinity;
      for (const w of words) {
        if (!w) continue;
        const d = levenshtein(term, w);
        if (d < best) best = d;
      }

      if (best === 0) {
        score += 15;
      } else if (best === 1) {
        score += 10;
      } else if (best === 2 && term.length >= 5) {
        score += 5;
      }
    }

    if (score <= 0) return 0;

    return score;
  }

  // ---------- Rendering ----------

  function createProductCard(product, isTopMatch) {
    const title = getTitle(product);
    const brand = getBrand(product);
    const category = getCategory(product);
    const priceNum = parsePrice(product.price);
    const image = getImage(product);
    const rating = getRating(product);
    const reviewCount = getReviewCount(product);

    const card = document.createElement("article");
    card.className = "product-card";
    if (isTopMatch) card.classList.add("highlight");

    card.innerHTML = `
      <div class="product-image-wrap">
        ${
          image
            ? `<img src="${escapeHtml(image)}" alt="${escapeHtml(
                title || "Product image"
              )}" loading="lazy" />`
            : ""
        }
      </div>
      <div class="product-body">
        <h2 class="product-title">${escapeHtml(title)}</h2>
        <p class="product-brand">${escapeHtml(brand || "")}</p>
        <p class="product-price">${
          Number.isFinite(priceNum) ? `$${priceNum.toFixed(2)}` : ""
        }</p>
        <div class="product-meta">
          <span class="rating">
            ${
              rating
                ? `<span class="rating-star">★</span>${Number(rating).toFixed(
                    1
                  )}${
                    reviewCount
                      ? ` <span class="rating-count">(${reviewCount})</span>`
                      : ""
                  }`
                : ""
            }
          </span>
          ${
            category
              ? `<span class="category-pill">${escapeHtml(
                  String(category).toLowerCase()
                )}</span>`
              : ""
          }
        </div>
      </div>
    `;

    card.addEventListener("click", () => {
      openDetail(product);
    });

    return card;
  }

  function renderResults(scored, query) {
    resultsEl.innerHTML = "";

    if (!query) {
      summaryEl.textContent =
        "Type a search term above to browse your scraped Walmart catalog.";
      return;
    }

    if (!scored.length) {
      summaryEl.textContent = `No products found for "${query}". Try another search term.`;
      return;
    }

    const MAX_SHOW = 500;
    const shown = scored.slice(0, MAX_SHOW);

    const queryText =
      scored.length === 1
        ? `1 product found for "${query}".`
        : `${scored.length} products found for "${query}".`;

    summaryEl.textContent = `${queryText} Sorted by best match, then lowest price.`;

    shown.forEach((entry, index) => {
      const card = createProductCard(entry.product, index === 0);
      resultsEl.appendChild(card);
    });
  }

  // ---------- Detail modal ----------

  function openDetail(product) {
    const title = getTitle(product) || "Product";
    const brand = getBrand(product);
    const category = getCategory(product);
    const priceNum = parsePrice(product.price);
    const unit = product.price_per_unit || "";
    const rating = getRating(product);
    const reviews = getReviewCount(product);
    const image = getImage(product);
    const url = getUrl(product);

    if (image) {
      detailImage.src = image;
      detailImage.style.visibility = "visible";
    } else {
      detailImage.removeAttribute("src");
      detailImage.style.visibility = "hidden";
    }

    detailTitle.textContent = title;
    detailBrand.textContent = brand ? `by ${brand}` : "";
    detailPrice.textContent = Number.isFinite(priceNum)
      ? `$${priceNum.toFixed(2)}`
      : "";
    detailUnit.textContent = unit || "";

    if (rating) {
      detailRating.textContent = `Rating: ${Number(rating).toFixed(1)}★${
        reviews ? ` (${reviews} review${reviews === 1 ? "" : "s"})` : ""
      }`;
    } else {
      detailRating.textContent = "";
    }

    detailCategory.textContent = category
      ? `Category: ${String(category)}`
      : "";

    if (url) {
      detailExternalLink.href = url;
      detailExternalLink.style.display = "inline-flex";
    } else {
      detailExternalLink.href = "#";
      detailExternalLink.style.display = "none";
    }

    overlayEl.classList.remove("hidden");
    document.body.classList.add("modal-open");
  }

  function closeDetail() {
    overlayEl.classList.add("hidden");
    document.body.classList.remove("modal-open");
  }

  // ---------- Search / events ----------

  function performSearch(rawQuery) {
    const query = (rawQuery || "").trim();
    const qLower = query.toLowerCase();

    if (!qLower) {
      renderResults([], "");
      return;
    }

    const terms = qLower.split(/\s+/).filter(Boolean);

    const scored = [];
    for (const product of allProducts) {
      const score = scoreProduct(product, qLower, terms);
      if (score <= 0) continue;

      const priceNum = parsePrice(product.price);
      scored.push({
        product,
        score,
        price: Number.isFinite(priceNum) ? priceNum : Infinity,
      });
    }

    scored.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.price - b.price;
    });

    renderResults(scored, query);
  }

  async function loadProducts() {
    try {
      const res = await fetch("products.json");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (Array.isArray(data)) return data;
      if (Array.isArray(data.items)) return data.items;
      console.warn("Unexpected products.json format; using empty list.");
      return [];
    } catch (err) {
      console.error("Failed to load products.json:", err);
      summaryEl.textContent =
        "Failed to load products.json. Make sure the file is next to index.html.";
      return [];
    }
  }

  // ---------- Wire up events & init ----------

  searchForm.addEventListener("submit", (evt) => {
    evt.preventDefault();
    performSearch(searchInput.value);
  });

  // Close modal handlers
  closeBtn.addEventListener("click", closeDetail);
  overlayBackdrop.addEventListener("click", closeDetail);
  window.addEventListener("keydown", (evt) => {
    if (evt.key === "Escape" && !overlayEl.classList.contains("hidden")) {
      closeDetail();
    }
  });

  // Initial load
  (async function init() {
    allProducts = await loadProducts();
    // You can optionally pre-populate with "milk" etc. here if you like
    // performSearch("milk");
  })();
})();
