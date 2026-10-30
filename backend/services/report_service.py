from collections import Counter
from datetime import datetime
from config import Config
from config.firebase import db
from services.network_service import get_security_monitor_summary

def get_reports_summary():
    """
    Requirement 25:
    Aggregates analytical data across Production, Compliance, Network, and Alerts
    suitable for frontend charts and executive reports.
    Aligned with dashboard_service metrics for calculation consistency.
    """
    # 1. Production Analytics & Real Monthly Throughput
    batches = [doc.to_dict() for doc in db.collection(Config.COLLECTION_PRODUCTION_BATCHES).get() if doc.to_dict()]
    batch_status_counts = Counter(b.get('status', 'Unknown') for b in batches)
    total_batch_qty = sum(int(b.get('quantity', 0)) for b in batches)

    monthly_map = {}
    for b in batches:
        p_date = str(b.get('production_date') or (b.get('created_at') or ''))[:10]
        if len(p_date) >= 7 and p_date[:4].isdigit() and p_date[5:7].isdigit():
            m_key = p_date[:7]
            try:
                dt = datetime.strptime(m_key, '%Y-%m')
                m_label = dt.strftime('%b %Y')
            except Exception:
                m_label = m_key
        else:
            m_key = "Current"
            m_label = "Current Period"

        if m_key not in monthly_map:
            monthly_map[m_key] = {
                "month_key": m_key,
                "month_label": m_label,
                "completed_units": 0,
                "pending_qa_units": 0,
                "completed_batches": 0,
                "pending_qa_batches": 0,
                "total_units": 0,
                "batch_count": 0
            }

        qty = int(b.get('quantity', 0))
        st = b.get('status', 'Pending')
        monthly_map[m_key]["total_units"] += qty
        monthly_map[m_key]["batch_count"] += 1
        if st in ('Completed', 'Passed'):
            monthly_map[m_key]["completed_units"] += qty
            monthly_map[m_key]["completed_batches"] += 1
        elif st in ('In QA Inspection', 'Running', 'Pending'):
            monthly_map[m_key]["pending_qa_units"] += qty
            monthly_map[m_key]["pending_qa_batches"] += 1

    monthly_throughput = sorted(monthly_map.values(), key=lambda x: x["month_key"])

    # 2. Compliance Analytics
    compliance_records = [doc.to_dict() for doc in db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).get() if doc.to_dict()]
    total_compliance = len(compliance_records)
    standard_counts = Counter(c.get('standard', 'Other') for c in compliance_records)
    compliance_status_counts = Counter(c.get('status', 'Unknown') for c in compliance_records)

    compliant_count = compliance_status_counts.get('Compliant', 0)
    pending_count = compliance_status_counts.get('Pending', 0) + compliance_status_counts.get('Review Required', 0)
    expired_count = compliance_status_counts.get('Expired', 0) + compliance_status_counts.get('Non-Compliant', 0)
    compliance_rate = round((compliant_count / total_compliance * 100), 1) if total_compliance > 0 else 100.0

    # 3. Network Analytics
    scans = [doc.to_dict() for doc in db.collection(Config.COLLECTION_NETWORK_SCANS).order_by('scan_date', direction='DESCENDING').limit(10).get() if doc.to_dict()]
    total_scans_run = len(scans)
    latest_scan = scans[0] if scans else None
    open_ports_list = latest_scan.get('open_ports', []) if latest_scan else []
    sec_summary = get_security_monitor_summary()

    # 4. Alerts Analytics
    alerts = [doc.to_dict() for doc in db.collection(Config.COLLECTION_ALERTS).get() if doc.to_dict()]
    alert_severity_counts = Counter(a.get('severity', 'Unknown') for a in alerts)
    alert_status_counts = Counter(a.get('status', 'Unknown') for a in alerts)

    critical_alerts = alert_severity_counts.get('Critical', 0)
    warning_alerts = alert_severity_counts.get('Warning', 0)
    active_alerts = alert_status_counts.get('Active', 0) + alert_status_counts.get('Open', 0)

    return {
        "production": {
            "total_batches": len(batches),
            "total_units_manufactured": total_batch_qty,
            "status_distribution": dict(batch_status_counts),
            "monthly_throughput": monthly_throughput
        },
        "compliance": {
            "total_certifications": total_compliance,
            "compliant_count": compliant_count,
            "pending_count": pending_count,
            "expired_count": expired_count,
            "compliance_rate": compliance_rate,
            "standards_distribution": dict(standard_counts),
            "status_distribution": dict(compliance_status_counts)
        },
        "network": {
            "total_scans_conducted": total_scans_run,
            "active_hosts_latest": latest_scan.get('devices_found', 0) if latest_scan else 0,
            "open_ports_count": len(open_ports_list),
            "critical_ports_count": sum(1 for p in open_ports_list if p.get('is_critical')),
            "network_status": sec_summary.get('network_status', 'Secure'),
            "threat_level": sec_summary.get('threat_level', 'Low')
        },
        "alerts": {
            "total_alerts": len(alerts),
            "active_alerts": active_alerts,
            "critical_alerts": critical_alerts,
            "warning_alerts": warning_alerts,
            "severity_distribution": dict(alert_severity_counts),
            "status_distribution": dict(alert_status_counts)
        }
    }
