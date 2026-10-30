from collections import Counter
from datetime import datetime
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
    compliance_rate, total_alerts, critical_alerts, warning_alerts,
    total_units_produced, total_material_quantity, completed_units, pending_qa_units,
    batch_status_distribution, recent_batches, monthly_throughput,
    active_devices, recent_scans, recent_activity.
    """
    # 1. Products catalog
    products_docs = db.collection(Config.COLLECTION_PRODUCTS).get()
    products_dict = {p.id: p.to_dict() for p in products_docs if p.to_dict()}
    products_count = len(products_dict)

    # 2. Raw materials
    materials_docs = db.collection(Config.COLLECTION_RAW_MATERIALS).get()
    materials_list = [m.to_dict() for m in materials_docs if m.to_dict()]
    materials_dict = {m.get('material_id', m.get('id')): m for m in materials_list}
    materials_count = len(materials_list)
    total_material_quantity = round(sum(float(m.get('quantity', 0.0)) for m in materials_list), 2)

    # 3. Suppliers
    suppliers_count = len(db.collection(Config.COLLECTION_SUPPLIERS).get())

    # 4. Production batches & real monthly throughput
    batch_docs = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).get()
    batches = [b.to_dict() for b in batch_docs if b.to_dict()]
    batches_count = len(batches)
    total_units_produced = sum(int(b.get('quantity', 0)) for b in batches)
    batch_status_counts = Counter(b.get('status', 'Unknown') for b in batches)

    completed_units = sum(
        int(b.get('quantity', 0)) for b in batches
        if b.get('status') in ('Completed', 'Passed')
    )
    pending_qa_units = sum(
        int(b.get('quantity', 0)) for b in batches
        if b.get('status') in ('In QA Inspection', 'Running', 'Pending')
    )

    # Aggregate real monthly throughput from actual batch records (no synthetic data)
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

    # Recent batches with resolved entity names for UI widgets
    sorted_batches = sorted(
        batches,
        key=lambda b: str(b.get('created_at') or b.get('production_date') or ''),
        reverse=True
    )
    recent_batches = []
    for b in sorted_batches[:10]:
        b_dict = serialize_value(b)
        p_id = b.get('product_id')
        m_id = b.get('material_id')
        prod_obj = products_dict.get(p_id)
        mat_obj = materials_dict.get(m_id)
        b_dict['id'] = b.get('batch_id', b_dict.get('id', ''))
        b_dict['product'] = prod_obj.get('product_name', p_id) if prod_obj else p_id
        b_dict['product_name'] = prod_obj.get('product_name', p_id) if prod_obj else p_id
        b_dict['product_code'] = prod_obj.get('product_code', '') if prod_obj else ''
        b_dict['material'] = mat_obj.get('material_name', m_id) if mat_obj else m_id
        b_dict['material_name'] = mat_obj.get('material_name', m_id) if mat_obj else m_id
        recent_batches.append(b_dict)

    # 5. Compliance calculation
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

    # 6. Alerts calculation
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

    # 7. Network Security Summary
    sec_summary = get_security_monitor_summary()
    recent_scans_docs = db.collection(Config.COLLECTION_NETWORK_SCANS)\
                          .order_by('scan_date', direction='DESCENDING')\
                          .limit(5)\
                          .get()
    recent_scans = [serialize_value(s.to_dict()) for s in recent_scans_docs if s.to_dict()]

    # 8. Recent Activity Logs
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
        "total_units_produced": total_units_produced,
        "total_units_manufactured": total_units_produced,
        "total_material_quantity": total_material_quantity,
        "completed_units": completed_units,
        "pending_qa_units": pending_qa_units,
        "batch_status_distribution": dict(batch_status_counts),
        "recent_batches": recent_batches,
        "monthly_throughput": monthly_throughput,
        "active_devices": sec_summary.get('active_devices', 0),
        "network_status": sec_summary.get('network_status', 'Secure'),
        "threat_level": sec_summary.get('threat_level', 'Low'),
        "recent_scans": recent_scans,
        "recent_activity": recent_activity
    }
