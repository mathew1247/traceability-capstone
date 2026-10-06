from collections import Counter
from config import Config
from config.firebase import db

def get_reports_summary():
    """
    Requirement 25:
    Aggregates analytical data across Production, Compliance, Network, and Alerts
    suitable for frontend charts and executive reports.
    """
    # 1. Production Analytics
    batches = [doc.to_dict() for doc in db.collection(Config.COLLECTION_PRODUCTION_BATCHES).get() if doc.to_dict()]
    batch_status_counts = Counter(b.get('status', 'Unknown') for b in batches)
    total_batch_qty = sum(b.get('quantity', 0) for b in batches)

    # 2. Compliance Analytics
    compliance_records = [doc.to_dict() for doc in db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).get() if doc.to_dict()]
    standard_counts = Counter(c.get('standard', 'Other') for c in compliance_records)
    compliance_status_counts = Counter(c.get('status', 'Unknown') for c in compliance_records)

    # 3. Network Analytics
    scans = [doc.to_dict() for doc in db.collection(Config.COLLECTION_NETWORK_SCANS).order_by('scan_date', direction='DESCENDING').limit(10).get() if doc.to_dict()]
    total_scans_run = len(scans)
    latest_scan = scans[0] if scans else None
    open_ports_list = latest_scan.get('open_ports', []) if latest_scan else []

    # 4. Alerts Analytics
    alerts = [doc.to_dict() for doc in db.collection(Config.COLLECTION_ALERTS).get() if doc.to_dict()]
    alert_severity_counts = Counter(a.get('severity', 'Unknown') for a in alerts)
    alert_status_counts = Counter(a.get('status', 'Unknown') for a in alerts)

    return {
        "production": {
            "total_batches": len(batches),
            "total_units_manufactured": total_batch_qty,
            "status_distribution": dict(batch_status_counts)
        },
        "compliance": {
            "total_certifications": len(compliance_records),
            "standards_distribution": dict(standard_counts),
            "status_distribution": dict(compliance_status_counts)
        },
        "network": {
            "total_scans_conducted": total_scans_run,
            "active_hosts_latest": latest_scan.get('devices_found', 0) if latest_scan else 0,
            "open_ports_count": len(open_ports_list),
            "critical_ports_count": sum(1 for p in open_ports_list if p.get('is_critical'))
        },
        "alerts": {
            "total_alerts": len(alerts),
            "severity_distribution": dict(alert_severity_counts),
            "status_distribution": dict(alert_status_counts)
        }
    }
