// script.js - STORE-SWITCHABLE CART SYSTEM
"use strict";

// Cart items: [{ productId, product, selectedStoreIndex, quantity }]
window.cartItems = window.cartItems || [];

document.addEventListener("DOMContentLoaded", () => {
  console.log("DOM loaded, initializing store-switchable cart...");
  
  const resultsEl = document.getElementById("results");
  const searchInputEl = document.getElementById("searchInput");
  const searchFormEl = document.getElementById("searchForm");
  const searchButtonEl = document.querySelector(".search-button");
  const searchSummaryEl = document.getElementById("searchSummary");
  const cartSummaryEl = document.getElementById("cartFab");

  let allProducts = [];
  let currentResults = [];
  let currentModalProduct = null;

  const productModal = createProductModal();
  const cartModal = createCartModal();

  wireEvents();
  loadProducts();
  updateCartDisplay();

  function wireEvents() {
    if (searchFormEl) {
      searchFormEl.addEventListener("submit", (e) => {
        e.preventDefault();
        handleSearch();
      });
    }
    if (searchButtonEl) {
      searchButtonEl.addEventListener("click", (e) => {
        e.preventDefault();
        handleSearch();
      });
    }
    if (searchInputEl) {
      searchInputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          handleSearch();
        }
      });
    }

    if (resultsEl) {
      resultsEl.addEventListener("click", (e) => {
        const card = e.target.closest(".product-card");
        if (!card) return;
        const id = Number(card.getAttribute("data-product-id"));
        const product = currentResults.find((p) => p.id === id);
        if (product) openProductModal(product);
      });
    }

    productModal.overlay.addEventListener("click", (e) => {
      if (e.target === productModal.overlay || e.target === productModal.closeBtn) {
        closeProductModal();
      }
    });

    if (cartSummaryEl) {
      cartSummaryEl.addEventListener("click", () => {
        openCartModal();
      });
    }

    cartModal.overlay.addEventListener("click", (e) => {
      if (e.target === cartModal.overlay || e.target === cartModal.closeBtn) {
        closeCartModal();
      }
    });

    cartModal.clearBtn.addEventListener("click", () => {
      window.cartItems = [];
      updateCartDisplay();
      renderCartModal();
    });
  }

  async function loadProducts() {
    try {
      const res = await fetch("/products.json");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      allProducts = Array.isArray(data.items) ? data.items : [];
      currentResults = [];
      if (resultsEl) resultsEl.innerHTML = "";
      if (searchSummaryEl) {
        searchSummaryEl.textContent = "Type a search term above to browse your scraped catalog.";
      }
      console.log(`Loaded ${allProducts.length} products`);
    } catch (err) {
      console.error("Failed to load products:", err);
      if (searchSummaryEl) {
        searchSummaryEl.textContent = "Failed to load products.";
      }
    }
  }

  function handleSearch() {
    if (!allProducts.length) return;
    const rawQuery = (searchInputEl?.value || "").trim();
    const query = rawQuery.toLowerCase();

    if (!query) {
      currentResults = [];
      if (resultsEl) resultsEl.innerHTML = "";
      if (searchSummaryEl) {
        searchSummaryEl.textContent = "Type a search term above to browse your scraped catalog.";
      }
      return;
    }

    const tokens = query.split(/\s+/).filter(Boolean);
    const scored = allProducts
      .map((item) => ({ item, score: scoreProduct(item, tokens) }))
      .filter((x) => x.score > 0);

    scored.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      const ap = a.item.min_price ?? Number.POSITIVE_INFINITY;
      const bp = b.item.min_price ?? Number.POSITIVE_INFINITY;
      return ap - bp;
    });

    currentResults = scored.map((x) => x.item);
    renderResults(currentResults, rawQuery);
  }

  function scoreProduct(item, tokens) {
    const title = (item.title || "").toLowerCase();
    const brand = (item.brand || "").toLowerCase();
    const desc = (item.description || "").toLowerCase();
    const queries = (item.search_queries || []).join(" ").toLowerCase();

    let score = 0;
    for (const t of tokens) {
      if (title.includes(t)) score += 6;
      if (brand.includes(t)) score += 4;
      if (queries.includes(t)) score += 3;
      if (desc.includes(t)) score += 1;
    }
    return score;
  }

  function renderResults(items, rawQuery) {
    if (!resultsEl) return;
    resultsEl.innerHTML = "";

    if (!items || !items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No products found. Try a different search term.";
      resultsEl.appendChild(empty);
      if (searchSummaryEl) {
        searchSummaryEl.textContent = rawQuery 
          ? `No products found for "${rawQuery}".`
          : "Type a search term above to browse your scraped catalog.";
      }
      return;
    }

    for (const product of items) {
      resultsEl.appendChild(createProductCard(product));
    }

    if (searchSummaryEl) {
      const q = rawQuery ? ` for "${rawQuery}"` : "";
      searchSummaryEl.textContent = `${items.length.toLocaleString()} products found${q}. Sorted by best match, then lowest price.`;
    }
  }

  function createProductCard(product) {
    const firstOffer = (product.offers && product.offers[0]) || {};
    const priceDisplay = product.min_price_display || firstOffer.price || "";

    const card = document.createElement("div");
    card.className = "product-card";
    card.setAttribute("data-product-id", String(product.id));

    const imgUrl = product.image_url || firstOffer.image_url || "";
    const brand = product.brand || "";

    card.innerHTML = `
      <div class="card-inner">
        <div class="product-image-wrap">
          ${imgUrl ? `<img src="${imgUrl}" alt="${escapeHtml(product.title || "")}">` : ""}
        </div>
        <div class="product-info">
          <h3 class="product-title">${escapeHtml(product.title || "")}</h3>
          <p class="product-brand">${escapeHtml(brand)}</p>
          <p class="product-price">${priceDisplay || ""}</p>
          ${product.store_count > 1 ? `<p class="product-stores">Available at ${product.store_count} stores</p>` : ""}
        </div>
      </div>
    `;
    return card;
  }

  function openProductModal(product) {
    currentModalProduct = product;
    const firstOffer = (product.offers && product.offers[0]) || {};

    const imgUrl = product.image_url || firstOffer.image_url || "";
    if (imgUrl) {
      productModal.imgEl.src = imgUrl;
      productModal.imgEl.alt = product.title || "";
    } else {
      productModal.imgEl.removeAttribute("src");
      productModal.imgEl.alt = "";
    }

    productModal.titleEl.textContent = product.title || "";
    productModal.brandEl.textContent = product.brand ? `by ${product.brand}` : "";
    productModal.priceEl.textContent = product.min_price_display ? `From ${product.min_price_display}` : "";

    const offerWithRating = product.offers?.find((o) => o.avg_rating) || firstOffer;
    if (offerWithRating.avg_rating && offerWithRating.review_count) {
      productModal.ratingEl.textContent = `Rating: ${offerWithRating.avg_rating.toFixed(1)}★ (${offerWithRating.review_count} reviews)`;
    } else if (offerWithRating.avg_rating) {
      productModal.ratingEl.textContent = `Rating: ${offerWithRating.avg_rating.toFixed(1)}★`;
    } else {
      productModal.ratingEl.textContent = "";
    }

    const category = (product.search_queries && product.search_queries[0]) || "";
    productModal.categoryEl.textContent = category || "";

    productModal.descriptionEl.innerHTML = "";
    if (product.description) {
      productModal.descriptionEl.innerHTML = product.description;
    } else if (product.short_description) {
      productModal.descriptionEl.textContent = product.short_description;
    }

    renderStoreOptions(product);

    productModal.overlay.classList.add("is-visible");
    document.body.classList.add("modal-open");
  }

  function renderStoreOptions(product) {
    productModal.storeOptionsEl.innerHTML = "";

    if (!product.offers || !product.offers.length) {
      productModal.storeOptionsEl.innerHTML = "<p>No offers available</p>";
      productModal.addToCartBtn.style.display = "none";
      return;
    }

    const heading = document.createElement("h3");
    heading.textContent = "Available at:";
    heading.className = "store-options-heading";
    productModal.storeOptionsEl.appendChild(heading);

    const sortedOffers = [...product.offers].sort((a, b) => {
      const priceA = a.price_numeric || 999999;
      const priceB = b.price_numeric || 999999;
      return priceA - priceB;
    });

    for (const offer of sortedOffers) {
      const storeOption = document.createElement("div");
      storeOption.className = "store-option";

      const storeName = offer.store_name || offer.store || "Store";
      const price = offer.price || (typeof offer.price_numeric === "number" ? `$${offer.price_numeric.toFixed(2)}` : "");
      const inventory = offer.inventory_status || "";
      const isInStock = inventory.toLowerCase().includes("in stock") || inventory.toLowerCase().includes("available");

      storeOption.innerHTML = `
        <div class="store-option-info">
          <span class="store-option-name">${escapeHtml(storeName)}</span>
          <span class="store-option-price">${price}</span>
          ${inventory ? `<span class="store-option-inventory ${isInStock ? "in-stock" : "out-stock"}">${escapeHtml(inventory)}</span>` : ""}
        </div>
        ${offer.link ? `<a href="${offer.link}" target="_blank" rel="noopener noreferrer" class="store-option-link">View</a>` : ""}
      `;

      productModal.storeOptionsEl.appendChild(storeOption);
    }

    // Show single add to cart button
    productModal.addToCartBtn.style.display = "inline-block";
    productModal.addToCartBtn.onclick = () => {
      addToCart(product);
      productModal.addToCartBtn.textContent = "Added!";
      productModal.addToCartBtn.style.background = "#10b981";
      setTimeout(() => {
        productModal.addToCartBtn.textContent = "Add to cart";
        productModal.addToCartBtn.style.background = "";
      }, 1000);
    };
  }

  function closeProductModal() {
    currentModalProduct = null;
    productModal.overlay.classList.remove("is-visible");
    document.body.classList.remove("modal-open");
  }

  // ========== CART FUNCTIONS ==========

  function addToCart(product) {
    console.log("Adding product to cart:", product.title);
    
    // Check if product already in cart
    const existing = window.cartItems.find((item) => item.productId === product.id);
    if (existing) {
      existing.quantity += 1;
      console.log("Increased quantity to:", existing.quantity);
    } else {
      // Default to cheapest store (index 0 after sorting)
      const sortedOffers = [...product.offers].sort((a, b) => {
        const priceA = a.price_numeric || 999999;
        const priceB = b.price_numeric || 999999;
        return priceA - priceB;
      });
      
      window.cartItems.push({
        productId: product.id,
        product: product,
        selectedStoreIndex: 0, // Index in sortedOffers
        quantity: 1
      });
      console.log("Added new item, cart now has:", window.cartItems.length, "items");
    }

    updateCartDisplay();
  }

  function updateCartDisplay() {
    console.log("Updating cart display, items:", window.cartItems.length);
    
    if (!cartSummaryEl) {
      console.error("cartSummaryEl not found!");
      return;
    }

    const totals = computeCartTotals();
    const totalDisplay = totals.totalEstimated > 0 ? `$${totals.totalEstimated.toFixed(2)}` : "$0.00";
    const itemText = totals.itemCount === 1 ? "item" : "items";
    
    cartSummaryEl.textContent = `Cart · ${totals.itemCount} ${itemText} · ${totalDisplay}`;
  }

  function computeCartTotals() {
    let itemCount = 0;
    let subtotal = 0;

    for (const entry of window.cartItems) {
      const sortedOffers = [...entry.product.offers].sort((a, b) => {
        const priceA = a.price_numeric || 999999;
        const priceB = b.price_numeric || 999999;
        return priceA - priceB;
      });
      
      const selectedOffer = sortedOffers[entry.selectedStoreIndex] || sortedOffers[0];
      const price = typeof selectedOffer.price_numeric === "number"
        ? selectedOffer.price_numeric
        : parseFloat((selectedOffer.price_raw || "").replace("$", "")) || 0;

      itemCount += entry.quantity;
      subtotal += price * entry.quantity;
    }

    const gstRate = 0.05;
    const gst = subtotal * gstRate;
    const totalEstimated = subtotal + gst;

    return { itemCount, subtotal, gst, totalEstimated };
  }

  function openCartModal() {
    renderCartModal();
    cartModal.overlay.classList.add("is-visible");
    document.body.classList.add("modal-open");
  }

  function closeCartModal() {
    cartModal.overlay.classList.remove("is-visible");
    document.body.classList.remove("modal-open");
  }

  function renderCartModal() {
    cartModal.itemsEl.innerHTML = "";

    if (!window.cartItems.length) {
      const empty = document.createElement("p");
      empty.textContent = "Your cart is currently empty.";
      cartModal.itemsEl.appendChild(empty);

      cartModal.subtotalEl.textContent = "$0.00";
      cartModal.gstEl.textContent = "$0.00";
      cartModal.totalEl.textContent = "$0.00";
      return;
    }

    for (const entry of window.cartItems) {
      const row = document.createElement("div");
      row.className = "cart-item";

      // Sort offers by price
      const sortedOffers = [...entry.product.offers].sort((a, b) => {
        const priceA = a.price_numeric || 999999;
        const priceB = b.price_numeric || 999999;
        return priceA - priceB;
      });

      const selectedOffer = sortedOffers[entry.selectedStoreIndex] || sortedOffers[0];
      const imgUrl = entry.product.image_url || selectedOffer.image_url || "";

      row.innerHTML = `
        <div class="cart-item-image">
          ${imgUrl ? `<img src="${imgUrl}" alt="${escapeHtml(entry.product.title || "")}">` : ""}
        </div>
        <div class="cart-item-details">
          <div class="cart-item-title">${escapeHtml(entry.product.title || "")}</div>
          <div class="cart-item-brand">${escapeHtml(entry.product.brand || "")}</div>
          <div class="cart-item-store-selector"></div>
        </div>
        <div class="cart-item-controls">
          <div class="cart-item-qty">
            <button class="qty-btn qty-dec" aria-label="Decrease quantity">−</button>
            <span class="qty-val">${entry.quantity}</span>
            <button class="qty-btn qty-inc" aria-label="Increase quantity">+</button>
          </div>
          <button class="cart-item-remove" aria-label="Remove item">×</button>
        </div>
      `;

      // Store selector dropdown
      const storeSelectorEl = row.querySelector(".cart-item-store-selector");
      if (sortedOffers.length > 1) {
        const select = document.createElement("select");
        select.className = "store-selector";
        
        sortedOffers.forEach((offer, idx) => {
          const option = document.createElement("option");
          option.value = idx;
          option.selected = idx === entry.selectedStoreIndex;
          const price = offer.price || (typeof offer.price_numeric === "number" ? `$${offer.price_numeric.toFixed(2)}` : "");
          option.textContent = `${offer.store_name || offer.store} - ${price}`;
          select.appendChild(option);
        });

        select.addEventListener("change", (e) => {
          entry.selectedStoreIndex = Number(e.target.value);
          updateCartDisplay();
          renderCartModal();
        });

        storeSelectorEl.appendChild(select);
      } else {
        const price = selectedOffer.price || (typeof selectedOffer.price_numeric === "number" ? `$${selectedOffer.price_numeric.toFixed(2)}` : "");
        storeSelectorEl.textContent = `${selectedOffer.store_name || selectedOffer.store} - ${price}`;
      }

      // Quantity controls
      const decBtn = row.querySelector(".qty-dec");
      const incBtn = row.querySelector(".qty-inc");
      const removeBtn = row.querySelector(".cart-item-remove");

      decBtn.addEventListener("click", () => {
        if (entry.quantity > 1) {
          entry.quantity -= 1;
        } else {
          window.cartItems = window.cartItems.filter((i) => i.productId !== entry.productId);
        }
        updateCartDisplay();
        renderCartModal();
      });

      incBtn.addEventListener("click", () => {
        entry.quantity += 1;
        updateCartDisplay();
        renderCartModal();
      });

      removeBtn.addEventListener("click", () => {
        window.cartItems = window.cartItems.filter((i) => i.productId !== entry.productId);
        updateCartDisplay();
        renderCartModal();
      });

      cartModal.itemsEl.appendChild(row);
    }

    const totals = computeCartTotals();
    cartModal.subtotalEl.textContent = `$${totals.subtotal.toFixed(2)}`;
    cartModal.gstEl.textContent = `$${totals.gst.toFixed(2)}`;
    cartModal.totalEl.textContent = `$${totals.totalEstimated.toFixed(2)}`;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function createProductModal() {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-backdrop"></div>
      <div class="product-modal">
        <button class="modal-close" aria-label="Close">×</button>
        <div class="modal-body">
          <div class="modal-image-wrap">
            <img id="modalImage" src="" alt="">
          </div>
          <div class="modal-content">
            <h2 id="modalTitle"></h2>
            <p class="modal-brand" id="modalBrand"></p>
            <p class="modal-price" id="modalPrice"></p>
            <p class="modal-rating" id="modalRating"></p>
            <p class="modal-category" id="modalCategory"></p>
            <div class="modal-description" id="modalDescription"></div>
            <div class="modal-store-options" id="modalStoreOptions"></div>
            <button class="modal-add-cart-btn" id="modalAddToCart">Add to cart</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    return {
      overlay,
      imgEl: overlay.querySelector("#modalImage"),
      titleEl: overlay.querySelector("#modalTitle"),
      brandEl: overlay.querySelector("#modalBrand"),
      priceEl: overlay.querySelector("#modalPrice"),
      ratingEl: overlay.querySelector("#modalRating"),
      categoryEl: overlay.querySelector("#modalCategory"),
      descriptionEl: overlay.querySelector("#modalDescription"),
      storeOptionsEl: overlay.querySelector("#modalStoreOptions"),
      addToCartBtn: overlay.querySelector("#modalAddToCart"),
      closeBtn: overlay.querySelector(".modal-close"),
    };
  }

  function createCartModal() {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay cart-modal-overlay";
    overlay.innerHTML = `
      <div class="modal-backdrop"></div>
      <div class="cart-modal">
        <button class="modal-close" aria-label="Close">×</button>
        <div class="cart-modal-body">
          <h2 class="cart-title">Your Cart</h2>
          <div class="cart-items" id="cartItems"></div>
          <div class="cart-summary">
            <div class="cart-summary-line">
              <span>Subtotal:</span>
              <span id="cartSubtotal">$0.00</span>
            </div>
            <div class="cart-summary-line">
              <span>GST (5%):</span>
              <span id="cartGST">$0.00</span>
            </div>
            <div class="cart-summary-line cart-summary-total">
              <span>Total:</span>
              <span id="cartTotal">$0.00</span>
            </div>
          </div>
          <div class="cart-footer">
            <button class="cart-clear-btn" id="cartClear">Clear cart</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    return {
      overlay,
      itemsEl: overlay.querySelector("#cartItems"),
      subtotalEl: overlay.querySelector("#cartSubtotal"),
      gstEl: overlay.querySelector("#cartGST"),
      totalEl: overlay.querySelector("#cartTotal"),
      clearBtn: overlay.querySelector("#cartClear"),
      closeBtn: overlay.querySelector(".modal-close"),
    };
  }
});