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

    // Safely extract counts and lists
    const suspiciousHostsList = Array.isArray(secData.suspicious_hosts)
      ? secData.suspicious_hosts
      : [];
    const suspiciousCount = secData.suspicious_hosts_count !== undefined
      ? secData.suspicious_hosts_count
      : (Array.isArray(secData.suspicious_hosts) ? secData.suspicious_hosts.length : (typeof secData.suspicious_hosts === 'number' ? secData.suspicious_hosts : 0));

    const criticalPortsList = Array.isArray(secData.open_critical_ports)
      ? secData.open_critical_ports
      : [];
    const criticalPortsCount = secData.open_critical_ports_count !== undefined
      ? secData.open_critical_ports_count
      : (Array.isArray(secData.open_critical_ports) ? secData.open_critical_ports.length : (typeof secData.open_critical_ports === 'number' ? secData.open_critical_ports : 0));

    const activeDevices = secData.active_devices ?? 0;
    const networkStatus = secData.network_status || "Secure";

    // Update KPI values
    const kpiCards = document.querySelectorAll(".kpi-grid-4 .kpi-card");
    if (kpiCards && kpiCards.length >= 4) {
      const val0 = kpiCards[0].querySelector(".kpi-card-value");
      const val1 = kpiCards[1].querySelector(".kpi-card-value");
      const val2 = kpiCards[2].querySelector(".kpi-card-value");
      const val3 = kpiCards[3].querySelector(".kpi-card-value");

      if (val0) {
        val0.textContent = networkStatus;
        val0.style.color = (networkStatus === "Critical") ? "#ef4444" : (networkStatus === "Warning" ? "#f59e0b" : "#10b981");
      }
      if (val1) val1.textContent = activeDevices;
      if (val2) val2.textContent = suspiciousCount;
      if (val3) val3.textContent = criticalPortsCount;

      const sub1 = kpiCards[1].querySelector(".kpi-trend-row span:last-child");
      if (sub1) sub1.textContent = activeDevices > 0 ? `${Math.max(0, activeDevices - suspiciousCount)} Verified, ${suspiciousCount} Unverified` : "Awaiting Subnet Discovery";

      const sub3 = kpiCards[3].querySelector(".kpi-trend-row span:last-child");
      if (sub3) {
        const portLabels = criticalPortsList.map(p => `TCP ${p.port}`).slice(0, 3).join(", ");
        sub3.textContent = portLabels || (criticalPortsCount > 0 ? `${criticalPortsCount} Critical Ports` : "No Critical Ports");
      }
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
      threatDesc.textContent = activeDevices > 0
        ? `${activeDevices} industrial devices scanned across subnet. ${criticalPortsCount} critical OT ports monitored.`
        : "No active devices detected in the latest scan. Click 'Execute Subnet Scan' above to scan your OT subnet.";
    }

    // Update Active Industrial Ports & Protocols Grid
    const portsGrid = document.querySelector(".ports-badge-grid");
    if (portsGrid) {
      if (criticalPortsList.length > 0) {
        let portsHtml = "";
        criticalPortsList.forEach(p => {
          const isCrit = p.is_critical || p.port === 502 || p.service === 'modbus';
          const cls = isCrit ? 'port-critical' : 'port-open';
          portsHtml += `<span class="port-pill ${cls}">Port ${p.port} &bull; ${(p.service || 'TCP').toUpperCase()} (${isCrit ? 'Critical' : 'Open'})</span>`;
        });
        portsGrid.innerHTML = portsHtml;
      } else {
        portsGrid.innerHTML = `<span style="font-size: 0.85rem; color: var(--text-secondary);">No open critical industrial ports detected in latest scan.</span>`;
      }
    }

    renderSuspiciousHosts(suspiciousHostsList);
    renderSecurityEvents(secData.recent_events || []);
  } catch (err) {
    console.error("Failed to load network security metrics:", err);
  }
}

function renderSecurityEvents(events) {
  const tbody = document.getElementById("sec-events-tbody");
  if (!tbody) return;

  const eventsList = Array.isArray(events) ? events : [];

  if (eventsList.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 24px; color: var(--text-secondary);">No security incidents recorded. Subnet operating within expected baseline.</td></tr>`;
    return;
  }

  let html = "";
  eventsList.forEach(ev => {
    const sev = (ev.severity || ev.type || "NOTICE").toUpperCase();
    const badge = (sev === "CRITICAL" || sev === "HIGH") ? "badge-danger" : (sev === "WARNING" || sev === "MEDIUM") ? "badge-warning" : "badge-info";
    html += `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 0.82rem;">${ev.timestamp || ev.time || 'Recent'}</td>
        <td><span class="badge ${badge}"><span class="badge-dot"></span>${sev}</span></td>
        <td class="td-code">${ev.ip || 'Subnet'}</td>
        <td>${ev.event || ev.message || 'Security telemetry event'}</td>
        <td><strong>${ev.status || 'Audited'}</strong></td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

function renderSuspiciousHosts(hosts) {
  const container = document.getElementById("suspicious-hosts-container");
  if (!container) return;

  const hostsList = Array.isArray(hosts) ? hosts : [];

  if (hostsList.length === 0) {
    container.innerHTML = `
      <div style="padding: 16px 20px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: var(--radius-md); color: #047857; font-size: 0.9rem;">
        &#10003; Zero unrecognized or rogue hosts active on the monitored industrial subnets.
      </div>
    `;
    return;
  }

  let html = "";
  hostsList.forEach(h => {
    html += `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; background: #fdf6f6; border: 1px solid rgba(239, 68, 68, 0.2); border-radius: var(--radius-md); margin-bottom: 10px;">
        <div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="td-code" style="color: #991b1b; font-weight: 700;">${h.ip}</span>
            <span class="badge badge-danger">${h.risk || 'Unverified'}</span>
          </div>
          <div style="font-size: 0.82rem; color: #7f1d1d; margin-top: 4px;">MAC: ${h.mac || 'N/A'} &bull; ${h.vendor || h.hostname || 'Unregistered Host'}</div>
        </div>
        <button class="btn btn-secondary btn-sm" disabled style="opacity: 0.65; cursor: not-allowed;" title="Host isolation is disabled: Requires network firewall/SDN enforcement infrastructure not configured in this deployment" onclick="isolateHost('${h.ip}', this)">${h.action ? h.action + ' (Disabled)' : 'Isolate (Disabled)'}</button>
      </div>
    `;
  });
  container.innerHTML = html;
}

function isolateHost(ip, btnEl) {
  // Host isolation is intentionally disabled in this phase.
  // Secure implementation requires dedicated firewall/SDN (iptables/802.1X) infrastructure
  // which is not configured in this environment. We do not alter firewall rules or simulate quarantine.
  showToast(`Host isolation unavailable: Dedicated firewall/SDN enforcement is not configured. Host ${ip} was not modified.`, "warning");
}

window.isolateHost = isolateHost;
