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

def parse_date_to_utc_date(date_val):
    """
    Parses a string, date, or datetime into a date object.
    Supports YYYY-MM-DD or ISO 8601 strings.
    Returns (date_obj, is_valid)
    """
    if date_val is None:
        return None, False
    if isinstance(date_val, datetime):
        return date_val.date(), True
    if hasattr(date_val, 'year') and hasattr(date_val, 'month') and hasattr(date_val, 'day') and not hasattr(date_val, 'hour'):
        return date_val, True

    val_str = str(date_val).strip()
    if not val_str:
        return None, False

    try:
        if 'T' in val_str:
            clean_str = val_str.replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean_str)
            return dt.date(), True
        else:
            dt = datetime.strptime(val_str, '%Y-%m-%d')
            return dt.date(), True
    except (ValueError, TypeError):
        return None, False


def evaluate_compliance_expiry(compliance_record, warning_days=None, reference_date=None):
    """
    Phase 2 Task 4: Compliance Expiry Monitoring Status Evaluator.
    Evaluates compliance certification expiration using calendar-date based comparison.

    Cases evaluated:
    1. Expired: Expiry date was in the past (days_left < 0) or stored status == 'Expired'.
    2. Expiring Today: Expiry date is today (days_left == 0).
    3. Expiring Soon: Expiry date is within the configured warning period (0 < days_left <= warning_days).
    4. Valid: Expiry date is beyond the warning period (days_left > warning_days).
    5. Missing Date: No expiry date provided (None or empty).
    6. Invalid Date: Expiry date cannot be parsed as a valid calendar date.

    Missing or invalid dates are NEVER silently treated as valid.
    """
    if warning_days is None:
        warning_days = getattr(Config, 'COMPLIANCE_WARNING_DAYS', 30)
    try:
        warning_days = int(warning_days)
    except (ValueError, TypeError):
        warning_days = 30
    if warning_days < 0:
        warning_days = 30

    if reference_date is None:
        ref_date = datetime.now(timezone.utc).date()
    else:
        ref_parsed, _ = parse_date_to_utc_date(reference_date)
        ref_date = ref_parsed if ref_parsed else datetime.now(timezone.utc).date()

    stored_status = str(compliance_record.get('status', '')).strip()
    raw_expiry = compliance_record.get('expiry_date')

    # Case 5: Missing expiry date
    if raw_expiry is None or (isinstance(raw_expiry, str) and not raw_expiry.strip()):
        is_expired = (stored_status == 'Expired')
        return {
            "status": "expired" if is_expired else "missing_date",
            "label": "Expired" if is_expired else "Missing Expiry Date",
            "days_remaining": None,
            "is_expired": is_expired,
            "is_expiring_soon": False,
            "is_valid": False,
            "severity": "Critical" if is_expired else "Warning",
            "warning_days": warning_days,
            "reference_date": ref_date.isoformat(),
            "parsed_expiry_date": None,
            "raw_expiry_date": raw_expiry,
            "requires_attention": True
        }

    exp_date, is_valid_date = parse_date_to_utc_date(raw_expiry)

    # Case 6: Invalid expiry date format
    if not is_valid_date or exp_date is None:
        is_expired = (stored_status == 'Expired')
        return {
            "status": "expired" if is_expired else "invalid_date",
            "label": "Expired" if is_expired else "Invalid Expiry Date",
            "days_remaining": None,
            "is_expired": is_expired,
            "is_expiring_soon": False,
            "is_valid": False,
            "severity": "Critical" if is_expired else "Warning",
            "warning_days": warning_days,
            "reference_date": ref_date.isoformat(),
            "parsed_expiry_date": None,
            "raw_expiry_date": str(raw_expiry),
            "requires_attention": True
        }

    # Date-based calendar comparison
    days_left = (exp_date - ref_date).days

    # Case 1: Already expired
    if days_left < 0 or stored_status == 'Expired':
        return {
            "status": "expired",
            "label": "Expired",
            "days_remaining": days_left,
            "is_expired": True,
            "is_expiring_soon": False,
            "is_valid": False,
            "severity": "Critical",
            "warning_days": warning_days,
            "reference_date": ref_date.isoformat(),
            "parsed_expiry_date": exp_date.isoformat(),
            "raw_expiry_date": str(raw_expiry),
            "requires_attention": True
        }

    # Case 2: Expires today
    if days_left == 0:
        return {
            "status": "expiring_today",
            "label": "Expires Today",
            "days_remaining": 0,
            "is_expired": False,
            "is_expiring_soon": True,
            "is_valid": True,
            "severity": "Critical",
            "warning_days": warning_days,
            "reference_date": ref_date.isoformat(),
            "parsed_expiry_date": exp_date.isoformat(),
            "raw_expiry_date": str(raw_expiry),
            "requires_attention": True
        }

    # Case 3: Expires within warning period
    if 0 < days_left <= warning_days:
        return {
            "status": "expiring_soon",
            "label": "Expiring Soon",
            "days_remaining": days_left,
            "is_expired": False,
            "is_expiring_soon": True,
            "is_valid": True,
            "severity": "Warning",
            "warning_days": warning_days,
            "reference_date": ref_date.isoformat(),
            "parsed_expiry_date": exp_date.isoformat(),
            "raw_expiry_date": str(raw_expiry),
            "requires_attention": True
        }

    # Case 4: Valid beyond warning period
    return {
        "status": "valid",
        "label": "Valid",
        "days_remaining": days_left,
        "is_expired": False,
        "is_expiring_soon": False,
        "is_valid": True,
        "severity": "Normal",
        "warning_days": warning_days,
        "reference_date": ref_date.isoformat(),
        "parsed_expiry_date": exp_date.isoformat(),
        "raw_expiry_date": str(raw_expiry),
        "requires_attention": False
    }


