// script.js – SmartSave frontend (products.json client-side search + modal)

(() => {
  const PRODUCTS_URL = "products.json";

  let allProducts = [];
  let normalizedProducts = [];
  let lastQuery = "";

  // ---------- Utility helpers ----------

  function escapeHtml(str = "") {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function toNumber(val) {
    if (typeof val === "number") return val;
    if (val == null) return null;
    const n = parseFloat(String(val).replace(/[^\d.-]/g, ""));
    return Number.isFinite(n) ? n : null;
  }

  function tokenize(str = "") {
    return str
      .toLowerCase()
      .split(/[^a-z0-9%]+/g)
      .filter(Boolean);
  }

  // Simple Levenshtein distance for fuzzy matching (typos)
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
      let prev = dp[0];
      dp[0] = i;
      for (let j = 1; j <= n; j++) {
        const tmp = dp[j];
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        dp[j] = Math.min(
          dp[j] + 1, // deletion
          dp[j - 1] + 1, // insertion
          prev + cost // substitution
        );
        prev = tmp;
      }
    }
    return dp[n];
  }

  // Slugify product name for Walmart URL (only cosmetic; ID is what matters)
  function slugify(name = "") {
    return name
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "item";
  }

  // Try to find an explicit URL field on the raw object
  function explicitUrlFromRaw(raw) {
    const candidates = [
      raw.url,
      raw.product_url,
      raw.productUrl,
      raw.product_page,
      raw.page_url,
      raw.link,
      raw.href,
      raw.canonical_url
    ];
    for (const u of candidates) {
      if (typeof u === "string" && u.startsWith("http")) return u;
    }
    // Sometimes scraper stores relative URLs like "/en/ip/..."
    if (typeof raw.relative_url === "string") {
      const rel = raw.relative_url;
      if (rel.startsWith("http")) return rel;
      if (rel.startsWith("/")) return "https://www.walmart.ca" + rel;
    }
    return null;
  }

  // Build a Walmart.ca product URL if we at least know item_id
  function walmartUrlFromIdAndName(itemId, name) {
    if (!itemId) return null;
    const slug = slugify(name || "");
    return `https://www.walmart.ca/en/ip/${slug}/${itemId}`;
  }

  // Derive the best store URL for a product (raw + normalized info)
  function deriveStoreUrl(raw, name, id) {
    const explicit = explicitUrlFromRaw(raw);
    if (explicit) return explicit;

    const itemId = raw.item_id || id;
    if (itemId) return walmartUrlFromIdAndName(itemId, name);

    return null;
  }

  // Normalize raw product into a consistent shape
  function normalizeProduct(raw, index) {
    const name = raw.product_name || raw.name || "";
    const brand = raw.brand || "";
    const category = raw.category || raw.category_path || "";
    const image =
      raw.image_url || raw.image || raw.thumbnail || raw.img || "";

    const price = toNumber(raw.price);
    const rating =
      toNumber(raw.avg_rating ?? raw.rating ?? raw.star_rating) ?? null;
    const reviewCount =
      toNumber(
        raw.review_count ?? raw.num_reviews ?? raw.reviews ?? raw.reviewCount
      ) ?? null;

    const description =
      raw.short_description ||
      raw.description ||
      raw.desc ||
      "";

    const queries = raw.search_queries || raw.queries || [];

    const id =
      raw.item_id ||
      raw.id ||
      raw.sku ||
      raw.productId ||
      `idx-${index}`;

    const url = deriveStoreUrl(raw, name, id);

    return {
      id,
      name,
      brand,
      category,
      image,
      price,
      rating,
      reviewCount,
      description,
      queries,
      url,
      _raw: raw
    };
  }

  // ---------- Scoring / search ----------

  function scoreProduct(prod, query) {
    const q = query.trim().toLowerCase();
    if (!q) return 0;

    const qTokens = tokenize(q);
    if (!qTokens.length) return 0;

    const name = prod.name.toLowerCase();
    const brand = prod.brand.toLowerCase();
    const category = prod.category.toLowerCase();
    const extra = (prod.queries || []).join(" ").toLowerCase();

    const nameTokens = tokenize(name);
    const brandTokens = tokenize(brand);
    const catTokens = tokenize(category);

    let score = 0;

    for (const qt of qTokens) {
      // Exact word matches – strongest signal
      if (nameTokens.includes(qt)) score += 200;
      if (brandTokens.includes(qt)) score += 180;
      if (catTokens.includes(qt)) score += 140;

      // Substring matches
      if (!nameTokens.includes(qt) && name.includes(qt)) score += 80;
      if (!brandTokens.includes(qt) && brand.includes(qt)) score += 60;
      if (!catTokens.includes(qt) && category.includes(qt)) score += 50;

      if (extra.includes(qt)) score += 40;

      // Fuzzy matches for typos (e.g. "millk" → "milk")
      let best = Infinity;
      const pools = [nameTokens, brandTokens, catTokens];
      for (const pool of pools) {
        for (const tok of pool) {
          const d = levenshtein(qt, tok);
          if (d < best) best = d;
        }
      }
      if (best === 1) score += 80;
      else if (best === 2) score += 40;
    }

    // Slight preference for cheaper items as a tie-breaker
    if (prod.price != null) {
      score += Math.max(0, 20 - Math.log10(prod.price + 1) * 5);
    }

    return score;
  }

  function searchProducts(query) {
    query = (query || "").trim();
    if (!query) return [];

    const scored = normalizedProducts
      .map((p) => ({
        product: p,
        score: scoreProduct(p, query)
      }))
      .filter((x) => x.score > 0);

    scored.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      const pa = a.product.price ?? Infinity;
      const pb = b.product.price ?? Infinity;
      return pa - pb;
    });

    return scored.map((x) => x.product);
  }

  // ---------- DOM references for search/results ----------

  const searchInput = document.getElementById("searchInput");
  const searchForm = document.getElementById("searchForm");
  const searchSummary = document.getElementById("searchSummary");
  const resultsEl = document.getElementById("results");

  // ---------- Modal elements (created if missing) ----------

  let modalOverlay,
    modalImage,
    modalTitle,
    modalBrand,
    modalPrice,
    modalRating,
    modalCategory,
    modalDescription,
    modalCloseBtn,
    modalLink;

  function ensureModal() {
    modalOverlay = document.getElementById("modalOverlay");

    // If there is no modal in the HTML, build it now
    if (!modalOverlay) {
      modalOverlay = document.createElement("div");
      modalOverlay.id = "modalOverlay";
      modalOverlay.className = "modal-overlay";
      modalOverlay.innerHTML = `
        <div class="modal-backdrop"></div>
        <div class="product-modal">
          <button class="modal-close" id="modalClose" aria-label="Close">×</button>
          <div class="modal-body">
            <div class="modal-image-wrap">
              <img id="modalImage" src="" alt="Product image">
            </div>
            <div class="modal-content">
              <h2 id="modalTitle"></h2>
              <p id="modalBrand" class="modal-brand"></p>
              <p id="modalPrice" class="modal-price"></p>
              <p id="modalRating" class="modal-rating"></p>
              <p id="modalCategory" class="modal-category"></p>
              <p id="modalDescription" class="modal-description"></p>
              <a id="modalLink"
                 class="modal-link"
                 href="#"
                 target="_blank"
                 rel="noopener noreferrer">
              </a>
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(modalOverlay);
    }

    // Grab references
    modalImage = document.getElementById("modalImage");
    modalTitle = document.getElementById("modalTitle");
    modalBrand = document.getElementById("modalBrand");
    modalPrice = document.getElementById("modalPrice");
    modalRating = document.getElementById("modalRating");
    modalCategory = document.getElementById("modalCategory");
    modalDescription = document.getElementById("modalDescription");
    modalCloseBtn = document.getElementById("modalClose");
    modalLink = document.getElementById("modalLink");

    // In case modal existed but had no link, ensure there is one
    if (!modalLink) {
      const content = document.querySelector(".modal-content");
      if (content) {
        modalLink = document.createElement("a");
        modalLink.id = "modalLink";
        modalLink.className = "modal-link";
        modalLink.target = "_blank";
        modalLink.rel = "noopener noreferrer";
        content.appendChild(modalLink);
      }
    }

    // Wire events only once
    if (modalOverlay && !modalOverlay._wired) {
      modalOverlay._wired = true;

      modalOverlay.addEventListener("click", (e) => {
        if (
          e.target === modalOverlay ||
          e.target.classList.contains("modal-backdrop")
        ) {
          closeModal();
        }
      });

      if (modalCloseBtn) {
        modalCloseBtn.addEventListener("click", closeModal);
      }

      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeModal();
      });
    }
  }

  // ---------- Rendering ----------

  function renderResults(query, products) {
    resultsEl.innerHTML = "";

    if (!query) {
      searchSummary.textContent =
        "Type a search term above to browse your scraped Walmart catalog.";
      return;
    }

    if (!products.length) {
      searchSummary.textContent = `No products found for "${query}". Try a different word (or fix typos).`;
      const div = document.createElement("div");
      div.className = "empty-state";
      div.textContent = "No matching products in your current dataset.";
      resultsEl.appendChild(div);
      return;
    }

    searchSummary.textContent = `${products.length} products found for "${query}". Sorted by best match, then lowest price.`;

    for (const prod of products) {
      const card = document.createElement("article");
      card.className = "product-card";
      card.dataset.id = prod.id;

      const priceText =
        prod.price != null ? `$${prod.price.toFixed(2)}` : "Price unavailable";

      const brandText = prod.brand || "";
      const categoryText = prod.category || "";

      const imgHtml = prod.image
        ? `<img src="${escapeHtml(prod.image)}" alt="${escapeHtml(
            prod.name || "Product image"
          )}" loading="lazy">`
        : "";

      card.innerHTML = `
        <div class="card-inner">
          <div class="product-image-wrap">
            ${imgHtml}
          </div>
          <div class="product-info">
            <h3 class="product-title">${escapeHtml(prod.name)}</h3>
            ${
              brandText
                ? `<p class="product-brand">${escapeHtml(brandText)}</p>`
                : ""
            }
            <p class="product-price">${priceText}</p>
            ${
              categoryText
                ? `<p class="product-category">${escapeHtml(
                    categoryText.toLowerCase()
                  )}</p>`
                : ""
            }
          </div>
        </div>
      `;

      // Card click -> modal
      card.addEventListener("click", () => openModal(prod));
      resultsEl.appendChild(card);
    }
  }

  // ---------- Modal behaviour ----------

  function openModal(prod) {
    ensureModal();
    if (!modalOverlay) return;

    // Image
    if (modalImage) {
      if (prod.image) {
        modalImage.src = prod.image;
        modalImage.alt = prod.name || "Product image";
      } else {
        modalImage.src = "";
        modalImage.alt = "Product image not available";
      }
    }

    // Text fields
    if (modalTitle) modalTitle.textContent = prod.name || "Product";
    if (modalBrand)
      modalBrand.textContent = prod.brand ? `by ${prod.brand}` : "";

    if (modalPrice) {
      modalPrice.textContent =
        prod.price != null ? `$${prod.price.toFixed(2)}` : "";
    }

    if (modalRating) {
      if (prod.rating != null) {
        const ratingStr = prod.rating.toFixed(1);
        const reviews =
          prod.reviewCount != null ? ` (${prod.reviewCount} reviews)` : "";
        modalRating.textContent = `Rating: ${ratingStr}★${reviews}`;
      } else {
        modalRating.textContent = "";
      }
    }

    if (modalCategory)
      modalCategory.textContent = prod.category || "";

    if (modalDescription)
      modalDescription.textContent = prod.description || "";

    // Little Walmart button under description
    if (modalLink) {
      const url = prod.url;
      if (url) {
        modalLink.href = url;
        modalLink.innerHTML = `
          <span class="walmart-spark">✦</span>
          <span>View on Walmart</span>
        `;
        modalLink.style.display = "inline-flex";
      } else {
        modalLink.style.display = "none";
      }
    }

    modalOverlay.classList.add("is-visible");
    document.body.classList.add("modal-open");
  }

  function closeModal() {
    if (!modalOverlay) return;
    modalOverlay.classList.remove("is-visible");
    document.body.classList.remove("modal-open");
  }

  // ---------- Search events ----------

  if (searchForm && searchInput) {
    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = searchInput.value || "";
      lastQuery = q;
      const results = searchProducts(q);
      renderResults(q, results);
    });

    // Live search with small debounce
    let typingTimer = null;
    searchInput.addEventListener("input", () => {
      clearTimeout(typingTimer);
      typingTimer = setTimeout(() => {
        const q = searchInput.value || "";
        lastQuery = q;
        const results = searchProducts(q);
        renderResults(q, results);
      }, 180);
    });
  }

  // ---------- Init: load products.json ----------

  async function init() {
    ensureModal(); // make sure the modal exists & events are wired

    try {
      const res = await fetch(PRODUCTS_URL);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      allProducts = Array.isArray(data.items) ? data.items : [];
      normalizedProducts = allProducts.map(normalizeProduct);

      renderResults("", []); // initial empty state
    } catch (err) {
      console.error("Failed to load products.json:", err);
      if (searchSummary) {
        searchSummary.textContent =
          "Failed to load products.json. Check that it exists next to app.py and Flask is running.";
      }
    }
  }

  init();
})();
