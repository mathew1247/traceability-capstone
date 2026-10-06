/* ===================================================================
   SENTINEL-TRACE ACTIVITY LOGS AUDIT CONTROLLER
   Search, Action Filter, Role Filter, Table Rendering
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await loadActivityLogs();
});

async function loadActivityLogs() {
  const logs = await getActivityLogs();
  const tbody = document.getElementById("logs-table-body");
  if (!tbody) return;

  let html = "";
  logs.forEach(l => {
    let actionBadge = "badge-neutral";
    if (l.action === "AUTH_LOGIN") actionBadge = "badge-info";
    else if (l.action === "CREATE") actionBadge = "badge-success";
    else if (l.action === "SCAN_TRIGGER") actionBadge = "badge-warning";
    else if (l.action === "DELETE") actionBadge = "badge-danger";

    html += `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-secondary);">${l.timestamp}</td>
        <td>
          <div class="td-primary-text">${l.user}</div>
          <div class="td-secondary-text">${l.role}</div>
        </td>
        <td><span class="badge ${actionBadge}">${l.action}</span></td>
        <td><strong>${l.resource}</strong></td>
        <td class="td-code">${l.ip}</td>
        <td><span class="badge badge-success"><span class="badge-dot"></span>${l.status}</span></td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

function filterLogs() {
  const query = document.getElementById("logs-search").value.toLowerCase();
  const actionFilter = document.getElementById("logs-action-filter").value;
  const rows = document.querySelectorAll("#logs-table-body tr");

  rows.forEach(r => {
    const text = r.textContent.toLowerCase();
    const matchSearch = text.includes(query);
    const matchAction = !actionFilter || text.includes(actionFilter.toLowerCase());
    r.style.display = matchSearch && matchAction ? "" : "none";
  });
}

async function exportAuditTrail() {
  try {
    showToast("Compiling immutable audit logs from Cloud Firestore...", "info");
    const logs = await getActivityLogs();

    if (!logs || logs.length === 0) {
      showToast("No activity logs available to export.", "warning");
      return;
    }

    let csv = "Timestamp,User,Role,Action,Resource,IP Address,Status\n";
    logs.forEach(l => {
      csv += `"${l.timestamp}","${l.user}","${l.role}","${l.action}","${l.resource || ''}","${l.ip}","${l.status}"\n`;
    });

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sentinel_trace_audit_trail_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast(`Exported ${logs.length} immutable audit ledger records to CSV!`, "success");
  } catch (err) {
    showToast(`Audit export failed: ${err.message}`, "danger");
  }
}

window.exportAuditTrail = exportAuditTrail;
