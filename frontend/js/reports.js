/* ===================================================================
   SENTINEL-TRACE ANALYTICS & REPORTS CONTROLLER
   Production Trends, Batch Throughput, Compliance Curves, CSV/PDF Export
   Connected to Flask GET /api/reports/summary with live Cloud Firestore
   =================================================================== */

let throughputChartInstance = null;
let threatDistributionChartInstance = null;

document.addEventListener("DOMContentLoaded", async () => {
  const summary = await getReportsSummary().catch(() => null);
  initThroughputChart(summary);
  initThreatDistributionChart(summary);

  const summaryTxt = document.getElementById("reports-asset-summary-txt");
  if (summaryTxt) {
    const totalScans = summary?.network?.total_scans_conducted ?? summary?.network?.total_scans ?? 0;
    const totalBatches = summary?.production?.total_batches ?? 0;
    summaryTxt.innerHTML = `<strong>${totalBatches} Production Batches</strong> &bull; ${totalScans} Network Security Scans Indexed`;
  }
});

function initThroughputChart(summary) {
  const ctx = document.getElementById("batchThroughputChart");
  if (!ctx || !window.Chart) return;

  if (throughputChartInstance) {
    throughputChartInstance.destroy();
  }

  const monthly = summary?.production?.monthly_throughput;
  let labels = [];
  let completedData = [];
  let qaData = [];

  if (monthly && monthly.length > 0) {
    labels = monthly.map(m => m.month_label || m.month_key);
    completedData = monthly.map(m => m.completed_units ?? 0);
    qaData = monthly.map(m => m.pending_qa_units ?? 0);
  } else {
    const prod = summary?.production;
    const totalCompleted = (prod?.status_distribution?.Completed || 0) + (prod?.status_distribution?.Passed || 0);
    const totalQA = (prod?.status_distribution?.["In QA Inspection"] || 0) + (prod?.status_distribution?.Running || 0) + (prod?.status_distribution?.Pending || 0);

    if (totalCompleted > 0 || totalQA > 0) {
      labels = ['Current Period'];
      completedData = [totalCompleted];
      qaData = [totalQA];
    } else {
      labels = ['No Batches Recorded'];
      completedData = [0];
      qaData = [0];
    }
  }

  throughputChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Completed / Passed Units',
          data: completedData,
          backgroundColor: '#fa7b7b',
          borderRadius: 6
        },
        {
          label: 'In QA / Running Units',
          data: qaData,
          backgroundColor: '#1e293b',
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
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              return ` ${context.dataset.label}: ${context.parsed.y.toLocaleString()} Units`;
            }
          }
        }
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          grid: { color: 'rgba(0,0,0,0.04)' },
          ticks: {
            callback: function(value) {
              return value === 0 ? '0' : `${value} u`;
            }
          }
        }
      }
    }
  });
}

function initThreatDistributionChart(summary) {
  const ctx = document.getElementById("threatDistributionChart");
  if (!ctx || !window.Chart) return;

  if (threatDistributionChartInstance) {
    threatDistributionChartInstance.destroy();
  }

  const comp = summary?.compliance;
  const compliant = comp?.compliant_count ?? comp?.status_distribution?.Compliant ?? 0;
  const pending = comp?.pending_count ?? ((comp?.status_distribution?.["Review Required"] || 0) + (comp?.status_distribution?.Pending || 0));
  const nonComp = comp?.expired_count ?? ((comp?.status_distribution?.["Non-Compliant"] || 0) + (comp?.status_distribution?.Expired || 0));
  const total = compliant + pending + nonComp;

  let labels = [];
  let data = [];
  let bgColors = [];

  if (total > 0) {
    const compliantPct = Math.round((compliant / total) * 100);
    const pendingPct = Math.round((pending / total) * 100);
    const nonCompPct = Math.max(0, 100 - compliantPct - pendingPct);

    labels = [
      `Compliant (${compliantPct}%)`,
      `Pending Review (${pendingPct}%)`,
      `Non-Compliant (${nonCompPct}%)`
    ];
    data = [compliantPct, pendingPct, nonCompPct];
    bgColors = ['#10b981', '#f59e0b', '#ef4444'];
  } else {
    labels = ['No Compliance Audits (0%)'];
    data = [100];
    bgColors = ['#94a3b8'];
  }

  threatDistributionChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: bgColors,
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

async function exportReport(format) {
  if (format === 'csv') {
    try {
      showToast("Compiling live Firestore production & compliance data into CSV...", "info");
      const [batches, compliance] = await Promise.all([
        getBatches().catch(() => []),
        getCompliance().catch(() => [])
      ]);

      let csv = "Type,Record ID,Title / Product,Secondary Meta,Metric / Quantity,Status,Timestamp\n";
      (batches || []).forEach(b => {
        const prodName = b.product_name || b.product || '';
        const matName = b.material_name || b.material || '';
        csv += `Production Batch,"${b.id}","${prodName}","${matName}","${b.quantity} Units","${b.status}","${b.production_date || b.created_at || b.date || ''}"\n`;
      });
      (compliance || []).forEach(c => {
        csv += `Compliance Audit,"${c.id}","${c.product || ''}","${c.standard || ''}","Score: ${c.score ?? 'N/A'}","${c.status}","${c.expiryDate || c.expiry_date || ''}"\n`;
      });

      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sentinel_trace_executive_analytics_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      showToast("Downloaded Sentinel-Trace Analytics CSV report!", "success");
    } catch (e) {
      showToast(`Export failed: ${e.message}`, "danger");
    }
  } else if (format === 'pdf') {
    showToast("Opening system print dialog for PDF export...", "info");
    setTimeout(() => {
      window.print();
    }, 400);
  }
}

async function handleGenerateReport() {
  const mod = document.getElementById("report-module").value;
  const range = document.getElementById("report-range").value;
  showToast(`Generating live analytics dossier for: ${mod} (${range})...`, "info");
  
  const summary = await getReportsSummary().catch(() => null);
  initThroughputChart(summary);
  initThreatDistributionChart(summary);
  showToast(`Updated analytics view for ${mod} (${range}) from Cloud Firestore!`, "success");
}

window.exportReport = exportReport;
window.handleGenerateReport = handleGenerateReport;
