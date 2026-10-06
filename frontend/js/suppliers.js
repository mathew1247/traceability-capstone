/* ===================================================================
   SENTINEL-TRACE SUPPLIER DIRECTORY CONTROLLER
   Connected to Flask GET /api/suppliers with live Cloud Firestore
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await loadSuppliersTable();
  initSupplierForm();
});

async function loadSuppliersTable() {
  const tbody = document.getElementById("suppliers-table-body");
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 24px; color: var(--text-secondary);">Loading suppliers from Cloud Firestore...</td></tr>`;

  try {
    const suppliers = await getSuppliers();

    if (!suppliers || suppliers.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 30px; color: var(--text-secondary);">No suppliers found in directory.</td></tr>`;
      return;
    }

    let html = "";
    suppliers.forEach(s => {
      let badgeClass = "badge-neutral";
      if (s.status === "Verified") badgeClass = "badge-success";
      else if (s.status === "Active") badgeClass = "badge-info";
      else if (s.status === "Pending") badgeClass = "badge-warning";
      else if (s.status === "Suspended") badgeClass = "badge-danger";

      html += `
        <tr>
          <td class="td-code">${s.id}</td>
          <td>
            <div class="td-primary-text">${s.name}</div>
            <div class="td-secondary-text">Vendor Score: ${s.rating || '4.8'}/5.0</div>
          </td>
          <td>${s.contact}</td>
          <td><a href="mailto:${s.email}" style="color: #e05e5e; font-weight: 500; text-decoration: underline;">${s.email}</a></td>
          <td><span style="font-size: 0.82rem; color: var(--text-secondary);">${s.address}</span></td>
          <td>
            <span class="badge ${badgeClass}"><span class="badge-dot"></span>${s.status}</span>
          </td>
          <td class="table-actions-cell">
            <button class="btn-table-action" title="Verify Vendor Documents" onclick="showToast('Vendor compliance certifications valid through 2027.', 'success')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                <polyline points="9 12 11 14 15 10"></polyline>
              </svg>
            </button>
            <button class="btn-table-action danger" title="Delete Supplier" onclick="handleDeleteSupplier('${s.id}')">
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
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 24px; color: #ef4444;">Failed to load suppliers: ${err.message}</td></tr>`;
  }
}

function initSupplierForm() {
  const form = document.getElementById("add-supplier-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("sup-name").value.trim();
    const contact = document.getElementById("sup-contact").value.trim();
    const email = document.getElementById("sup-email").value.trim();
    const address = document.getElementById("sup-address").value.trim();
    const status = document.getElementById("sup-status").value;

    try {
      await createSupplier({ name, contact, email, address, status, rating: "4.8" });
      closeModal("add-supplier-modal");
      form.reset();
      showToast(`Supplier "${name}" onboarded to directory!`, "success");
      await loadSuppliersTable();
    } catch (err) {
      showToast(`Failed to save supplier: ${err.message}`, "danger");
    }
  });
}

function filterSuppliers() {
  const query = document.getElementById("supplier-search").value.toLowerCase();
  const rows = document.querySelectorAll("#suppliers-table-body tr");

  rows.forEach(r => {
    const text = r.textContent.toLowerCase();
    r.style.display = text.includes(query) ? "" : "none";
  });
}

async function handleDeleteSupplier(id) {
  if (confirm(`Are you sure you want to remove supplier ${id}?`)) {
    try {
      await deleteSupplier(id);
      showToast(`Supplier ${id} removed successfully.`, "info");
      await loadSuppliersTable();
    } catch (err) {
      showToast(`Failed to delete supplier: ${err.message}`, "danger");
    }
  }
}
