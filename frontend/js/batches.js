/* ===================================================================
   SENTINEL-TRACE PRODUCTION BATCHES CONTROLLER
   Connected to Flask GET /api/batches with live Cloud Firestore
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await populateBatchDropdowns();
  await loadBatchesTable();
  initBatchForm();
  initEditBatchForm();

  const params = new URLSearchParams(window.location.search);
  if (params.get("action") === "new") {
    openModal("add-batch-modal");
  }
});

async function populateBatchDropdowns() {
  const prodSelect = document.getElementById("batch-product");
  const matSelect = document.getElementById("batch-material");
  const editProdSelect = document.getElementById("edit-batch-product");
  const editMatSelect = document.getElementById("edit-batch-material");

  try {
    const [products, materials] = await Promise.all([
      getProducts().catch(() => []),
      getMaterials().catch(() => [])
    ]);

    const fillSelect = (selectEl, items) => {
      if (!selectEl || !items || items.length === 0) return;
      selectEl.innerHTML = "";
      items.forEach(item => {
        const opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = `${item.name} (${item.id})`;
        selectEl.appendChild(opt);
      });
    };

    fillSelect(prodSelect, products);
    fillSelect(editProdSelect, products);
    fillSelect(matSelect, materials);
    fillSelect(editMatSelect, materials);
  } catch (err) {
    console.warn("Could not populate batch dropdowns:", err);
  }
}

async function loadBatchesTable() {
  const tbody = document.getElementById("batches-table-body");
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 24px; color: var(--text-secondary);">Loading production batches from Firestore...</td></tr>`;

  try {
    const batches = await getBatches();

    if (!batches || batches.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 30px; color: var(--text-secondary);">No production batches found.</td></tr>`;
      return;
    }

    let html = "";
    batches.forEach(b => {
      let statusClass = "badge-neutral";
      if (b.status === "Completed" || b.status === "Passed") statusClass = "badge-success";
      else if (b.status === "In QA Inspection" || b.status === "Running") statusClass = "badge-warning";
      else if (b.status === "Pending") statusClass = "badge-info";

      html += `
        <tr>
          <td class="td-code">${b.id}</td>
          <td>
            <div class="td-primary-text">${b.product}</div>
            <div class="td-secondary-text">Operator: ${b.operator || 'Jack Mathew'}</div>
          </td>
          <td>${b.material}</td>
          <td><strong>${b.quantity}</strong> units</td>
          <td>${b.date}</td>
          <td>
            <span class="badge ${statusClass}"><span class="badge-dot"></span>${b.status}</span>
          </td>
          <td class="table-actions-cell">
            <button class="btn-table-action" title="View Genealogy" onclick="viewBatchGenealogy('${b.id}')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="18" r="3"></circle>
                <circle cx="6" cy="6" r="3"></circle>
                <circle cx="18" cy="6" r="3"></circle>
                <path d="M18 9v1a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V9"></path>
                <path d="M12 12v3"></path>
              </svg>
            </button>
            <button class="btn-table-action" title="Edit Batch" onclick="handleEditBatch('${b.id}')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
              </svg>
            </button>
            <button class="btn-table-action danger" title="Delete Batch" onclick="handleDeleteBatch('${b.id}')">
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
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 24px; color: #ef4444;">Failed to load batches: ${err.message}</td></tr>`;
  }
}

function initBatchForm() {
  const form = document.getElementById("add-batch-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const product = document.getElementById("batch-product").value;
    const material = document.getElementById("batch-material").value;
    const quantity = parseInt(document.getElementById("batch-qty").value, 10);
    const status = document.getElementById("batch-status").value;

    try {
      await createBatch({
        product,
        material,
        quantity,
        status,
        operator: "Jack Mathew",
        qaLead: "Pending Inspection"
      });

      closeModal("add-batch-modal");
      form.reset();
      showToast(`Production Batch initiated for ${product}!`, "success");
      await loadBatchesTable();
    } catch (err) {
      showToast(`Failed to create batch: ${err.message}`, "danger");
    }
  });
}

async function handleEditBatch(id) {
  try {
    const batches = await getBatches();
    const batch = batches.find(b => b.id === id);
    if (!batch) {
      showToast("Batch not found.", "danger");
      return;
    }
    document.getElementById("edit-batch-id").value = batch.id;
    if (batch.product_id) {
      document.getElementById("edit-batch-product").value = batch.product_id;
    }
    if (batch.material_id) {
      document.getElementById("edit-batch-material").value = batch.material_id;
    }
    document.getElementById("edit-batch-qty").value = batch.quantity || 1;
    document.getElementById("edit-batch-status").value = batch.status || "Running";
    openModal("edit-batch-modal");
  } catch (err) {
    showToast(`Failed to load batch details: ${err.message}`, "danger");
  }
}

function initEditBatchForm() {
  const form = document.getElementById("edit-batch-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("edit-batch-id").value;
    const product = document.getElementById("edit-batch-product").value;
    const material = document.getElementById("edit-batch-material").value;
    const quantity = parseInt(document.getElementById("edit-batch-qty").value, 10);
    const status = document.getElementById("edit-batch-status").value;

    if (!quantity || quantity <= 0) {
      showToast("Quantity must be a positive integer.", "danger");
      return;
    }

    try {
      await updateBatch(id, { product, material, quantity, status });
      closeModal("edit-batch-modal");
      showToast(`Batch ${id} updated successfully!`, "success");
      await loadBatchesTable();
    } catch (err) {
      showToast(`Failed to update batch: ${err.message}`, "danger");
    }
  });
}

function filterBatches() {
  const query = document.getElementById("batch-search").value.toLowerCase();
  const statusFilter = document.getElementById("batch-status-filter").value;
  const rows = document.querySelectorAll("#batches-table-body tr");

  rows.forEach(r => {
    const text = r.textContent.toLowerCase();
    const matchesSearch = text.includes(query);
    const matchesStatus = !statusFilter || text.includes(statusFilter.toLowerCase());
    r.style.display = matchesSearch && matchesStatus ? "" : "none";
  });
}

function viewBatchGenealogy(id) {
  showToast(`Tracing batch genealogy for ${id}...`, "info");
  window.location.href = `traceability.html?id=${encodeURIComponent(id)}`;
}

async function handleDeleteBatch(id) {
  if (confirm(`Remove production batch ${id} from system?`)) {
    try {
      await deleteBatch(id);
      showToast(`Batch ${id} removed successfully.`, "info");
      await loadBatchesTable();
    } catch (err) {
      showToast(`Failed to delete batch: ${err.message}`, "danger");
    }
  }
}
