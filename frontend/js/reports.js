/* ===================================================================
   SENTINEL-TRACE ANALYTICS & REPORTS CONTROLLER
   Production Trends, Batch Throughput, Compliance Curves, CSV/PDF Export
   =================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  initThroughputChart();
  initThreatDistributionChart();
});

function initThroughputChart() {
  const ctx = document.getElementById("batchThroughputChart");
  if (!ctx || !window.Chart) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct'],
      datasets: [
        {
          label: 'Completed Batches',
          data: [45, 52, 60, 78, 92, 110],
          backgroundColor: '#fa7b7b',
          borderRadius: 6
        },
        {
          label: 'Inspection Passes',
          data: [44, 50, 58, 77, 90, 108],
          backgroundColor: '#f97316',
          borderRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: { font: { family: "'Plus Jakarta Sans', sans-serif" } }
        }
      },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: 'rgba(0,0,0,0.04)' } }
      }
    }
  });
}

function initThreatDistributionChart() {
  const ctx = document.getElementById("threatDistributionChart");
  if (!ctx || !window.Chart) return;

  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Verified OT Nodes (85%)', 'Monitored Devices (10%)', 'Suspicious/Quarantined (5%)'],
      datasets: [{
        data: [85, 10, 5],
        backgroundColor: ['#fa7b7b', '#f97316', '#ef4444'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } }
        }
      }
    }
  });
}

function exportReport(format) {
  showToast(`Compiling and downloading Sentinel-Trace executive report in ${format.toUpperCase()} format...`, "success");
}

function handleGenerateReport() {
  const mod = document.getElementById("report-module").value;
  const range = document.getElementById("report-range").value;
  showToast(`Generated comprehensive analytics dossier for module: ${mod} (${range})`, "success");
}
