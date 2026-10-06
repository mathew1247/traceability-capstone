import uuid
from datetime import datetime, timezone
from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from services.activity_log_service import log_activity
from utils.validators import validate_email, validate_required_fields

def get_all_suppliers():
    docs = db.collection(Config.COLLECTION_SUPPLIERS).get()
    return [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]


def get_supplier_by_id(supplier_id):
    doc = db.collection(Config.COLLECTION_SUPPLIERS).document(supplier_id).get()
    if doc.exists:
        return serialize_value(doc.to_dict())
    return None


def create_supplier(data, current_user):
    missing = validate_required_fields(data, ['supplier_name', 'contact', 'email', 'address'])
    if missing:
        return None, f"Missing required fields: {', '.join(missing)}", 400

    if not validate_email(data['email']):
        return None, "Invalid supplier email address format.", 400

    # Generate sequential or readable ID
    existing_count = len(get_all_suppliers())
    supplier_id = f"SUP{101 + existing_count}"

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
        return None, "Supplier not found", 404

    updates = {}
    if 'supplier_name' in data and data['supplier_name']:
        updates['supplier_name'] = data['supplier_name'].strip()
    if 'contact' in data and data['contact']:
        updates['contact'] = data['contact'].strip()
    if 'email' in data and data['email']:
        if not validate_email(data['email']):
            return None, "Invalid email format", 400
        updates['email'] = data['email'].strip().lower()
    if 'address' in data and data['address']:
        updates['address'] = data['address'].strip()
    if 'status' in data and data['status']:
        updates['status'] = data['status'].strip()

    if not updates:
        return None, "No valid update fields provided", 400

    doc_ref.update(updates)
    updated = doc_ref.get().to_dict()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='Supplier',
        resource_id=supplier_id,
        details=f"Updated supplier {supplier_id}"
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
