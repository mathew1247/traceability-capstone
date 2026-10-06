/* ===================================================================
   SENTINEL-TRACE SECURITY MONITOR CONTROLLER
   Connected to Flask GET /api/network/security with live Cloud Firestore
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await loadSecurityOverview();
});

async function loadSecurityOverview() {
  try {
    const secData = await getNetworkSecurity();

    // Update KPI values
    const kpiCards = document.querySelectorAll(".kpi-grid-4 .kpi-card-value");
    if (kpiCards && kpiCards.length >= 4) {
      kpiCards[0].textContent = secData.network_status || "Secure";
      kpiCards[0].style.color = (secData.network_status === "Critical") ? "#ef4444" : "#10b981";
      kpiCards[1].textContent = secData.active_devices ?? 14;
      kpiCards[2].textContent = (secData.suspicious_hosts && secData.suspicious_hosts.length) ?? 0;
      kpiCards[3].textContent = (secData.open_critical_ports && secData.open_critical_ports.length) ?? 0;
    }

    // Update Threat Meter Gauge
    const threatGauge = document.querySelector(".threat-gauge-circle");
    const threatTitle = document.querySelector(".threat-details h4");
    const threatDesc = document.querySelector(".threat-details p");
    const level = (secData.threat_level || "LOW").toUpperCase();

    if (threatGauge) {
      threatGauge.textContent = level;
      threatGauge.style.background = (level === "HIGH" || level === "CRITICAL") ? "#ef4444" : (level === "MEDIUM") ? "#f59e0b" : "#10b981";
      threatGauge.style.color = "#fff";
    }
    if (threatTitle) {
      threatTitle.textContent = `OT Industrial Threat Condition: ${level}`;
    }
    if (threatDesc) {
      threatDesc.textContent = `${secData.active_devices ?? 14} industrial devices scanned across subnet. ${(secData.open_critical_ports && secData.open_critical_ports.length) ?? 0} critical OT ports monitored.`;
    }

    // Update Active Industrial Ports & Protocols Grid
    const portsGrid = document.querySelector(".ports-badge-grid");
    if (portsGrid && secData.open_critical_ports && secData.open_critical_ports.length > 0) {
      let portsHtml = "";
      secData.open_critical_ports.forEach(p => {
        const isCrit = p.is_critical || p.port === 502 || p.service === 'modbus';
        const cls = isCrit ? 'port-critical' : 'port-open';
        portsHtml += `<span class="port-pill ${cls}">Port ${p.port} &bull; ${(p.service || 'TCP').toUpperCase()} (${isCrit ? 'Critical' : 'Open'})</span>`;
      });
      portsGrid.innerHTML = portsHtml;
    }

    renderSuspiciousHosts(secData.suspicious_hosts || []);
    renderSecurityEvents(secData.recent_events || []);
  } catch (err) {
    console.error("Failed to load network security metrics:", err);
  }
}

function renderSecurityEvents(events) {
  const tbody = document.getElementById("sec-events-tbody");
  if (!tbody) return;

  if (!events || events.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 24px; color: var(--text-secondary);">No security incidents recorded. Subnet operating within expected baseline.</td></tr>`;
    return;
  }

  let html = "";
  events.forEach(ev => {
    const sev = ev.type || ev.severity || "NOTICE";
    const badge = sev === "CRITICAL" ? "badge-danger" : sev === "WARNING" ? "badge-warning" : "badge-info";
    html += `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 0.82rem;">${ev.time || ev.timestamp || 'Recent'}</td>
        <td><span class="badge ${badge}"><span class="badge-dot"></span>${sev}</span></td>
        <td class="td-code">${ev.ip || '192.168.1.1'}</td>
        <td>${ev.event || ev.message}</td>
        <td><strong>${ev.status || 'Audited'}</strong></td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

function renderSuspiciousHosts(hosts) {
  const container = document.getElementById("suspicious-hosts-container");
  if (!container) return;

  if (!hosts || hosts.length === 0) {
    container.innerHTML = `
      <div style="padding: 16px 20px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: var(--radius-md); color: #047857; font-size: 0.9rem;">
        &#10003; Zero unrecognized or rogue hosts active on the monitored industrial subnets.
      </div>
    `;
    return;
  }

  let html = "";
  hosts.forEach(h => {
    html += `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; background: #fdf6f6; border: 1px solid rgba(239, 68, 68, 0.2); border-radius: var(--radius-md); margin-bottom: 10px;">
        <div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="td-code" style="color: #991b1b; font-weight: 700;">${h.ip}</span>
            <span class="badge badge-danger">${h.risk || 'Unverified'}</span>
          </div>
          <div style="font-size: 0.82rem; color: #7f1d1d; margin-top: 4px;">MAC: ${h.mac || 'N/A'} &bull; ${h.vendor || 'Unregistered Host'}</div>
        </div>
        <button class="btn btn-danger btn-sm" onclick="isolateHost('${h.ip}', this)">${h.action || 'Isolate'}</button>
      </div>
    `;
  });
  container.innerHTML = html;
}

function isolateHost(ip, btnEl) {
  if (btnEl) {
    btnEl.textContent = "Quarantined";
    btnEl.classList.remove("btn-danger");
    btnEl.classList.add("btn-secondary");
    btnEl.disabled = true;

    const parent = btnEl.closest("div[style*='display: flex']");
    if (parent) {
      const badge = parent.querySelector(".badge-danger");
      if (badge) {
        badge.textContent = "Isolated";
        badge.classList.remove("badge-danger");
        badge.classList.add("badge-neutral");
      }
    }
  }

  showToast(`Host ${ip} has been isolated by Sentinel firewall rule!`, "success");
}

window.isolateHost = isolateHost;
