/* ===================================================================
   SENTINEL-TRACE EXECUTIVE DASHBOARD CONTROLLER
   Renders Live KPIs from Firestore, Chart.js Production & Compliance Gauges, Alerts
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  const stats = await loadDashboardMetrics();
  initProductionChart();
  initComplianceDonutChart(stats);
  await loadRecentAlerts();
});

// Load KPI Data
async function loadDashboardMetrics() {
  const stats = await getDashboardStats();

  const elBatches = document.getElementById("kpi-total-batches");
  const elCompliance = document.getElementById("kpi-compliance-rate");
  const elNetwork = document.getElementById("kpi-network-status");
  const elAlerts = document.getElementById("kpi-active-alerts");

  if (elBatches) elBatches.textContent = stats.total_batches ?? stats.totalBatches ?? 0;
  if (elCompliance) {
    const rateVal = stats.compliance_rate !== undefined ? `${stats.compliance_rate}%` : (stats.complianceRate || "100%");
    elCompliance.textContent = rateVal;
  }
  if (elNetwork) elNetwork.textContent = stats.network_status || stats.networkStatus || "Secure";
  if (elAlerts) elAlerts.textContent = stats.active_alerts ?? stats.activeAlerts ?? 0;

  return stats;
}

// Production Overview Chart (Area/Line with smooth curves)
function initProductionChart() {
  const ctx = document.getElementById("productionOverviewChart");
  if (!ctx || !window.Chart) return;

  new Chart(ctx, {
    type: 'line',
    data: {
      labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      datasets: [
        {
          label: 'Completed Batches',
          data: [42, 68, 85, 120, 160, 195, 200],
          borderColor: '#fa7b7b', // Signature Warm Coral
          backgroundColor: 'rgba(250, 123, 123, 0.16)',
          fill: true,
          tension: 0.4,
          pointBackgroundColor: '#fa7b7b',
          pointBorderColor: '#ffffff',
          pointBorderWidth: 2,
          pointRadius: 5,
          pointHoverRadius: 7
        },
        {
          label: 'Pending QA Checks',
          data: [12, 19, 15, 25, 18, 14, 10],
          borderColor: '#f97316', // Vibrant Orange
          backgroundColor: 'rgba(249, 115, 22, 0.08)',
          fill: true,
          tension: 0.4,
          pointBackgroundColor: '#f97316',
          pointBorderColor: '#ffffff',
          pointBorderWidth: 2,
          pointRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            boxWidth: 12,
            font: { family: "'Plus Jakarta Sans', sans-serif", size: 12 }
          }
        },
        tooltip: {
          backgroundColor: '#1e293b',
          titleFont: { family: "'Plus Jakarta Sans', sans-serif" },
          padding: 12,
          cornerRadius: 8
        }
      },
      scales: {
        x: {
          grid: { display: false }
        },
        y: {
          grid: { color: 'rgba(0, 0, 0, 0.04)' },
          ticks: { font: { family: "'Plus Jakarta Sans', sans-serif" } }
        }
      }
    }
  });
}

// Compliance Status Donut Chart
function initComplianceDonutChart(stats) {
  const ctx = document.getElementById("complianceDonutChart");
  if (!ctx || !window.Chart) return;

  const compliant = stats?.compliant_records ?? 22;
  const nonCompliant = (stats?.pending_compliance ?? 5) + (stats?.expired_compliance ?? 3);
  const total = compliant + nonCompliant;
  const compliantPct = total > 0 ? Math.round((compliant / total) * 100) : 98;
  const reviewPct = 100 - compliantPct;

  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: [`Compliant (${compliantPct}%)`, `Review / Pending (${reviewPct}%)`],
      datasets: [{
        data: [compliantPct, reviewPct],
        backgroundColor: ['#fa7b7b', '#f59e0b'],
        borderWidth: 0,
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '78%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 },
            boxWidth: 10
          }
        }
      }
    }
  });
}

// Load Recent Alerts Feed
async function loadRecentAlerts() {
  const alerts = await getAlerts();
  const container = document.getElementById("dashboard-alerts-feed");
  if (!container) return;

  if (!alerts || alerts.length === 0) {
    container.innerHTML = `<div style="padding: 16px 0; color: var(--text-secondary); font-size: 0.85rem;">No active alerts recorded in system.</div>`;
    return;
  }

  const top3 = alerts.slice(0, 3);
  let html = "";

  top3.forEach(a => {
    const badgeClass = a.severity === "Critical" ? "badge-danger" : a.severity === "Warning" ? "badge-warning" : "badge-info";
    html += `
      <div style="display: flex; align-items: flex-start; justify-content: space-between; padding: 14px 0; border-bottom: 1px solid rgba(0,0,0,0.05); gap: 12px;">
        <div style="display: flex; flex-direction: column; gap: 4px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="badge ${badgeClass}"><span class="badge-dot"></span>${a.severity}</span>
            <span style="font-weight: 700; font-size: 0.9rem; color: var(--text-primary);">${a.title}</span>
          </div>
          <p style="font-size: 0.8rem; color: var(--text-secondary); margin: 0;">${a.details}</p>
        </div>
        <span style="font-size: 0.74rem; color: var(--text-muted); white-space: nowrap;">${a.timestamp}</span>
      </div>
    `;
  });

  container.innerHTML = html;
}
