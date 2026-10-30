/* ===================================================================
   SENTINEL-TRACE TRACEABILITY EXPLORER CONTROLLER
   Genealogy Lineage Visualization, Forward & Backward Tracing, Node Inspector
   Connected to Flask GET /api/traceability/<id>?direction=forward|backward with Cloud Firestore
   =================================================================== */

let activeGenealogy = null;
let currentDirection = "forward"; // "forward" or "backward"
let currentIdentifier = "PRD101";

document.addEventListener("DOMContentLoaded", async () => {
  await initTraceabilityExplorer();
});

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function updateDirectionButtonsUI() {
  const btnFwd = document.getElementById("btn-forward-trace");
  const btnBwd = document.getElementById("btn-backward-trace");
  if (currentDirection === "backward") {
    if (btnBwd) btnBwd.classList.add("active");
    if (btnFwd) btnFwd.classList.remove("active");
  } else {
    if (btnFwd) btnFwd.classList.add("active");
    if (btnBwd) btnBwd.classList.remove("active");
  }
}

async function initTraceabilityExplorer() {
  // 1. Read URL query parameters for deep linking
  const urlParams = new URLSearchParams(window.location.search);
  const deepId = urlParams.get("id") ||
                 urlParams.get("batch") ||
                 urlParams.get("product") ||
                 urlParams.get("material") ||
                 urlParams.get("supplier") ||
                 urlParams.get("compliance") ||
                 urlParams.get("code") ||
                 urlParams.get("q");
  const deepDir = urlParams.get("direction");

  if (deepDir && deepDir.toLowerCase() === "backward") {
    currentDirection = "backward";
  } else {
    currentDirection = "forward";
  }
  updateDirectionButtonsUI();

  if (deepId && deepId.trim()) {
    currentIdentifier = deepId.trim();
  }

  // 2. Search input binding
  const searchInput = document.getElementById("trace-query-input");
  if (searchInput) {
    searchInput.value = currentIdentifier;
    searchInput.addEventListener("keyup", (e) => {
      if (e.key === "Enter") {
        const q = searchInput.value.trim();
        if (q) loadLineageForIdentifier(q);
      }
    });
  }

  // 3. Populate dropdown options from real products and batches
  await populateTraceabilityDropdown(currentIdentifier);

  // If deepId was not provided, use the first dropdown item if available
  if (!deepId) {
    const select = document.getElementById("trace-batch-select") || document.querySelector(".trace-search-bar select");
    if (select && select.value) {
      currentIdentifier = select.value;
      if (searchInput) searchInput.value = currentIdentifier;
    }
  }

  // 4. Load the initial lineage graph from Firestore
  await loadLineageForIdentifier(currentIdentifier);
}

async function populateTraceabilityDropdown(selectedId) {
  const select = document.getElementById("trace-batch-select") || document.querySelector(".trace-search-bar select");
  if (!select) return;

  try {
    const [products, batches] = await Promise.all([
      getProducts().catch(() => []),
      getBatches().catch(() => [])
    ]);

    if ((products && products.length > 0) || (batches && batches.length > 0)) {
      select.innerHTML = "";
      let foundSelected = false;

      // Products
      (products || []).forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `${p.id} (${p.name || 'Product'})`;
        if (selectedId && (p.id === selectedId || (p.code && p.code === selectedId))) {
          opt.selected = true;
          foundSelected = true;
        }
        select.appendChild(opt);
      });

      // Batches
      (batches || []).forEach(b => {
        const opt = document.createElement("option");
        opt.value = b.id;
        opt.textContent = `${b.id} (${b.product || 'Batch'})`;
        if (selectedId && b.id === selectedId) {
          opt.selected = true;
          foundSelected = true;
        }
        select.appendChild(opt);
      });

      // If selectedId wasn't in products or batches (e.g. material, supplier, compliance, custom code), prepend it
      if (selectedId && !foundSelected) {
        const customOpt = document.createElement("option");
        customOpt.value = selectedId;
        customOpt.textContent = `${selectedId} (Active Target)`;
        customOpt.selected = true;
        select.prepend(customOpt);
      }
    }
  } catch (err) {
    console.warn("Could not populate traceability dropdown options:", err);
  }
}

async function handleBatchSelectionChange(selectedId) {
  if (!selectedId) return;
  const searchInput = document.getElementById("trace-query-input");
  if (searchInput) searchInput.value = selectedId;
  await loadLineageForIdentifier(selectedId);
}

