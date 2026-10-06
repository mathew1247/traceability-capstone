from config import Config
from config.firebase import db
from services.network_service import get_security_monitor_summary
from services.firestore_service import serialize_value

def get_dashboard_metrics():
    """
    Requirement 16:
    Calculates live dashboard statistics directly from Firestore:
    total_products, total_batches, total_materials, total_suppliers,
    total_compliance_records, compliant_records, pending_compliance, expired_compliance,
    total_alerts, critical_alerts, warning_alerts, active_devices, recent_scans.
    """
    products_count = len(db.collection(Config.COLLECTION_PRODUCTS).get())
    batches_count = len(db.collection(Config.COLLECTION_PRODUCTION_BATCHES).get())
    materials_count = len(db.collection(Config.COLLECTION_RAW_MATERIALS).get())
    suppliers_count = len(db.collection(Config.COLLECTION_SUPPLIERS).get())

    # Compliance calculation
    compliance_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).get()
    total_compliance = len(compliance_docs)
    compliant_count = 0
    pending_count = 0
    expired_count = 0

    for c in compliance_docs:
        c_data = c.to_dict() or {}
        st = c_data.get('status')
        if st == 'Compliant':
            compliant_count += 1
        elif st in ('Pending', 'Review Required'):
            pending_count += 1
        elif st in ('Expired', 'Non-Compliant'):
            expired_count += 1

    compliance_rate = round((compliant_count / total_compliance * 100), 1) if total_compliance > 0 else 100.0

    # Alerts calculation
    all_alerts_docs = db.collection(Config.COLLECTION_ALERTS).get()
    total_alerts = len(all_alerts_docs)
    critical_alerts = 0
    warning_alerts = 0
    active_alerts = 0

    for a in all_alerts_docs:
        a_data = a.to_dict() or {}
        status = a_data.get('status')
        severity = a_data.get('severity')
        if status in ('Active', 'Open'):
            active_alerts += 1
        if severity == 'Critical':
            critical_alerts += 1
        elif severity == 'Warning':
            warning_alerts += 1

    # Network Security Summary
    sec_summary = get_security_monitor_summary()
    recent_scans_docs = db.collection(Config.COLLECTION_NETWORK_SCANS)\
                          .order_by('scan_date', direction='DESCENDING')\
                          .limit(5)\
                          .get()
    recent_scans = [serialize_value(s.to_dict()) for s in recent_scans_docs if s.to_dict()]

    # Recent Activity
    logs = db.collection(Config.COLLECTION_ACTIVITY_LOGS)\
             .order_by('timestamp', direction='DESCENDING')\
             .limit(6)\
             .get()
    recent_activity = [serialize_value(log.to_dict()) for log in logs if log.to_dict()]

    return {
        "total_products": products_count,
        "total_batches": batches_count,
        "total_materials": materials_count,
        "total_suppliers": suppliers_count,
        "total_compliance_records": total_compliance,
        "compliant_records": compliant_count,
        "pending_compliance": pending_count,
        "expired_compliance": expired_count,
        "compliance_rate": compliance_rate,
        "total_alerts": total_alerts,
        "active_alerts": active_alerts,
        "critical_alerts": critical_alerts,
        "warning_alerts": warning_alerts,
        "active_devices": sec_summary.get('active_devices', 0),
        "network_status": sec_summary.get('network_status', 'Secure'),
        "threat_level": sec_summary.get('threat_level', 'Low'),
        "recent_scans": recent_scans,
        "recent_activity": recent_activity
    }
