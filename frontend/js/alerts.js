/* ===================================================================
   SENTINEL-TRACE ALERTS & NOTIFICATIONS CONTROLLER
   Filters, Severity Categorization, Triage Actions (Acknowledge, Resolve, Dismiss)
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await loadAlerts();
});

let currentFilter = "All";

async function loadAlerts() {
  const alerts = await getAlerts();
  const container = document.getElementById("alerts-list-container");
  if (!container) return;

  const filtered = currentFilter === "All" ? alerts : alerts.filter(a => a.severity.toLowerCase() === currentFilter.toLowerCase());

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">&#10003;</div>
        <div class="empty-state-title">No Active Alerts</div>
        <p class="empty-state-desc">All industrial systems are running within calibrated tolerances.</p>
      </div>
    `;
    return;
  }

  let html = "";
  filtered.forEach(a => {
    const isCritical = a.severity === "Critical";
    const isWarning = a.severity === "Warning";
    const badgeClass = isCritical ? "badge-danger" : isWarning ? "badge-warning" : "badge-info";
    const borderAccent = isCritical ? "border-left: 5px solid #ef4444;" : isWarning ? "border-left: 5px solid #f59e0b;" : "border-left: 5px solid #06b6d4;";

    html += `
      <div class="card" style="margin-bottom: 16px; padding: 22px 26px; ${borderAccent}">
        <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
          <div style="flex-grow: 1;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
              <span class="badge ${badgeClass}"><span class="badge-dot"></span>${a.severity}</span>
              <span style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-secondary);">${a.id}</span>
              <span style="font-size: 0.8rem; color: var(--text-muted);">&bull; ${a.timestamp}</span>
              <span class="badge badge-neutral" style="font-size: 0.75rem;">Status: ${a.status}</span>
            </div>
            <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;">${a.title}</h3>
            <p style="font-size: 0.9rem; color: var(--text-secondary); margin: 0; max-width: 720px;">${a.details}</p>
          </div>

          <div style="display: flex; align-items: center; gap: 8px;">
            ${a.status !== "Acknowledged" && a.status !== "Resolved" ? `
              <button class="btn btn-secondary btn-sm" onclick="handleAlertAction('${a.id}', 'Acknowledged')">Acknowledge</button>
            ` : ''}
            ${a.status !== "Resolved" ? `
              <button class="btn btn-primary btn-sm" onclick="handleAlertAction('${a.id}', 'Resolved')">Resolve</button>
            ` : ''}
            <button class="btn btn-ghost btn-sm" onclick="handleAlertAction('${a.id}', 'Dismiss')">Dismiss</button>
          </div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

function setAlertFilter(filter) {
  currentFilter = filter;
  document.querySelectorAll(".alert-filter-pill").forEach(btn => {
    btn.classList.toggle("active", btn.textContent.trim().toLowerCase() === filter.toLowerCase());
  });
  loadAlerts();
}

async function handleAlertAction(id, action) {
  try {
    const user = (typeof getCurrentUser === 'function') ? getCurrentUser() : {};
    const res = await updateAlert(id, action);
    const recipient = res?.email_notification?.recipient || user?.email || "jack@sentineltrace.io";

    if (action === "Acknowledged" || action === "Acknowledge") {
      showToast(`Alert ${id} Acknowledged — Email notification sent to ${recipient}`, "success");
    } else if (action === "Resolved" || action === "Resolve") {
      showToast(`Alert ${id} Resolved — Resolution recorded & notification sent to ${recipient}`, "success");
    } else {
      showToast(`Alert ${id} Dismissed`, "info");
    }
    await loadAlerts();
  } catch (err) {
    showToast(`Failed to update alert: ${err.message}`, "danger");
  }
}
