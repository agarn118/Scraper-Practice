// script.js
// Frontend search, scoring, modal + in-memory cart with AB container deposits

(function () {
  "use strict";

  // ------- DOM helpers -------

  const $ = (id) => document.getElementById(id);

  const searchForm = $("searchForm");
  const searchInput = $("searchInput");
  const searchSummary = $("searchSummary");
  const resultsEl = $("results");

  const modalOverlay = $("modalOverlay");
  const modalCloseBtn = $("modalCloseBtn");
  const modalImage = $("modalImage");
  const modalTitle = $("modalTitle");
  const modalBrand = $("modalBrand");
  const modalPrice = $("modalPrice");
  const modalRating = $("modalRating");
  const modalCategory = $("modalCategory");
  const modalDescription = $("modalDescription");
  const modalStoreLink = $("modalStoreLink");
  const addToCartBtn = $("addToCartBtn");

  const cartFab = $("cartFab");

  // Cart overlay elements (created dynamically)
  let cartOverlay = null;
  let cartItemsEl = null;
  let cartItemCountEl = null;
  let cartSubtotalEl = null;
  let cartDepositsEl = null;
  let cartTotalPriceEl = null;
  let cartCloseBtn = null;
  let cartClearBtn = null;

  // ------- Data state -------

  let allProducts = [];
  let currentProduct = null;

  // Simple in-memory cart: Map<id, { product, qty }>
  const cart = new Map();

  // ------- Utils -------

  const cleanText = (s) => (s || "").toString().toLowerCase();

  function tokenize(s) {
    return cleanText(s)
      .split(/[^a-z0-9%]+/g)
      .filter(Boolean);
  }

  function parsePrice(x) {
    if (x == null) return null;
    const num = parseFloat(String(x).replace(/[^\d.]/g, ""));
    return Number.isFinite(num) ? num : null;
  }

  function formatPrice(p) {
    if (p == null || !Number.isFinite(p)) return "";
    return `$${p.toFixed(2)}`;
  }

  // Levenshtein distance for fuzzy matching
  function levenshtein(a, b) {
    a = cleanText(a);
    b = cleanText(b);
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
        dp[j] = Math.min(dp[j] + 1, dp[j - 1] + 1, prev + cost);
        prev = tmp;
      }
    }
    return dp[n];
  }

  // ------- Alberta deposit estimator -------

  // Estimate deposit for ONE store "unit" (one product card).
  // If it's a 6 x 200 mL pack, this returns deposit for all 6 bottles in the pack.
  function estimateDepositFromText(text) {
    if (!text) return 0;
    const s = text.replace(/,/g, " ");
    let deposit = 0;

    // 6 x 200 mL, 12x355mL, etc.
    const packRegex =
      /(\d+)\s*[xX]\s*(\d+(?:\.\d+)?)\s*(mL|ml|ML|l|L|litre|liter)/g;
    let m;
    let foundPack = false;

    while ((m = packRegex.exec(s)) !== null) {
      foundPack = true;
      const count = parseInt(m[1], 10) || 1;
      const volNum = parseFloat(m[2]) || 0;
      const unit = m[3].toLowerCase();
      let litres = unit.startsWith("m") ? volNum / 1000 : volNum;
      const rate = litres <= 1 ? 0.1 : 0.25;
      deposit += count * rate;
    }

    // If we already saw an explicit "6 x 200 mL" style string,
    // don't also treat "200 mL" alone as a separate container.
    if (foundPack) return deposit;

    // Single container size: 1L, 946 mL, 2 L, etc.
    const singleRegex =
      /(\d+(?:\.\d+)?)\s*(mL|ml|ML|l|L|litre|liter)\b/;
    const m2 = singleRegex.exec(s);
    if (m2) {
      const volNum = parseFloat(m2[1]) || 0;
      const unit = m2[2].toLowerCase();
      let litres = unit.startsWith("m") ? volNum / 1000 : volNum;
      const rate = litres <= 1 ? 0.1 : 0.25;
      deposit += rate;
    }

    return deposit;
  }

  // ------- Normalization -------

  function normalizeProduct(raw) {
    const name =
      raw.product_name || raw.name || raw.title || "Unnamed product";
    const brand = raw.brand || raw.merchant || raw.sellerName || "";
    const category =
      raw.category ||
      (Array.isArray(raw.search_queries) ? raw.search_queries[0] : "") ||
      raw.department ||
      "";
    const description =
      raw.long_description || raw.short_description || raw.description || "";

    const price = parsePrice(raw.price);
    const rating = raw.avg_rating != null ? Number(raw.avg_rating) : null;
    const ratingCount =
      raw.review_count != null ? Number(raw.review_count) : null;

    const image =
      raw.image_url ||
      raw.image ||
      raw.thumbnail ||
      raw.imageUrl ||
      "";

    const url =
      raw.url ||
      raw.product_url ||
      raw.productUrl ||
      raw.item_url ||
      raw.link ||
      "";

    const id =
      raw.item_id ||
      raw.sku ||
      raw.id ||
      `${name}-${brand}`.replace(/\s+/g, "_");

    const searchBlob = `${name} ${brand} ${category}`;
    const tokens = tokenize(searchBlob);

    // Try to pull any size hints we might have
    const sizeHints = [
      raw.size,
      raw.package_size,
      raw.unit_size,
      raw.package,
      raw.short_title,
    ]
      .filter(Boolean)
      .join(" ");

    // Use name + description + size hints to estimate deposit
    const depositPerUnit = estimateDepositFromText(
      `${name} ${description} ${sizeHints}`
    );

    return {
      id,
      name,
      brand,
      category,
      description,
      price,
      priceFormatted: formatPrice(price),
      rating,
      ratingCount,
      image,
      url,
      depositPerUnit, // deposit for one store "unit" (pack or bottle)
      nameLower: cleanText(name),
      brandLower: cleanText(brand),
      categoryLower: cleanText(category),
      tokens,
    };
  }

  // ------- Scoring / search -------

  function scoreProduct(product, qTokens) {
    if (!qTokens.length) return 0;
    let score = 0;
    const name = product.nameLower;
    const brand = product.brandLower;
    const cat = product.categoryLower;

    for (const qt of qTokens) {
      if (!qt) continue;

      // strong matches in the name
      if (name.startsWith(qt)) score += 10;
      else if (name.includes(qt)) score += 6;

      // brand matches
      if (brand.startsWith(qt)) score += 4;
      else if (brand.includes(qt)) score += 2;

      // category / other
      if (cat.includes(qt)) score += 1;

      // fuzzy against product tokens (handles "millk" -> "milk")
      let bestSim = 0;
      for (const pt of product.tokens) {
        const maxLen = Math.max(qt.length, pt.length);
        if (maxLen === 0) continue;
        const dist = levenshtein(qt, pt);
        const sim = 1 - dist / maxLen; // 0..1
        if (sim > bestSim) bestSim = sim;
        if (bestSim >= 0.95) break;
      }
      if (bestSim >= 0.7) {
        score += 4 * bestSim; // up to +4
      }
    }

    // Slight nudge for cheaper items and higher ratings
    if (product.price != null && Number.isFinite(product.price)) {
      score += 1 / (1 + product.price * 0.04);
    }
    if (product.rating != null && Number.isFinite(product.rating)) {
      score += product.rating * 0.15;
    }

    return score;
  }

  function runSearch(rawQuery) {
    const q = (rawQuery || "").trim();
    if (!q) {
      resultsEl.innerHTML = "";
      searchSummary.textContent =
        "Type a search term above to browse your scraped Walmart catalog.";
      return;
    }

    const qTokens = tokenize(q);

    const scored = allProducts
      .map((p) => ({
        product: p,
        score: scoreProduct(p, qTokens),
      }))
      .filter((x) => x.score > 0.5);

    scored.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      const ap = a.product.price ?? Infinity;
      const bp = b.product.price ?? Infinity;
      if (ap !== bp) return ap - bp;
      return a.product.name.localeCompare(b.product.name);
    });

    const matches = scored.map((x) => x.product);
    renderResults(matches);

    searchSummary.textContent = `${matches.length.toLocaleString()} products found for "${q}". Sorted by best match, then lowest price.`;
  }

  // ------- Rendering -------

  function renderResults(products) {
    if (!products.length) {
      resultsEl.innerHTML =
        '<div class="empty-state">No products matched your search.</div>';
      return;
    }

    const frag = document.createDocumentFragment();

    for (const p of products) {
      const card = document.createElement("article");
      card.className = "product-card";
      card.dataset.id = p.id;

      const inner = document.createElement("div");
      inner.className = "card-inner";

      const imgWrap = document.createElement("div");
      imgWrap.className = "product-image-wrap";

      const img = document.createElement("img");
      img.src = p.image || "";
      img.alt = p.name;
      img.loading = "lazy";
      imgWrap.appendChild(img);

      const info = document.createElement("div");
      info.className = "product-info";

      const titleEl = document.createElement("h3");
      titleEl.className = "product-title";
      titleEl.textContent = p.name;

      const brandEl = document.createElement("p");
      brandEl.className = "product-brand";
      brandEl.textContent = p.brand || "";

      const priceEl = document.createElement("p");
      priceEl.className = "product-price";
      priceEl.textContent = p.priceFormatted || "";

      const catEl = document.createElement("p");
      catEl.className = "product-category";
      catEl.textContent = p.category || "";

      info.appendChild(titleEl);
      info.appendChild(brandEl);
      info.appendChild(priceEl);
      info.appendChild(catEl);

      inner.appendChild(imgWrap);
      inner.appendChild(info);
      card.appendChild(inner);

      card.addEventListener("click", () => openProductModal(p));

      frag.appendChild(card);
    }

    resultsEl.innerHTML = "";
    resultsEl.appendChild(frag);
  }

  // ------- Product modal logic -------

  function openProductModal(product) {
    currentProduct = product;

    modalTitle.textContent = product.name;
    modalBrand.textContent = product.brand ? `by ${product.brand}` : "";
    modalPrice.textContent = product.priceFormatted || "";
    if (
      product.rating != null &&
      Number.isFinite(product.rating) &&
      product.ratingCount != null
    ) {
      modalRating.textContent = `Rating: ${product.rating.toFixed(
        1
      )}★ (${product.ratingCount} reviews)`;
    } else if (product.rating != null && Number.isFinite(product.rating)) {
      modalRating.textContent = `Rating: ${product.rating.toFixed(1)}★`;
    } else {
      modalRating.textContent = "";
    }
    modalCategory.textContent = product.category || "";
    modalDescription.textContent =
      product.description || "No description available for this product.";

    if (product.image) {
      modalImage.src = product.image;
      modalImage.alt = product.name;
    } else {
      modalImage.removeAttribute("src");
      modalImage.alt = "Product image";
    }

    // View on Walmart – fall back to a search URL if we don't have the exact one
    let storeUrl = product.url;
    if (
      !storeUrl ||
      storeUrl === "null" ||
      storeUrl === "undefined" ||
      storeUrl === "#"
    ) {
      storeUrl =
        "https://www.walmart.ca/search?q=" +
        encodeURIComponent(product.name || "");
    }
    if (modalStoreLink) {
      modalStoreLink.href = storeUrl;
      modalStoreLink.classList.remove("is-hidden");
    }

    modalOverlay.classList.add("is-visible");
    document.body.classList.add("modal-open");
  }

  function closeModal() {
    modalOverlay.classList.remove("is-visible");
    currentProduct = null;
    // Only unlock scroll if cart overlay isn't open
    if (!cartOverlay || !cartOverlay.classList.contains("is-visible")) {
      document.body.classList.remove("modal-open");
    }
  }

  // ------- Cart core logic (with deposits) -------

  function addToCart(product) {
    if (!product || !product.id) return;
    const existing = cart.get(product.id) || { product, qty: 0 };
    existing.qty += 1;
    cart.set(product.id, existing);
    updateCartSummary();
  }

  function calculateCartTotals() {
    let totalItems = 0;
    let subtotal = 0;
    let deposits = 0;

    for (const { product, qty } of cart.values()) {
      totalItems += qty;
      if (product.price != null && Number.isFinite(product.price)) {
        subtotal += product.price * qty;
      }
      if (
        product.depositPerUnit != null &&
        Number.isFinite(product.depositPerUnit)
      ) {
        deposits += product.depositPerUnit * qty;
      }
    }

    const grandTotal = subtotal + deposits;
    return { totalItems, subtotal, deposits, grandTotal };
  }

  function updateCartSummary() {
    const { totalItems, grandTotal } = calculateCartTotals();

    if (cartFab) {
      const label = `Cart · ${totalItems} item${
        totalItems === 1 ? "" : "s"
      } · $${grandTotal.toFixed(2)} est.`;
      cartFab.textContent = label;

      // little pulse animation class, if CSS defines it
      cartFab.classList.remove("pulse");
      void cartFab.offsetWidth;
      cartFab.classList.add("pulse");
    }

    // If the cart panel is open, refresh its contents
    if (cartOverlay && cartOverlay.classList.contains("is-visible")) {
      renderCartOverlay();
    }
  }

  // ------- Cart overlay creation / rendering -------

  function createCartOverlay() {
    cartOverlay = document.createElement("div");
    cartOverlay.id = "cartOverlay";
    cartOverlay.className = "modal-overlay";

    cartOverlay.innerHTML = `
      <div class="modal-backdrop" data-role="cart-backdrop"></div>
      <section class="product-modal" style="max-width: 720px; display: flex; flex-direction: column;">
        <button type="button" class="modal-close cart-close" aria-label="Close cart">&times;</button>
        <div class="modal-body" style="flex-direction: column; gap: 12px;">
          <div style="display:flex; justify-content: space-between; align-items:center; margin-bottom: 4px;">
            <h2 style="margin:0; font-size:18px; font-weight:700; color:#0f172a;">Your Cart</h2>
          </div>
          <div id="cartItems" style="max-height:340px; overflow-y:auto; padding-right:4px;"></div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
            <div style="display:flex; flex-direction:column; gap:2px; font-size:13px;">
              <span id="cartItemCount">0 items</span>
              <span id="cartSubtotal">Subtotal (before taxes & fees): $0.00</span>
              <span id="cartDeposits">Estimated taxes & fees: $0.00</span>
              <span id="cartTotalPrice" style="font-weight:700; color:#1d4ed8;">Total Estimated: $0.00</span>
            </div>
            <button type="button" class="cart-clear-btn" style="
                border:none;
                border-radius:999px;
                padding:7px 14px;
                font-size:12px;
                cursor:pointer;
                background:#fee2e2;
                color:#b91c1c;
            ">Clear cart</button>
          </div>
        </div>
      </section>
    `;

    document.body.appendChild(cartOverlay);

    cartItemsEl = cartOverlay.querySelector("#cartItems");
    cartItemCountEl = cartOverlay.querySelector("#cartItemCount");
    cartSubtotalEl = cartOverlay.querySelector("#cartSubtotal");
    cartDepositsEl = cartOverlay.querySelector("#cartDeposits");
    cartTotalPriceEl = cartOverlay.querySelector("#cartTotalPrice");
    cartCloseBtn = cartOverlay.querySelector(".cart-close");
    cartClearBtn = cartOverlay.querySelector(".cart-clear-btn");

    const cartBackdrop = cartOverlay.querySelector("[data-role='cart-backdrop']");

    cartCloseBtn.addEventListener("click", closeCartOverlay);
    if (cartBackdrop) {
      cartBackdrop.addEventListener("click", closeCartOverlay);
    }
    cartClearBtn.addEventListener("click", () => {
      cart.clear();
      updateCartSummary();
      renderCartOverlay();
    });

    // quantity +/- buttons via event delegation
    cartItemsEl.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-action]");
      if (!btn) return;
      const id = btn.dataset.id;
      const action = btn.dataset.action;
      const entry = cart.get(id);
      if (!entry) return;

      if (action === "inc") {
        entry.qty += 1;
      } else if (action === "dec") {
        entry.qty -= 1;
        if (entry.qty <= 0) {
          cart.delete(id);
        }
      }
      updateCartSummary();
      renderCartOverlay();
    });
  }

  function renderCartOverlay() {
    if (!cartItemsEl) return;

    cartItemsEl.innerHTML = "";

    if (cart.size === 0) {
      const empty = document.createElement("p");
      empty.textContent = "Your cart is empty.";
      empty.style.fontSize = "13px";
      empty.style.color = "#6b7280";
      cartItemsEl.appendChild(empty);
    } else {
      const frag = document.createDocumentFragment();
      for (const [id, { product, qty }] of cart.entries()) {
        const row = document.createElement("div");
        row.style.display = "flex";
        row.style.alignItems = "center";
        row.style.justifyContent = "space-between";
        row.style.gap = "12px";
        row.style.padding = "8px 0";
        row.style.borderBottom = "1px solid #e5e7eb";

        const main = document.createElement("div");
        main.style.display = "flex";
        main.style.alignItems = "center";
        main.style.gap = "10px";
        main.style.flex = "1";

        const img = document.createElement("img");
        img.src = product.image || "";
        img.alt = product.name;
        img.loading = "lazy";
        img.style.width = "52px";
        img.style.height = "52px";
        img.style.objectFit = "contain";
        img.style.borderRadius = "12px";
        img.style.background = "#f3f4f6";

        const info = document.createElement("div");
        info.style.display = "flex";
        info.style.flexDirection = "column";
        info.style.gap = "2px";

        const title = document.createElement("div");
        title.textContent = product.name;
        title.style.fontSize = "13px";
        title.style.fontWeight = "600";
        title.style.color = "#111827";

        const brand = document.createElement("div");
        brand.textContent = product.brand || "";
        brand.style.fontSize = "11px";
        brand.style.color = "#6b7280";

        const price = document.createElement("div");
        price.textContent = product.priceFormatted || "";
        price.style.fontSize = "12px";
        price.style.color = "#1d4ed8";
        price.style.fontWeight = "600";

        info.appendChild(title);
        info.appendChild(brand);
        info.appendChild(price);

        main.appendChild(img);
        main.appendChild(info);

        const qtyBox = document.createElement("div");
        qtyBox.style.display = "flex";
        qtyBox.style.alignItems = "center";
        qtyBox.style.gap = "6px";

        const decBtn = document.createElement("button");
        decBtn.type = "button";
        decBtn.dataset.action = "dec";
        decBtn.dataset.id = id;
        decBtn.textContent = "−";
        decBtn.style.width = "24px";
        decBtn.style.height = "24px";
        decBtn.style.borderRadius = "999px";
        decBtn.style.border = "none";
        decBtn.style.background = "#e5e7eb";
        decBtn.style.cursor = "pointer";
        decBtn.style.fontSize = "14px";

        const qtySpan = document.createElement("span");
        qtySpan.textContent = String(qty);
        qtySpan.style.minWidth = "16px";
        qtySpan.style.textAlign = "center";
        qtySpan.style.fontSize = "13px";

        const incBtn = document.createElement("button");
        incBtn.type = "button";
        incBtn.dataset.action = "inc";
        incBtn.dataset.id = id;
        incBtn.textContent = "+";
        incBtn.style.width = "24px";
        incBtn.style.height = "24px";
        incBtn.style.borderRadius = "999px";
        incBtn.style.border = "none";
        incBtn.style.background = "#e5e7eb";
        incBtn.style.cursor = "pointer";
        incBtn.style.fontSize = "14px";

        qtyBox.appendChild(decBtn);
        qtyBox.appendChild(qtySpan);
        qtyBox.appendChild(incBtn);

        row.appendChild(main);
        row.appendChild(qtyBox);

        frag.appendChild(row);
      }
      cartItemsEl.appendChild(frag);
    }

    const { totalItems, subtotal, deposits, grandTotal } =
      calculateCartTotals();

    if (cartItemCountEl) {
      cartItemCountEl.textContent = `${totalItems} item${
        totalItems === 1 ? "" : "s"
      }`;
    }
    if (cartSubtotalEl) {
      cartSubtotalEl.textContent = `Subtotal (before taxes & fees): $${subtotal.toFixed(
        2
      )}`;
    }
    if (cartDepositsEl) {
      cartDepositsEl.textContent = `Estimated taxes & fees: $${deposits.toFixed(
        2
      )}`;
    }
    if (cartTotalPriceEl) {
      cartTotalPriceEl.textContent = `Total Estimated: $${grandTotal.toFixed(
        2
      )}`;
    }
  }

  function openCartOverlay() {
    if (!cartOverlay) return;
    renderCartOverlay();
    cartOverlay.classList.add("is-visible");
    document.body.classList.add("modal-open");
  }

  function closeCartOverlay() {
    if (!cartOverlay) return;
    cartOverlay.classList.remove("is-visible");
    // Only unlock scroll if product modal isn't open
    if (!modalOverlay.classList.contains("is-visible")) {
      document.body.classList.remove("modal-open");
    }
  }

  // ------- Init -------

  async function init() {
    // Build the cart overlay HTML once
    createCartOverlay();

    try {
      const res = await fetch("products.json");
      const data = await res.json();
      const rawItems = Array.isArray(data.items) ? data.items : [];
      allProducts = rawItems.map(normalizeProduct);
    } catch (err) {
      console.error("Failed to load products.json", err);
      searchSummary.textContent =
        "Failed to load products.json. Make sure it exists next to index.html.";
    }

    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      runSearch(searchInput.value);
    });

    // Clear results when input is cleared
    searchInput.addEventListener("input", () => {
      if (!searchInput.value.trim()) {
        resultsEl.innerHTML = "";
        searchSummary.textContent =
          "Type a search term above to browse your scraped Walmart catalog.";
      }
    });

    modalCloseBtn.addEventListener("click", closeModal);
    const backdrop = modalOverlay.querySelector("[data-role='modal-backdrop']");
    if (backdrop) {
      backdrop.addEventListener("click", closeModal);
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (cartOverlay && cartOverlay.classList.contains("is-visible")) {
          closeCartOverlay();
        } else if (modalOverlay.classList.contains("is-visible")) {
          closeModal();
        }
      }
    });

    addToCartBtn.addEventListener("click", () => {
      if (currentProduct) {
        addToCart(currentProduct);
        // quick button feedback
        const originalText = addToCartBtn.textContent;
        addToCartBtn.textContent = "Added!";
        addToCartBtn.disabled = true;
        setTimeout(() => {
          addToCartBtn.textContent = originalText;
          addToCartBtn.disabled = false;
        }, 700);
      }
    });

    if (cartFab) {
      cartFab.addEventListener("click", openCartOverlay);
    }

    // Initialise cart pill text
    updateCartSummary();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
