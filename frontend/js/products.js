/* ===================================================================
   SENTINEL-TRACE PRODUCT CATALOG CONTROLLER
   Connected to Flask GET /api/products with live Cloud Firestore
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await loadProductsTable();
  initProductForm();
  initEditProductForm();
});

async function loadProductsTable() {
  const tbody = document.getElementById("products-table-body");
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 24px; color: var(--text-secondary);">Loading products from Cloud Firestore...</td></tr>`;

  try {
    const products = await getProducts();

    if (!products || products.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 30px; color: var(--text-secondary);">No products registered in catalog.</td></tr>`;
      return;
    }

    let html = "";
    products.forEach(p => {
      const statusBadge = p.status === "Certified" ? "badge-success" : p.status === "In Production" ? "badge-info" : "badge-danger";
      html += `
        <tr>
          <td class="td-code">${p.id}</td>
          <td>
            <div class="td-primary-text">${p.name}</div>
            <div class="td-secondary-text">Standard: ${p.compliance || 'ISO 9001:2015'}</div>
          </td>
          <td class="td-code">${p.code}</td>
          <td>
            <span class="badge ${statusBadge}"><span class="badge-dot"></span>${p.status}</span>
          </td>
          <td>${p.createdDate || '2026-10-06'}</td>
          <td class="table-actions-cell">
            <button class="btn-table-action" title="View Traceability" onclick="viewProductTrace('${p.id}')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
            </button>
            <button class="btn-table-action" title="Edit Product" onclick="handleEditProduct('${p.id}')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
              </svg>
            </button>
            <button class="btn-table-action danger" title="Delete Product" onclick="handleDeleteProduct('${p.id}')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = html;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 24px; color: #ef4444;">Failed to load products: ${err.message}</td></tr>`;
  }
}

function initProductForm() {
  const form = document.getElementById("add-product-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("prod-name").value.trim();
    const code = document.getElementById("prod-code").value.trim();
    const status = document.getElementById("prod-status").value;
    const compliance = document.getElementById("prod-compliance").value;

    if (!name || !code) {
      showToast("Please provide product name and code.", "danger");
      return;
    }

    try {
      await createProduct({ name, code, status, compliance });
      closeModal("add-product-modal");
      form.reset();
      showToast(`Product "${name}" successfully registered!`, "success");
      await loadProductsTable();
    } catch (err) {
      showToast(`Failed to register product: ${err.message}`, "danger");
    }
  });
}

async function handleEditProduct(id) {
  try {
    const products = await getProducts();
    const prod = products.find(p => p.id === id);
    if (!prod) {
      showToast("Product not found.", "danger");
      return;
    }
    document.getElementById("edit-prod-id").value = prod.id;
    document.getElementById("edit-prod-name").value = prod.name || prod.product_name || "";
    document.getElementById("edit-prod-code").value = prod.code || prod.product_code || "";
    document.getElementById("edit-prod-status").value = prod.status || "In Production";
    document.getElementById("edit-prod-compliance").value = prod.compliance || prod.description || "";
    openModal("edit-product-modal");
  } catch (err) {
    showToast(`Failed to load product details: ${err.message}`, "danger");
  }
}

function initEditProductForm() {
  const form = document.getElementById("edit-product-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("edit-prod-id").value;
    const name = document.getElementById("edit-prod-name").value.trim();
    const code = document.getElementById("edit-prod-code").value.trim();
    const status = document.getElementById("edit-prod-status").value;
    const compliance = document.getElementById("edit-prod-compliance").value.trim();

    if (!name || !code) {
      showToast("Please provide product name and code.", "danger");
      return;
    }

    try {
      await updateProduct(id, { name, code, status, compliance });
      closeModal("edit-product-modal");
      showToast(`Product ${id} updated successfully!`, "success");
      await loadProductsTable();
    } catch (err) {
      showToast(`Failed to update product: ${err.message}`, "danger");
    }
  });
}

function filterProducts() {
  const query = document.getElementById("product-search").value.toLowerCase();
  const statusFilter = document.getElementById("product-status-filter").value;
  const rows = document.querySelectorAll("#products-table-body tr");

  rows.forEach(r => {
    const text = r.textContent.toLowerCase();
    const matchesSearch = text.includes(query);
    const matchesStatus = !statusFilter || text.includes(statusFilter.toLowerCase());
    r.style.display = matchesSearch && matchesStatus ? "" : "none";
  });
}

function viewProductTrace(id) {
  showToast(`Loading lineage trace for product ${id}...`, "info");
  window.location.href = `traceability.html?id=${encodeURIComponent(id)}`;
}

async function handleDeleteProduct(id) {
  if (confirm(`Are you sure you want to remove product ${id} from catalog?`)) {
    try {
      await deleteProduct(id);
      showToast(`Product ${id} deleted successfully.`, "info");
      await loadProductsTable();
    } catch (err) {
      showToast(`Failed to delete product: ${err.message}`, "danger");
    }
  }
}