def enrich_compliance_with_expiry(compliance_record, warning_days=None, reference_date=None):
    """
    Enriches a compliance dictionary with derived expiry fields without mutating Firestore.
    """
    rec = dict(compliance_record)
    eval_res = evaluate_compliance_expiry(rec, warning_days=warning_days, reference_date=reference_date)
    rec['expiry_status'] = eval_res['status']
    rec['expiry_status_label'] = eval_res['label']
    rec['days_remaining'] = eval_res['days_remaining']
    rec['is_expired'] = eval_res['is_expired']
    rec['is_expiring_soon'] = eval_res['is_expiring_soon']
    rec['is_valid'] = eval_res['is_valid']
    rec['expiry_severity'] = eval_res['severity']
    rec['requires_attention'] = eval_res['requires_attention']
    rec['expiry_evaluation'] = eval_res
    return rec


def check_and_trigger_compliance_alert(compliance_record, reference_date=None, warning_days=None):
    """
    Requirement 16 / Phase 2 Task 4:
    Inspects compliance certification expiry date using calendar-date comparison.
    Triggers Warning alert if expiring within warning_days (default 30),
    or Critical alert if expiring today or already expired.
    """
    eval_res = evaluate_compliance_expiry(compliance_record, warning_days=warning_days, reference_date=reference_date)
    product_id = compliance_record.get('product_id', '')
    standard = compliance_record.get('standard', '')
    record_id = compliance_record.get('compliance_id', '')
    days_left = eval_res['days_remaining']
    status = eval_res['status']

    if status == 'expired':
        days_ago = abs(days_left) if (days_left is not None and days_left < 0) else 0
        return create_alert(
            severity="Critical",
            source="Compliance",
            message=f"Compliance certification for {standard} on Product {product_id} expired {days_ago} days ago.",
            resource_id=record_id
        )
    elif status == 'expiring_today':
        return create_alert(
            severity="Critical",
            source="Compliance",
            message=f"Compliance certification for {standard} on Product {product_id} expires today ({eval_res['parsed_expiry_date']}).",
            resource_id=record_id
        )
    elif status == 'expiring_soon':
        return create_alert(
            severity="Warning",
            source="Compliance",
            message=f"Compliance certification for {standard} on Product {product_id} expires in {days_left} days.",
            resource_id=record_id
        )
    elif status in ('missing_date', 'invalid_date'):
        return create_alert(
            severity="Warning",
            source="Compliance",
            message=f"Compliance certification for {standard} on Product {product_id} has invalid or missing expiry date.",
            resource_id=record_id
        )
    return None


