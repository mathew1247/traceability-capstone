/* ===================================================================
   SENTINEL-TRACE NETWORK SCANNER CONTROLLER
   Triggers Flask POST /api/network/scan, Terminal Progress Simulation, Port Matrix
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await loadScanHistory();
  initScanControls();

  const params = new URLSearchParams(window.location.search);
  if (params.get("action") === "scan") {
    const input = document.getElementById("scan-target-ip");
    if (input) input.focus();
    showToast("Ready to run automated OT subnet scan. Click 'Start Network Scan' to begin.", "info");
  }
});

function initScanControls() {
  const scanBtn = document.getElementById("start-scan-btn");
  if (!scanBtn) return;

  scanBtn.addEventListener("click", async () => {
    const target = document.getElementById("scan-target-ip").value.trim() || "192.168.1.0/24";
    const statusBox = document.getElementById("scan-status-box");
    const progressBar = document.getElementById("scan-progress-bar");
    const progressPercent = document.getElementById("scan-progress-percent");
    const terminal = document.getElementById("scan-terminal-logs");
    const resultsCard = document.getElementById("scan-results-container");

    scanBtn.disabled = true;
    scanBtn.innerHTML = `<span>Scanning Subnet...</span>`;
    statusBox.style.display = "block";
    resultsCard.style.display = "none";
    terminal.innerHTML = `[${new Date().toLocaleTimeString()}] Initializing probe for target: ${target}...\n`;

    let progress = 0;
    const interval = setInterval(() => {
      progress += 20;
      if (progress <= 90) {
        progressBar.style.width = `${progress}%`;
        progressPercent.textContent = `${progress}%`;
      }
      if (progress === 20) {
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] Validating authorization and target subnet boundary...\n`;
      } else if (progress === 60) {
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] Dispatching probe request to backend scanner service...\n`;
      }
    }, 280);

    try {
      const scanResult = await startNetworkScan(target);
      clearInterval(interval);
      progressBar.style.width = "100%";
      progressPercent.textContent = "100%";

      const engineName = scanResult.scannerEngine || scanResult.scanner_engine || "Scanner Engine";
      terminal.innerHTML += `[${new Date().toLocaleTimeString()}] <span class="log-success">Execution complete. Engine: ${engineName}</span>\n`;

      if (scanResult.limitations) {
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] <span class="log-warning">Engine Notice: ${scanResult.limitations}</span>\n`;
      }

      terminal.innerHTML += `[${new Date().toLocaleTimeString()}] Scan Result: Discovered ${scanResult.devicesFound} active host(s).\n`;

      if (scanResult.openPorts && scanResult.openPorts.length > 0) {
        scanResult.openPorts.forEach(p => {
          const isCrit = p.risk === "Critical" || p.is_critical;
          const cls = isCrit ? "log-warning" : "log-success";
          terminal.innerHTML += `[${new Date().toLocaleTimeString()}] <span class="${cls}">Open Port: ${p.port}/${p.service || 'tcp'} on ${p.host} (${p.state || 'open'})</span>\n`;
        });
      } else {
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] No open ports discovered on target.\n`;
      }

      if (scanResult.newHostsDetected && scanResult.newHostsDetected.length > 0) {
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] <span class="log-warning">ALERT: Unverified newly observed host(s): ${scanResult.newHostsDetected.join(", ")}</span>\n`;
      }

      scanBtn.disabled = false;
      scanBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        Start Network Scan
      `;
      renderScanResults(scanResult);
      await loadScanHistory();
      showToast(`Network scan completed (${engineName})`, "success");
    } catch (err) {
      clearInterval(interval);
      progressBar.style.width = "100%";
      progressPercent.textContent = "Failed";
      terminal.innerHTML += `[${new Date().toLocaleTimeString()}] <span class="log-error" style="color: #ef4444;">Scan execution error: ${err.message}</span>\n`;
      showToast("Scan probe error: " + err.message, "danger");
      scanBtn.disabled = false;
      scanBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        Start Network Scan
      `;
    }
  });
}

function renderScanResults(scan) {
  const container = document.getElementById("scan-results-container");
  if (!container) return;

  container.style.display = "block";
  document.getElementById("res-target").textContent = scan.target;
  document.getElementById("res-devices").textContent = `${scan.devicesFound} Hosts Active`;
  document.getElementById("res-duration").textContent = scan.duration || "N/A";

  const portsTbody = document.getElementById("scan-ports-body");
  if (portsTbody) {
    if (scan.openPorts && scan.openPorts.length > 0) {
      let html = "";
      scan.openPorts.forEach(p => {
        const isCritical = p.risk === "Critical";
        const isWarning = p.risk === "Warning";
        const badge = isCritical ? "badge-danger" : isWarning ? "badge-warning" : "badge-success";

        html += `
          <tr>
            <td class="td-code" style="font-weight: 700; color: #e05e5e;">${p.port} / TCP</td>
            <td><strong>${p.service || 'unknown'}</strong></td>
            <td>${p.host || scan.target}</td>
            <td><span class="badge badge-success"><span class="badge-dot"></span>${p.state || 'open'}</span></td>
            <td><span class="badge ${badge}">${p.risk || (isCritical ? 'Critical' : 'Normal')}</span></td>
          </tr>
        `;
      });
      portsTbody.innerHTML = html;
    } else {
      portsTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 24px; color: var(--text-secondary);">No open ports discovered on target.</td></tr>`;
    }
  }
}

async function loadScanHistory() {
  const history = await getNetworkHistory();
  const tbody = document.getElementById("scan-history-tbody");
  if (!tbody) return;

  let html = "";
  history.forEach(s => {
    html += `
      <tr>
        <td class="td-code">${s.id}</td>
        <td><strong>${s.target}</strong></td>
        <td>${s.timestamp}</td>
        <td>${s.duration}</td>
        <td>${s.devicesFound} Devices</td>
        <td><span class="badge badge-success"><span class="badge-dot"></span>${s.status}</span></td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}