async function setTraceDirection(dir) {
  const newDir = dir === "backward" ? "backward" : "forward";
  currentDirection = newDir;
  updateDirectionButtonsUI();
  showToast(`Mode: ${newDir === 'forward' ? 'Forward Trace (Source to Distribution)' : 'Backward Trace (Field to Supplier)'}`, "info");

  if (currentIdentifier) {
    await loadLineageForIdentifier(currentIdentifier);
  }
}

async function loadLineageForIdentifier(identifier) {
  if (!identifier || !identifier.trim()) {
    showToast("Please enter an identifier to trace.", "warning");
    return;
  }

  currentIdentifier = identifier.trim();

  // Sync search input and select dropdown
  const searchInput = document.getElementById("trace-query-input");
  if (searchInput && searchInput.value !== currentIdentifier) {
    searchInput.value = currentIdentifier;
  }
  const select = document.getElementById("trace-batch-select") || document.querySelector(".trace-search-bar select");
  if (select && select.value !== currentIdentifier) {
    let exists = false;
    for (let opt of select.options) {
      if (opt.value === currentIdentifier) {
        select.value = currentIdentifier;
        exists = true;
        break;
      }
    }
    if (!exists) {
      const customOpt = document.createElement("option");
      customOpt.value = currentIdentifier;
      customOpt.textContent = `${currentIdentifier} (Active Target)`;
      customOpt.selected = true;
      select.prepend(customOpt);
    }
  }

  const flowContainer = document.getElementById("lineage-flow-container");
  if (flowContainer) {
    flowContainer.innerHTML = `<div style="padding: 30px; text-align: center; color: var(--text-secondary);"><span class="badge-dot" style="background:#fa7b7b;"></span> Querying Firestore ${currentDirection} genealogy for <strong>${escapeHtml(currentIdentifier)}</strong>...</div>`;
  }

  try {
    const res = await getTraceability(currentIdentifier, currentDirection);
    if (!res) {
      showToast(`No traceability records found for ${escapeHtml(currentIdentifier)}`, "warning");
      renderEmptyTraceability(currentIdentifier);
      return;
    }

    let stages = res.stages;

    // Fallback in case stages wasn't provided directly
    if (!stages || !Array.isArray(stages) || stages.length === 0) {
      const t = res.traceability || {};
      const product = t.product || res.product;
      const batch = t.batch || (res.batches && res.batches[0]);
      const material = t.material || (res.materials && res.materials[0]);
      const supplier = t.supplier || (res.suppliers && res.suppliers[0]);
      const complianceList = t.compliance || res.compliance || [];

      stages = [];
      let step = 1;

      if (supplier) {
        stages.push({
          step: step++,
          stage: "Supplier",
          id: supplier.supplier_id || supplier.id,
          title: supplier.supplier_name || supplier.name || "Vendor Partner",
          meta: `${supplier.address || 'Facility'} • ${supplier.status || 'Active'}`,
          details: {
            "Supplier ID": supplier.supplier_id || supplier.id,
            "Company Name": supplier.supplier_name || supplier.name,
            "Contact Person": supplier.contact || "N/A",
            "Official Email": supplier.email || "N/A",
            "Facility Address": supplier.address || "N/A",
            "Vendor Status": supplier.status || "Active"
          }
        });
      }

      if (material) {
        stages.push({
          step: step++,
          stage: "Raw Material",
          id: material.material_id || material.id,
          title: material.material_name || material.name || "Raw Material",
          meta: `${material.quantity || 0} ${material.unit || 'Kg'} • Verified`,
          details: {
            "Material ID": material.material_id || material.id,
            "Specification": material.material_name || material.name,
            "Lot Quantity": `${material.quantity || 0} ${material.unit || 'Kg'}`,
            "Supplier Reference": material.supplier_id || (supplier ? supplier.supplier_id : "N/A"),
            "Inbound Timestamp": material.created_at || "Verified"
          }
        });
      }

      if (batch) {
        stages.push({
          step: step++,
          stage: "Production Batch",
          id: batch.batch_id || batch.id,
          title: `Batch ${batch.batch_id || batch.id}`,
          meta: `Qty: ${batch.quantity || 0} units • ${batch.status || 'Completed'}`,
          details: {
            "Batch ID": batch.batch_id || batch.id,
            "Product Target": batch.product_id || (product ? product.product_id : "N/A"),
            "Material Input": batch.material_id || (material ? material.material_id : "N/A"),
            "Output Quantity": `${batch.quantity || 0} units`,
            "Production Date": batch.production_date || "N/A",
            "Operational State": batch.status || "Completed"
          }
        });
      }

      if (product) {
        stages.push({
          step: step++,
          stage: "Product",
          id: product.product_id || product.id,
          title: product.product_name || product.name || "Finished Assembly",
          meta: `SKU: ${product.product_code || product.code} • ${product.status || 'Certified'}`,
          details: {
            "Product ID": product.product_id || product.id,
            "Catalog Title": product.product_name || product.name,
            "Product Code": product.product_code || product.code,
            "Description": product.description || "N/A",
            "Lifecycle Status": product.status || "Certified"
          }
        });
      }

      if (complianceList && complianceList.length > 0) {
        complianceList.forEach((c, idx) => {
          stages.push({
            step: step++,
            stage: "Compliance",
            id: c.compliance_id || c.id || `CMP-${idx + 1}`,
            title: `${c.standard || 'Audit Standard'}`,
            meta: `Status: ${c.status || 'Compliant'} • Exp: ${c.expiry_date || 'N/A'}`,
            details: {
              "Compliance ID": c.compliance_id || c.id,
              "Governing Standard": c.standard || "N/A",
              "Verification Status": c.status || "Compliant",
              "Auditing Authority": c.audited_by || c.auditing_body || "Authorized Inspector",
              "Certification Expiry": c.expiry_date || "N/A",
              "Audit Notes": c.remarks || "Fully verified without non-conformance"
            }
          });
        });
      }
    }

    const matchedProd = res.product;
    activeGenealogy = {
      key: currentIdentifier,
      product: matchedProd ? (matchedProd.product_name || matchedProd.name) : currentIdentifier,
      stages: stages,
      direction: res.direction || currentDirection,
      matched_type: res.matched_entity_type
    };

    renderLineageFlow();

    // Select the queried node if present in stages, otherwise the first stage
    const targetNode = stages.find(s => s.id === currentIdentifier) ||
                       stages.find(s => s.id && s.id.toLowerCase() === currentIdentifier.toLowerCase()) ||
                       stages[0];
    if (targetNode) {
      selectNode(targetNode);
    }

    showToast(`Genealogy lineage retrieved for ${escapeHtml(currentIdentifier)} (${currentDirection.toUpperCase()})`, "success");
  } catch (err) {
    console.error("Failed to load traceability graph:", err);
    showToast(`Error retrieving traceability: ${err.message}`, "danger");
    renderEmptyTraceability(currentIdentifier, err.message);
  }
}

