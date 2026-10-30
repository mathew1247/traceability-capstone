from datetime import datetime, timezone, timedelta
from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from services.activity_log_service import log_activity
from services.alert_service import create_alert
from utils.validators import (
    validate_required_fields,
    validate_compliance_standard,
    validate_compliance_status
)

def check_and_trigger_compliance_alert(compliance_record):
    """
    Requirement 16:
    Inspects compliance certification expiry date.
    Triggers Warning alert if expiring within 30 days, or Critical alert if already expired.
    """
    expiry_str = compliance_record.get('expiry_date')
    if not expiry_str:
        return

    try:
        # Support YYYY-MM-DD or ISO formats
        if 'T' in expiry_str:
            expiry_dt = datetime.fromisoformat(expiry_str)
        else:
            expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d')
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        days_left = (expiry_dt - now).days

        product_id = compliance_record.get('product_id', '')
        standard = compliance_record.get('standard', '')
        record_id = compliance_record.get('compliance_id', '')

        if days_left < 0 or compliance_record.get('status') == 'Expired':
            create_alert(
                severity="Critical",
                source="Compliance",
                message=f"Compliance certification for {standard} on Product {product_id} expired {abs(days_left) if days_left < 0 else 0} days ago.",
                resource_id=record_id
            )
        elif days_left <= 30:
            create_alert(
                severity="Warning",
                source="Compliance",
                message=f"Compliance certification for {standard} on Product {product_id} expires in {days_left} days.",
                resource_id=record_id
            )

    except Exception:
        pass


def get_all_compliance():
    docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).get()
    return [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]


def get_compliance_by_id(compliance_id):
    doc = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).document(compliance_id).get()
    if doc.exists:
        return serialize_value(doc.to_dict())
    matched = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('compliance_id', '==', compliance_id).get()
    for d in matched:
        if d.exists or d.to_dict():
            return serialize_value(d.to_dict())
    return None


def create_compliance_record(data, current_user):
    missing = validate_required_fields(data, ['product_id', 'standard', 'status', 'expiry_date'])
    if missing:
        return None, f"Missing required fields: {', '.join(missing)}", 400

    product_id = data['product_id'].strip()
    prod_doc = db.collection(Config.COLLECTION_PRODUCTS).document(product_id).get()
    if not prod_doc or not prod_doc.exists:
        matched = db.collection(Config.COLLECTION_PRODUCTS).where('product_id', '==', product_id).get()
        if not matched:
            matched = db.collection(Config.COLLECTION_PRODUCTS).where('product_code', '==', product_id).get()
        if not matched:
            return None, f"Product '{product_id}' does not exist.", 404
        for d in matched:
            prod_doc = d
            product_id = d.to_dict().get('product_id', product_id)
            break

    standard = data['standard'].strip()
    if not validate_compliance_standard(standard):
        return None, f"Invalid compliance standard '{standard}'. Valid: 'ISO 9001:2015', 'RoHS', 'GMP'.", 400

    status = data['status'].strip()
    if not validate_compliance_status(status):
        return None, f"Invalid compliance status '{status}'. Valid: 'Compliant', 'Review Required', 'Non-Compliant'.", 400

    expiry_date = data['expiry_date'].strip()
    try:
        if 'T' in expiry_date:
            datetime.fromisoformat(expiry_date)
        else:
            datetime.strptime(expiry_date, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None, f"Invalid expiry_date format '{expiry_date}'. Expected YYYY-MM-DD or ISO 8601.", 400

    # Distinguish external auditing authority (e.g. TUV Rheinland) from authenticated user
    raw_auditor = data.get('auditor') or data.get('auditing_body') or data.get('audited_by')
    auditing_body = (data.get('auditing_body') or data.get('auditor') or '').strip()
    audited_by = None

    audited_by_candidate = data.get('audited_by')
    if audited_by_candidate:
        cand_str = str(audited_by_candidate).strip()
        u_doc = db.collection(Config.COLLECTION_USERS).document(cand_str).get()
        if not u_doc or not u_doc.exists:
            matched = db.collection(Config.COLLECTION_USERS).where('user_id', '==', cand_str).get()
            for d in matched:
                u_doc = d
                break
        if u_doc and u_doc.exists:
            audited_by = u_doc.to_dict().get('user_id', cand_str)
        elif not auditing_body:
            auditing_body = cand_str

    if not audited_by:
        audited_by = current_user.get('user_id', '')

    if not auditing_body:
        if raw_auditor and raw_auditor != audited_by:
            auditing_body = str(raw_auditor).strip()
        else:
            auditing_body = "External Certification Agency"

    from services.id_service import allocate_sequential_id
    compliance_id = allocate_sequential_id('compliance')

    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "compliance_id": compliance_id,
        "product_id": product_id,
        "standard": standard,
        "status": status,
        "remarks": data.get('remarks', '').strip(),
        "audited_by": audited_by,
        "auditing_body": auditing_body,
        "created_by": current_user.get('user_id', ''),
        "expiry_date": expiry_date,
        "created_at": now_iso
    }

    db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).document(compliance_id).set(record)

    # Check for compliance expiry alert
    check_and_trigger_compliance_alert(record)

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='CREATE',
        resource='ComplianceRecord',
        resource_id=compliance_id,
        details=f"Created compliance audit record {compliance_id} for product {product_id} ({standard})"
    )

    return record, None, 201


