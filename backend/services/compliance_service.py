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
    return None


def create_compliance_record(data, current_user):
    missing = validate_required_fields(data, ['product_id', 'standard', 'status', 'expiry_date'])
    if missing:
        return None, f"Missing required fields: {', '.join(missing)}", 400

    product_id = data['product_id'].strip()
    prod_doc = db.collection(Config.COLLECTION_PRODUCTS).document(product_id).get()
    if not prod_doc.exists:
        return None, f"Product '{product_id}' does not exist.", 404

    standard = data['standard'].strip()
    if not validate_compliance_standard(standard):
        return None, f"Invalid compliance standard '{standard}'. Valid: 'ISO 9001:2015', 'RoHS', 'GMP'.", 400

    status = data['status'].strip()
    if not validate_compliance_status(status):
        return None, f"Invalid compliance status '{status}'. Valid: 'Compliant', 'Review Required', 'Non-Compliant'.", 400

    audited_by = data.get('audited_by') or current_user.get('user_id')
    user_doc = db.collection(Config.COLLECTION_USERS).document(audited_by).get()
    if not user_doc.exists:
        return None, f"Auditor user '{audited_by}' does not exist.", 404

    existing_count = len(get_all_compliance())
    compliance_id = f"CMP{401 + existing_count}"

    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "compliance_id": compliance_id,
        "product_id": product_id,
        "standard": standard,
        "status": status,
        "remarks": data.get('remarks', '').strip(),
        "audited_by": audited_by,
        "expiry_date": data['expiry_date'].strip(),
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
    if not doc.exists:
        return None, "Compliance record not found", 404

    updates = {}
    if 'product_id' in data and data['product_id']:
        p_id = data['product_id'].strip()
        if not db.collection(Config.COLLECTION_PRODUCTS).document(p_id).get().exists:
            return None, f"Product '{p_id}' does not exist", 404
        updates['product_id'] = p_id

    if 'standard' in data and data['standard']:
        if not validate_compliance_standard(data['standard']):
            return None, "Invalid compliance standard", 400
        updates['standard'] = data['standard'].strip()

    if 'status' in data and data['status']:
        if not validate_compliance_status(data['status']):
            return None, "Invalid compliance status", 400
        updates['status'] = data['status'].strip()

    if 'remarks' in data:
        updates['remarks'] = data['remarks'].strip()

    if 'expiry_date' in data and data['expiry_date']:
        updates['expiry_date'] = data['expiry_date'].strip()

    if not updates:
        return None, "No valid update fields provided", 400

    doc_ref.update(updates)
    updated = doc_ref.get().to_dict()

    # Re-evaluate compliance alerts on update
    check_and_trigger_compliance_alert(updated)

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='ComplianceRecord',
        resource_id=compliance_id,
        details=f"Updated compliance record {compliance_id}"
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
