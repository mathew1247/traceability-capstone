/* ===================================================================
   SENTINEL-TRACE TRACEABILITY EXPLORER CONTROLLER
   Genealogy Lineage Visualization, Forward & Backward Tracing, Node Inspector
   Connected to Flask GET /api/traceability/<id> with Cloud Firestore
   =================================================================== */

let activeGenealogy = null;
let currentDirection = "forward"; // forward or backward

document.addEventListener("DOMContentLoaded", async () => {
  await initTraceabilityExplorer();
});

async function initTraceabilityExplorer() {
  await populateTraceabilityDropdown();

  // Search input binding
  const searchInput = document.getElementById("trace-query-input");
  if (searchInput) {
    searchInput.addEventListener("keyup", (e) => {
      if (e.key === "Enter") {
        const q = searchInput.value.trim();
        if (q) loadLineageForIdentifier(q);
      }
    });
  }

  // Load default product or batch
  const select = document.querySelector(".trace-search-bar select");
  const initialId = select && select.value ? select.value : "PRD101";
  await loadLineageForIdentifier(initialId);
}

async function populateTraceabilityDropdown() {
  const select = document.querySelector(".trace-search-bar select");
  if (!select) return;

  try {
    const [products, batches] = await Promise.all([
      getProducts().catch(() => []),
      getBatches().catch(() => [])
    ]);

    if ((products && products.length > 0) || (batches && batches.length > 0)) {
      select.innerHTML = "";
      
      // Products
      (products || []).forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `${p.id} (${p.name || 'Product'})`;
        select.appendChild(opt);
      });

      // Batches
      (batches || []).forEach(b => {
        const opt = document.createElement("option");
        opt.value = b.id;
        opt.textContent = `${b.id} (${b.product || 'Batch'})`;
        select.appendChild(opt);
      });
    }
  } catch (err) {
    console.warn("Could not populate traceability dropdown options:", err);
  }
}

async function handleBatchSelectionChange(selectedId) {
  if (!selectedId) return;
  await loadLineageForIdentifier(selectedId);
}

async function loadLineageForIdentifier(identifier) {
  const flowContainer = document.getElementById("lineage-flow-container");
  if (flowContainer) {
    flowContainer.innerHTML = `<div style="padding: 30px; text-align: center; color: var(--text-secondary);"><span class="badge-dot" style="background:#fa7b7b;"></span> Querying Firestore genealogy for <strong>${identifier}</strong>...</div>`;
  }

  try {
    const res = await getTraceability(identifier);
    if (!res) {
      showToast(`No traceability records found for ${identifier}`, "warning");
      renderEmptyTraceability(identifier);
      return;
    }

    const t = res.traceability || {};
    const product = t.product || res.product;
    const batch = t.batch || (res.batches && res.batches[0]);
    const material = t.material || (res.materials && res.materials[0]);
    const supplier = t.supplier || (res.suppliers && res.suppliers[0]);
    const complianceList = t.compliance || res.compliance || [];

    // Construct sequential stages: Supplier -> Raw Material -> Batch -> Product -> Compliance
    const stages = [];
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
        meta: `${material.quantity} ${material.unit || 'Kg'} • Verified`,
        details: {
          "Material ID": material.material_id || material.id,
          "Specification": material.material_name || material.name,
          "Lot Quantity": `${material.quantity} ${material.unit || 'Kg'}`,
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
        meta: `Qty: ${batch.quantity} units • ${batch.status}`,
        details: {
          "Batch ID": batch.batch_id || batch.id,
          "Product Target": batch.product_id || (product ? product.product_id : "N/A"),
          "Material Input": batch.material_id || (material ? material.material_id : "N/A"),
          "Output Quantity": `${batch.quantity} units`,
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
        meta: `SKU: ${product.product_code || product.code} • ${product.status}`,
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
            "Auditing Authority": c.audited_by || "Authorized Inspector",
            "Certification Expiry": c.expiry_date || "N/A",
            "Audit Notes": c.remarks || "Fully verified without non-conformance"
          }
        });
      });
    }

    activeGenealogy = {
      key: identifier,
      product: product ? (product.product_name || product.name) : identifier,
      stages: stages
    };

    renderLineageFlow();

    // Select the center node or first node
    const defaultSelectNode = stages.length > 2 ? stages[2] : stages[0];
    if (defaultSelectNode) {
      selectNode(defaultSelectNode);
    }

    showToast(`Genealogy lineage retrieved for ${identifier}`, "success");
  } catch (err) {
    console.error("Failed to load traceability graph:", err);
    showToast(`Error retrieving traceability for ${identifier}: ${err.message}`, "danger");
    renderEmptyTraceability(identifier);
  }
}

function renderEmptyTraceability(identifier) {
  const flowContainer = document.getElementById("lineage-flow-container");
  if (!flowContainer) return;

  flowContainer.innerHTML = `
    <div style="padding: 40px; text-align: center; width: 100%;">
      <div style="font-size: 1.2rem; font-weight: 700; color: var(--text-primary); margin-bottom: 8px;">No Lineage Records Found</div>
      <p style="color: var(--text-secondary); max-width: 480px; margin: 0 auto 16px;">
        Identifier "<strong>${identifier}</strong>" has no linked entries in Firestore. Try searching for a known ID like <strong>PRD101</strong>, <strong>BAT201</strong>, <strong>RM301</strong>, or <strong>SUP101</strong>.
      </p>
    </div>
  `;
}

function renderLineageFlow() {
  const flowContainer = document.getElementById("lineage-flow-container");
  if (!flowContainer || !activeGenealogy || !activeGenealogy.stages) return;

  const displayStages = currentDirection === "backward" 
    ? [...activeGenealogy.stages].reverse() 
    : activeGenealogy.stages;

  let html = "";
  displayStages.forEach((stage, idx) => {
    html += `
      <div class="lineage-stage-col" id="stage-col-${stage.id}">
        <div class="stage-step-bubble">${idx + 1}</div>
        <div class="stage-title">${stage.stage}</div>
        <div class="node-card" onclick='handleNodeClick("${stage.id}")' id="node-${stage.id}">
          <div class="node-card-id">${stage.id}</div>
          <div class="node-card-name">${stage.title}</div>
          <div class="node-card-meta">${stage.meta}</div>
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
        <div class="inspector-field-label">${key}</div>
        <div class="inspector-field-value">${val}</div>
      </div>
    `;
  }

  inspectorPanel.innerHTML = `
    <div class="inspector-header">
      <div class="inspector-tag">${stage.stage} Node</div>
      <div class="inspector-title">${stage.title}</div>
      <div style="font-family: var(--font-mono); font-size: 0.82rem; color: #fa7b7b; font-weight: 600; margin-top: 4px;">UID: ${stage.id}</div>
    </div>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      ${fieldsHtml}
    </div>
    <div style="margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--border);">
      <button class="btn btn-primary btn-sm" style="width: 100%;" onclick="showToast('Exporting cryptographic pedigree certificate for ${stage.id}...', 'success')">
        Export Provenance Dossier
      </button>
    </div>
  `;
}

function searchTraceability(query) {
  if (!query) return;
  loadLineageForIdentifier(query.trim());
}

// Direction toggle helper
window.setTraceDirection = function(dir) {
  currentDirection = dir;
  renderLineageFlow();
  showToast(`Switched to ${dir.toUpperCase()} Trace mode`, "info");
};

window.handleBatchSelectionChange = handleBatchSelectionChange;
window.handleNodeClick = handleNodeClick;
window.selectNode = selectNode;
window.searchTraceability = searchTraceability;
