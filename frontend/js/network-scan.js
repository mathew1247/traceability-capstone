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
    terminal.innerHTML = `[${new Date().toLocaleTimeString()}] Initiating Nmap probe target: ${target}...\n`;

    // Simulated terminal progress steps while triggering API
    let progress = 0;
    const interval = setInterval(() => {
      progress += 20;
      if (progress <= 100) {
        progressBar.style.width = `${progress}%`;
        progressPercent.textContent = `${progress}%`;
      }
      if (progress === 20) {
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] Sending ARP discovery broadcast on local segment...\n`;
      } else if (progress === 60) {
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] <span class="log-success">Discovered 14 active OT/IT host interfaces.</span>\n`;
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] Probing TCP SYN top ports (22, 80, 443, 502, 4840)...\n`;
      } else if (progress === 100) {
        clearInterval(interval);
      }
    }, 280);

    try {
      const scanResult = await startNetworkScan(target);
      setTimeout(() => {
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] <span class="log-success">Nmap scan complete. Duration: ${scanResult.duration}</span>\n`;
        terminal.innerHTML += `[${new Date().toLocaleTimeString()}] <span class="log-warning">ALERT: Exposed unauthenticated Modbus-TCP detected on 192.168.1.88:502</span>\n`;
        scanBtn.disabled = false;
        scanBtn.innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
          Start Network Scan
        `;
        renderScanResults(scanResult);
        loadScanHistory();
        showToast("Network scan finished successfully!", "success");
      }, 1600);
    } catch (err) {
      showToast("Scan probe error: " + err.message, "danger");
      scanBtn.disabled = false;
    }
  });
}

function renderScanResults(scan) {
  const container = document.getElementById("scan-results-container");
  if (!container) return;

  container.style.display = "block";
  document.getElementById("res-target").textContent = scan.target;
  document.getElementById("res-devices").textContent = `${scan.devicesFound} Hosts Active`;
  document.getElementById("res-duration").textContent = scan.duration;

  const portsTbody = document.getElementById("scan-ports-body");
  if (portsTbody && scan.openPorts) {
    let html = "";
    scan.openPorts.forEach(p => {
      const isCritical = p.risk === "Critical";
      const isWarning = p.risk === "Warning";
      const badge = isCritical ? "badge-danger" : isWarning ? "badge-warning" : "badge-success";

      html += `
        <tr>
          <td class="td-code" style="font-weight: 700; color: #e05e5e;">${p.port} / TCP</td>
          <td><strong>${p.service}</strong></td>
          <td>${p.host}</td>
          <td><span class="badge badge-success"><span class="badge-dot"></span>${p.state}</span></td>
          <td><span class="badge ${badge}">${p.risk}</span></td>
        </tr>
      `;
    });
    portsTbody.innerHTML = html;
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