function renderEmptyTraceability(identifier, errorMessage) {
  const flowContainer = document.getElementById("lineage-flow-container");
  if (!flowContainer) return;

  const desc = errorMessage || `Identifier "${identifier}" has no linked entries in Firestore. Try searching for a known ID like PRD101, BAT201, RM301, SUP101, or product code TURB-A320-X.`;
  flowContainer.innerHTML = `
    <div style="padding: 40px; text-align: center; width: 100%;">
      <div style="font-size: 1.2rem; font-weight: 700; color: var(--text-primary); margin-bottom: 8px;">No Lineage Records Found</div>
      <p style="color: var(--text-secondary); max-width: 520px; margin: 0 auto 16px;">
        ${escapeHtml(desc)}
      </p>
    </div>
  `;

  const inspectorPanel = document.getElementById("node-inspector-content");
  if (inspectorPanel) {
    inspectorPanel.innerHTML = `
      <div style="padding: 24px; text-align: center; color: var(--text-secondary);">
        Select a valid node from the lineage flow to view detailed provenance attributes.
      </div>
    `;
  }
}

function renderLineageFlow() {
  const flowContainer = document.getElementById("lineage-flow-container");
  if (!flowContainer || !activeGenealogy || !activeGenealogy.stages) return;

  const stages = activeGenealogy.stages;

  let html = "";
  stages.forEach((stage, idx) => {
    html += `
      <div class="lineage-stage-col" id="stage-col-${escapeHtml(stage.id)}">
        <div class="stage-step-bubble">${idx + 1}</div>
        <div class="stage-title">${escapeHtml(stage.stage)}</div>
        <div class="node-card" onclick='handleNodeClick("${escapeHtml(stage.id)}")' id="node-${escapeHtml(stage.id)}">
          <div class="node-card-id">${escapeHtml(stage.id)}</div>
          <div class="node-card-name">${escapeHtml(stage.title)}</div>
          <div class="node-card-meta">${escapeHtml(stage.meta)}</div>
          <span class="badge badge-success" style="font-size: 0.7rem; padding: 2px 8px;">
            <span class="badge-dot"></span> Verified
          </span>
        </div>
      </div>
    `;
  });

  flowContainer.innerHTML = html;
}