def get_compliance_expiry_status(warning_days=None, reference_date=None, status_filter=None, standard_filter=None, product_id_filter=None):
    """
    Computes overall compliance expiry monitoring metrics and returns filtered records.
    """
    if warning_days is None:
        warning_days = getattr(Config, 'COMPLIANCE_WARNING_DAYS', 30)
    try:
        warning_days = int(warning_days)
    except (ValueError, TypeError):
        warning_days = 30
    if warning_days < 0:
        warning_days = 30

    if reference_date is None:
        ref_date = datetime.now(timezone.utc).date()
    else:
        ref_parsed, _ = parse_date_to_utc_date(reference_date)
        ref_date = ref_parsed if ref_parsed else datetime.now(timezone.utc).date()

    docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).get()
    all_raw = [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]

    enriched = [enrich_compliance_with_expiry(r, warning_days=warning_days, reference_date=ref_date) for r in all_raw]

    # Summary metrics
    total_count = len(enriched)
    valid_count = sum(1 for r in enriched if r['expiry_status'] == 'valid')
    expiring_soon_count = sum(1 for r in enriched if r['expiry_status'] == 'expiring_soon')
    expiring_today_count = sum(1 for r in enriched if r['expiry_status'] == 'expiring_today')
    expired_count = sum(1 for r in enriched if r['expiry_status'] == 'expired')
    missing_date_count = sum(1 for r in enriched if r['expiry_status'] == 'missing_date')
    invalid_date_count = sum(1 for r in enriched if r['expiry_status'] == 'invalid_date')
    attention_required_count = sum(1 for r in enriched if r['requires_attention'])

    summary = {
        "total_records": total_count,
        "valid_count": valid_count,
        "expiring_soon_count": expiring_soon_count,
        "expiring_today_count": expiring_today_count,
        "expired_count": expired_count,
        "missing_date_count": missing_date_count,
        "invalid_date_count": invalid_date_count,
        "attention_required_count": attention_required_count,
        "warning_days": warning_days,
        "reference_date": ref_date.isoformat()
    }

    # Filtering
    filtered = enriched
    if status_filter:
        s_filter = str(status_filter).strip().lower()
        if s_filter in ('expiring', 'expiring_all'):
            filtered = [r for r in filtered if r['expiry_status'] in ('expiring_soon', 'expiring_today')]
        elif s_filter in ('attention', 'requires_attention'):
            filtered = [r for r in filtered if r['requires_attention']]
        else:
            filtered = [r for r in filtered if r['expiry_status'].lower() == s_filter]

    if standard_filter:
        std_val = str(standard_filter).strip().lower()
        filtered = [r for r in filtered if str(r.get('standard', '')).strip().lower() == std_val]

    if product_id_filter:
        prod_val = str(product_id_filter).strip().lower()
        filtered = [r for r in filtered if str(r.get('product_id', '')).strip().lower() == prod_val]

    return {
        "summary": summary,
        "records": filtered,
        "warning_days": warning_days,
        "reference_date": ref_date.isoformat()
    }


def scan_and_alert_compliance_expiries(warning_days=None, reference_date=None, current_user=None):
    """
    Scans all compliance records and triggers alerts for any expired, expiring, or invalid records.
    Does not duplicate existing active alerts.
    """
    result = get_compliance_expiry_status(warning_days=warning_days, reference_date=reference_date)
    records = result['records']
    alerts_triggered = 0

    for r in records:
        if r['requires_attention']:
            alert = check_and_trigger_compliance_alert(r, reference_date=reference_date, warning_days=warning_days)
            if alert:
                alerts_triggered += 1

    if current_user:
        log_activity(
            user_id=current_user.get('user_id'),
            username=current_user.get('username'),
            action='SCAN',
            resource='ComplianceExpiry',
            resource_id='ALL',
            details=f"Compliance expiry scan triggered: {result['summary']['expired_count']} expired, {result['summary']['expiring_soon_count']} expiring soon"
        )

    return {
        "summary": result['summary'],
        "alerts_triggered": alerts_triggered
    }


def get_all_compliance(expiry_status=None, warning_days=None, reference_date=None):
    docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).get()
    records = [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]
    enriched = [enrich_compliance_with_expiry(r, warning_days=warning_days, reference_date=reference_date) for r in records]
    if expiry_status:
        st_clean = str(expiry_status).strip().lower()
        if st_clean in ('expiring', 'expiring_all'):
            enriched = [r for r in enriched if r['expiry_status'] in ('expiring_soon', 'expiring_today')]
        elif st_clean in ('attention', 'requires_attention'):
            enriched = [r for r in enriched if r['requires_attention']]
        else:
            enriched = [r for r in enriched if r['expiry_status'].lower() == st_clean]
    return enriched


def get_compliance_by_id(compliance_id, warning_days=None, reference_date=None):
    doc = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).document(compliance_id).get()
    if doc.exists:
        return enrich_compliance_with_expiry(serialize_value(doc.to_dict()), warning_days=warning_days, reference_date=reference_date)
    matched = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('compliance_id', '==', compliance_id).get()
    for d in matched:
        if d.exists or d.to_dict():
            return enrich_compliance_with_expiry(serialize_value(d.to_dict()), warning_days=warning_days, reference_date=reference_date)
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
