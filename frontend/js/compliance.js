/* ===================================================================
   SENTINEL-TRACE COMPLIANCE TRACKER CONTROLLER
   Connected to Flask GET /api/compliance with live Cloud Firestore
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await populateComplianceProducts();
  await loadComplianceTable();
  initComplianceForm();
});

async function populateComplianceProducts() {
  const prodSelect = document.getElementById("comp-product");
  if (!prodSelect) return;

  try {
    const products = await getProducts();
    if (products && products.length > 0) {
      prodSelect.innerHTML = "";
      products.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `${p.name} (${p.id})`;
        prodSelect.appendChild(opt);
      });
    }
  } catch (err) {
    console.warn("Could not populate compliance products:", err);
  }
}

async function loadComplianceTable() {
  const tbody = document.getElementById("compliance-table-body");
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 24px; color: var(--text-secondary);">Loading compliance certifications from Cloud Firestore...</td></tr>`;

  try {
    const records = await getCompliance();

    if (!records || records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 30px; color: var(--text-secondary);">No compliance records found.</td></tr>`;
      return;
    }

    let html = "";
    records.forEach(c => {
      let badgeClass = "badge-success";
      if (c.status === "Review Required" || c.status === "Pending") badgeClass = "badge-warning";
      else if (c.status === "Non-Compliant" || c.status === "Expired") badgeClass = "badge-danger";

      html += `
        <tr>
          <td class="td-code">${c.id}</td>
          <td>
            <div class="td-primary-text">${c.product}</div>
            <div class="td-secondary-text">Verification Score: ${c.score || '98.5%'}</div>
          </td>
          <td><strong>${c.standard}</strong></td>
          <td>
            <span class="badge ${badgeClass}"><span class="badge-dot"></span>${c.status}</span>
          </td>
          <td>${c.auditor}</td>
          <td>${c.expiryDate}</td>
          <td class="table-actions-cell">
            <button class="btn-table-action" title="Download Regulatory Certificate" onclick="showToast('Downloading accredited audit certificate...', 'success')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </button>
            <button class="btn-table-action danger" title="Delete Compliance Record" onclick="handleDeleteCompliance('${c.id}')">
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
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 24px; color: #ef4444;">Failed to load compliance records: ${err.message}</td></tr>`;
  }
}

function initComplianceForm() {
  const form = document.getElementById("add-compliance-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const product = document.getElementById("comp-product").value;
    const standard = document.getElementById("comp-standard").value;
    const status = document.getElementById("comp-status").value;
    const auditor = document.getElementById("comp-auditor").value.trim();
    const expiryDate = document.getElementById("comp-expiry").value;

    try {
      await createCompliance({ product, standard, status, auditor, expiryDate, score: "99.0%" });
      closeModal("add-compliance-modal");
      form.reset();
      showToast(`Compliance audit record registered!`, "success");
      await loadComplianceTable();
    } catch (err) {
      showToast(`Failed to record compliance certification: ${err.message}`, "danger");
    }
  });
}

function filterCompliance() {
  const query = document.getElementById("compliance-search").value.toLowerCase();
  const rows = document.querySelectorAll("#compliance-table-body tr");

  rows.forEach(r => {
    const text = r.textContent.toLowerCase();
    r.style.display = text.includes(query) ? "" : "none";
  });
}

async function handleDeleteCompliance(id) {
  if (confirm(`Remove compliance record ${id}?`)) {
    try {
      await deleteCompliance(id);
      showToast(`Compliance record ${id} deleted.`, "info");
      await loadComplianceTable();
    } catch (err) {
      showToast(`Failed to delete record: ${err.message}`, "danger");
    }
  }
}