def update_compliance_record(compliance_id, data, current_user):
    doc_ref = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).document(compliance_id)
    doc = doc_ref.get()
    if not doc or not doc.exists:
        matched = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('compliance_id', '==', compliance_id).get()
        for d in matched:
            doc_ref = d.reference
            doc = d
            break
    if not doc or not doc.exists:
        return None, "Compliance record not found", 404

    updates = {}
    if 'product_id' in data:
        p_id = str(data['product_id']).strip()
        if not p_id:
            return None, "Product reference cannot be empty", 400
        p_doc = db.collection(Config.COLLECTION_PRODUCTS).document(p_id).get()
        if not p_doc or not p_doc.exists:
            matched = db.collection(Config.COLLECTION_PRODUCTS).where('product_id', '==', p_id).get()
            if not matched:
                matched = db.collection(Config.COLLECTION_PRODUCTS).where('product_code', '==', p_id).get()
            if not matched:
                return None, f"Product '{p_id}' does not exist", 404
            for d in matched:
                p_id = d.to_dict().get('product_id', p_id)
                break
        updates['product_id'] = p_id

    if 'standard' in data:
        std_val = str(data['standard']).strip() if data['standard'] is not None else ""
        if not validate_compliance_standard(std_val):
            return None, f"Invalid compliance standard '{std_val}'. Valid: {', '.join(VALID_COMPLIANCE_STANDARDS)}", 400
        updates['standard'] = std_val

    if 'status' in data:
        st_val = str(data['status']).strip() if data['status'] is not None else ""
        if not validate_compliance_status(st_val):
            return None, f"Invalid compliance status '{st_val}'. Valid: {', '.join(VALID_COMPLIANCE_STATUSES)}", 400
        updates['status'] = st_val

    if 'remarks' in data:
        updates['remarks'] = str(data['remarks']).strip() if data['remarks'] is not None else ""

    if 'expiry_date' in data:
        exp_str = str(data['expiry_date']).strip() if data['expiry_date'] is not None else ""
        if not exp_str:
            return None, "Expiry date cannot be empty", 400
        try:
            if 'T' in exp_str:
                datetime.fromisoformat(exp_str)
            else:
                datetime.strptime(exp_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            return None, f"Invalid expiry_date format '{exp_str}'. Expected YYYY-MM-DD or ISO 8601.", 400
        updates['expiry_date'] = exp_str

    if 'auditing_body' in data or 'auditor' in data:
        body_val = str(data.get('auditing_body') or data.get('auditor') or '').strip()
        if body_val:
            updates['auditing_body'] = body_val

    if 'audited_by' in data and data['audited_by']:
        aud_cand = str(data['audited_by']).strip()
        u_doc = db.collection(Config.COLLECTION_USERS).document(aud_cand).get()
        if not u_doc or not u_doc.exists:
            matched = db.collection(Config.COLLECTION_USERS).where('user_id', '==', aud_cand).get()
            for d in matched:
                u_doc = d
                break
        if u_doc and u_doc.exists:
            updates['audited_by'] = u_doc.to_dict().get('user_id', aud_cand)
        elif 'auditing_body' not in updates:
            updates['auditing_body'] = aud_cand

    if not updates:
        return None, "No valid update fields provided", 400

    doc_ref.update(updates)
    updated = serialize_value(doc_ref.get().to_dict())

    # Re-evaluate compliance alerts on update
    check_and_trigger_compliance_alert(updated)

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='ComplianceRecord',
        resource_id=compliance_id,
        details=f"Updated compliance record {compliance_id} fields: {list(updates.keys())}"
    )

    return updated, None, 200


def delete_compliance_record(compliance_id, current_user):
    doc_ref = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).document(compliance_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False, "Compliance record not found", 404

    doc_ref.delete()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='DELETE',
        resource='ComplianceRecord',
        resource_id=compliance_id,
        details=f"Deleted compliance record {compliance_id}"
    )

    return True, None, 200