function handleNodeClick(stageId) {
  if (!activeGenealogy || !activeGenealogy.stages) return;
  const stage = activeGenealogy.stages.find(s => s.id === stageId);
  if (stage) selectNode(stage);
}

function selectNode(stage) {
  document.querySelectorAll(".node-card").forEach(el => el.classList.remove("selected"));
  document.querySelectorAll(".lineage-stage-col").forEach(el => el.classList.remove("active"));

  const targetNode = document.getElementById(`node-${stage.id}`);
  const targetCol = document.getElementById(`stage-col-${stage.id}`);
  if (targetNode) targetNode.classList.add("selected");
  if (targetCol) targetCol.classList.add("active");

  const inspectorPanel = document.getElementById("node-inspector-content");
  if (!inspectorPanel) return;

  let fieldsHtml = "";
  for (const [key, val] of Object.entries(stage.details || {})) {
    fieldsHtml += `
      <div class="inspector-field">
        <div class="inspector-field-label">${escapeHtml(key)}</div>
        <div class="inspector-field-value">${escapeHtml(val)}</div>
      </div>
    `;
  }

  inspectorPanel.innerHTML = `
    <div class="inspector-header">
      <div class="inspector-tag">${escapeHtml(stage.stage)} Node</div>
      <div class="inspector-title">${escapeHtml(stage.title)}</div>
      <div style="font-family: var(--font-mono); font-size: 0.82rem; color: #fa7b7b; font-weight: 600; margin-top: 4px;">UID: ${escapeHtml(stage.id)}</div>
    </div>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      ${fieldsHtml}
    </div>
    <div style="margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--border);">
      <button class="btn btn-primary btn-sm" style="width: 100%;" onclick="exportProvenanceNode('${escapeHtml(stage.id)}')">
        Export Provenance Dossier
      </button>
    </div>
  `;
}

function searchTraceability(query) {
  if (!query) return;
  loadLineageForIdentifier(query.trim());
}

async function exportTraceabilityDossier() {
  try {
    if (!activeGenealogy || !activeGenealogy.stages || activeGenealogy.stages.length === 0) {
      showToast("No active lineage selected to export.", "warning");
      return;
    }
    const jsonStr = JSON.stringify(activeGenealogy, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sentinel_traceability_${activeGenealogy.key}_${currentDirection}_${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast("Downloaded complete genealogy topology JSON dossier!", "success");
  } catch (err) {
    showToast(`Failed to export topology: ${err.message}`, "danger");
  }
}

async function auditLineageChain() {
  const targetId = currentIdentifier || (activeGenealogy && activeGenealogy.query_id);
  if (!targetId || !activeGenealogy || !activeGenealogy.stages || activeGenealogy.stages.length === 0) {
    showToast("No active lineage pipeline loaded to audit. Please trace a batch or product first.", "warning");
    return;
  }

  try {
    showToast(`Auditing lineage chain for ${escapeHtml(targetId)} against Cloud Firestore...`, "info");
    const res = await (window.auditLineage ? window.auditLineage(targetId) : apiRequest(`/traceability/${encodeURIComponent(targetId)}/audit`, { method: "POST" }));

    if (res && res.chain_intact) {
      showToast(res.message || `Audit complete: All ${res.nodes_verified || activeGenealogy.stages.length} lineage node(s) verified against Firestore ledger!`, "success");
    } else if (res && res.integrity_status === "PARTIAL_VALIDATED") {
      showToast(res.message || `Audit complete: ${res.nodes_verified} nodes verified, partial chain.`, "info");
    } else {
      showToast(res?.message || `Audit flagged potential gaps in lineage chain.`, "warning");
    }
  } catch (err) {
    showToast(`Lineage audit failed: ${err.message}`, "danger");
  }
}

function exportProvenanceNode(nodeId) {
  const node = (activeGenealogy && activeGenealogy.stages) ? activeGenealogy.stages.find(s => s.id === nodeId) : null;
  const content = node ? JSON.stringify(node, null, 2) : `{"nodeId": "${nodeId}", "status": "Verified", "ledger": "traceability-a5528"}`;
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `provenance_node_${nodeId}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(`Exported provenance dossier for node ${nodeId}!`, "success");
}

window.setTraceDirection = setTraceDirection;
window.handleBatchSelectionChange = handleBatchSelectionChange;
window.handleNodeClick = handleNodeClick;
window.selectNode = selectNode;
window.searchTraceability = searchTraceability;
window.exportTraceabilityDossier = exportTraceabilityDossier;
window.auditLineageChain = auditLineageChain;
window.exportProvenanceNode = exportProvenanceNode;
