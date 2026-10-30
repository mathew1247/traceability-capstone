import uuid
from datetime import datetime, timezone
from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from services.activity_log_service import log_activity
from utils.validators import validate_email, validate_required_fields
from utils.pagination import paginate_records

def get_all_suppliers(page=1, page_size=10, sort_by='created_at', sort_order='desc', search=None, status=None, is_paginated=False):
    col = db.collection(Config.COLLECTION_SUPPLIERS)
    if status:
        docs = col.where('status', '==', status).get()
    else:
        docs = col.get()

    items = [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]

    if search:
        s = search.lower()
        items = [
            sup for sup in items
            if s in (sup.get('supplier_name') or '').lower() or
               s in (sup.get('supplier_id') or '').lower() or
               s in (sup.get('contact') or '').lower() or
               s in (sup.get('email') or '').lower() or
               s in (sup.get('address') or '').lower() or
               s in (sup.get('status') or '').lower()
        ]

    return paginate_records(
        items=items,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        tie_breaker_field='supplier_id',
        is_paginated=is_paginated
    )


def get_supplier_by_id(supplier_id):
    doc = db.collection(Config.COLLECTION_SUPPLIERS).document(supplier_id).get()
    if doc.exists:
        return serialize_value(doc.to_dict())
    matched = db.collection(Config.COLLECTION_SUPPLIERS).where('supplier_id', '==', supplier_id).get()
    for d in matched:
        if d.exists or d.to_dict():
            return serialize_value(d.to_dict())
    return None


def create_supplier(data, current_user):
    missing = validate_required_fields(data, ['supplier_name', 'contact', 'email', 'address'])
    if missing:
        return None, f"Missing required fields: {', '.join(missing)}", 400

    if not validate_email(data['email']):
        return None, "Invalid supplier email address format.", 400

    # Generate sequential or readable ID via atomic transaction
    from services.id_service import allocate_sequential_id
    supplier_id = allocate_sequential_id('suppliers')

    now_iso = datetime.now(timezone.utc).isoformat()
    supplier_record = {
        "supplier_id": supplier_id,
        "supplier_name": data['supplier_name'].strip(),
        "contact": data['contact'].strip(),
        "email": data['email'].strip().lower(),
        "address": data['address'].strip(),
        "status": data.get('status', 'Active'),
        "created_at": now_iso
    }

    db.collection(Config.COLLECTION_SUPPLIERS).document(supplier_id).set(supplier_record)

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='CREATE',
        resource='Supplier',
        resource_id=supplier_id,
        details=f"Created supplier {supplier_record['supplier_name']}"
    )

    return supplier_record, None, 201


def update_supplier(supplier_id, data, current_user):
    doc_ref = db.collection(Config.COLLECTION_SUPPLIERS).document(supplier_id)
    doc = doc_ref.get()
    if not doc.exists:
        matched = db.collection(Config.COLLECTION_SUPPLIERS).where('supplier_id', '==', supplier_id).get()
        for d in matched:
            doc_ref = d.reference
            doc = d
            break
    if not doc.exists:
        return None, "Supplier not found", 404

    updates = {}
    if 'supplier_name' in data:
        name_val = str(data['supplier_name']).strip() if data['supplier_name'] is not None else ""
        if not name_val:
            return None, "Supplier name cannot be empty", 400
        updates['supplier_name'] = name_val

    if 'contact' in data:
        contact_val = str(data['contact']).strip() if data['contact'] is not None else ""
        if not contact_val:
            return None, "Contact person cannot be empty", 400
        updates['contact'] = contact_val

    if 'email' in data:
        email_val = str(data['email']).strip().lower() if data['email'] is not None else ""
        if not validate_email(email_val):
            return None, "Invalid email format", 400
        updates['email'] = email_val

    if 'address' in data:
        updates['address'] = str(data['address']).strip() if data['address'] is not None else ""

    if 'status' in data:
        updates['status'] = str(data['status']).strip() if data['status'] is not None else ""

    if not updates:
        return None, "No valid update fields provided", 400

    doc_ref.update(updates)
    updated = serialize_value(doc_ref.get().to_dict())

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='Supplier',
        resource_id=supplier_id,
        details=f"Updated supplier {supplier_id} fields: {list(updates.keys())}"
    )

    return updated, None, 200


def delete_supplier(supplier_id, current_user):
    doc_ref = db.collection(Config.COLLECTION_SUPPLIERS).document(supplier_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False, "Supplier not found", 404

    # Check for dependent raw materials
    materials = db.collection(Config.COLLECTION_RAW_MATERIALS).where('supplier_id', '==', supplier_id).get()
    if len(materials) > 0:
        return False, f"Cannot delete supplier {supplier_id}: Linked raw materials exist.", 409

    doc_ref.delete()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='DELETE',
        resource='Supplier',
        resource_id=supplier_id,
        details=f"Deleted supplier {supplier_id}"
    )

    return True, None, 200


def verify_supplier_documents(supplier_id, current_user):
    """
    Verifies actual compliance records, certifications, and inventory links
    for a given supplier against Firestore data.
    """
    supplier = get_supplier_by_id(supplier_id)
    if not supplier:
        return None, "Supplier not found", 404

    s_id = supplier.get('supplier_id') or supplier_id
    supplier_name = supplier.get('supplier_name', 'Unknown')
    supplier_status = supplier.get('status', 'Active')

    # Find raw materials linked to this supplier
    mat_docs = db.collection(Config.COLLECTION_RAW_MATERIALS).where('supplier_id', '==', s_id).get()
    materials = [d.to_dict() for d in mat_docs if d.to_dict()]
    material_ids = [m.get('material_id') for m in materials if m.get('material_id')]

    # Find batches and products associated with those materials
    product_ids = set()
    for m_id in material_ids:
        batch_docs = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('material_id', '==', m_id).get()
        for b in batch_docs:
            b_dict = b.to_dict()
            if b_dict and b_dict.get('product_id'):
                product_ids.add(b_dict['product_id'])

    # Find compliance records for those products
    compliance_records = []
    seen_comp = set()
    for p_id in product_ids:
        comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', p_id).get()
        for c in comp_docs:
            c_dict = c.to_dict()
            if c_dict and c_dict.get('compliance_id') and c_dict['compliance_id'] not in seen_comp:
                seen_comp.add(c_dict['compliance_id'])
                compliance_records.append(c_dict)

    # Also check any direct compliance records linked to supplier_id
    direct_comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('supplier_id', '==', s_id).get()
    for c in direct_comp_docs:
        c_dict = c.to_dict()
        if c_dict and c_dict.get('compliance_id') and c_dict['compliance_id'] not in seen_comp:
            seen_comp.add(c_dict['compliance_id'])
            compliance_records.append(c_dict)

    # Evaluate compliance records
    now = datetime.now(timezone.utc)
    valid_records = []
    flagged_records = []
    expiries = []

    for c in compliance_records:
        is_expired = False
        exp_str = c.get('expiry_date')
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str) if 'T' in exp_str else datetime.strptime(exp_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                expiries.append(exp_dt)
                if exp_dt < now:
                    is_expired = True
            except Exception:
                pass

        if c.get('status') == 'Expired' or is_expired:
            flagged_records.append({**c, "reason": "Certification expired"})
        elif c.get('status') == 'Review Required':
            flagged_records.append({**c, "reason": "Audit review required"})
        elif c.get('status') == 'Compliant':
            valid_records.append(c)
        else:
            flagged_records.append({**c, "reason": f"Status: {c.get('status')}"})

    earliest_valid_expiry = min(expiries).strftime('%Y-%m-%d') if expiries else "N/A"

    if supplier_status == 'Suspended':
        verified = False
        msg = f"Verification failed: Supplier '{supplier_name}' is SUSPENDED in vendor registry."
    elif supplier_status == 'Pending':
        verified = False
        msg = f"Verification pending: Supplier '{supplier_name}' onboarding documentation is awaiting review."
    elif not materials and not compliance_records:
        verified = False
        msg = f"No documentation or raw material inventory on file for supplier '{supplier_name}'."
    elif flagged_records:
        verified = False
        reasons = [f"{r.get('standard', 'Cert')} ({r.get('reason')})" for r in flagged_records]
        msg = f"Documentation audit flagged: {len(flagged_records)} certification issue(s) for '{supplier_name}': {'; '.join(reasons[:2])}."
    elif valid_records:
        verified = True
        standards = list(set(r.get('standard') for r in valid_records if r.get('standard')))
        msg = f"Verified: {len(valid_records)} compliance certification(s) ({', '.join(standards)}) valid through {earliest_valid_expiry}."
    else:
        verified = False
        msg = f"Supplier '{supplier_name}' has {len(materials)} material(s) on file, but no active compliance certifications."

    result = {
        "supplier_id": s_id,
        "supplier_name": supplier_name,
        "status": supplier_status,
        "verified": verified,
        "materials_count": len(materials),
        "materials": [m.get('material_name') for m in materials],
        "compliance_count": len(compliance_records),
        "valid_certifications_count": len(valid_records),
        "flagged_certifications_count": len(flagged_records),
        "earliest_expiry": earliest_valid_expiry,
        "message": msg
    }

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='VERIFY_DOCS',
        resource='Supplier',
        resource_id=s_id,
        details=f"Document verification for {supplier_name} ({s_id}): verified={verified}"
    )

    return result, None, 200
