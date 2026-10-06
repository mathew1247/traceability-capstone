from datetime import datetime, timezone
from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from services.activity_log_service import log_activity
from utils.validators import validate_required_fields

def get_all_materials():
    docs = db.collection(Config.COLLECTION_RAW_MATERIALS).get()
    return [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]


def get_material_by_id(material_id):
    doc = db.collection(Config.COLLECTION_RAW_MATERIALS).document(material_id).get()
    if doc.exists:
        return serialize_value(doc.to_dict())
    return None


def create_material(data, current_user):
    missing = validate_required_fields(data, ['material_name', 'supplier_id', 'quantity', 'unit'])
    if missing:
        return None, f"Missing required fields: {', '.join(missing)}", 400

    supplier_id = data['supplier_id'].strip()
    
    # Requirement 11: Verify supplier_id exists
    supplier_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(supplier_id).get()
    if not supplier_doc.exists:
        return None, f"Supplier with ID '{supplier_id}' does not exist.", 404

    existing_count = len(get_all_materials())
    material_id = f"RM{301 + existing_count}"

    try:
        qty = float(data['quantity'])
    except (ValueError, TypeError):
        return None, "Quantity must be a valid number.", 400

    now_iso = datetime.now(timezone.utc).isoformat()
    material_record = {
        "material_id": material_id,
        "material_name": data['material_name'].strip(),
        "supplier_id": supplier_id,
        "quantity": qty,
        "unit": data['unit'].strip(),
        "created_at": now_iso
    }

    db.collection(Config.COLLECTION_RAW_MATERIALS).document(material_id).set(material_record)

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='CREATE',
        resource='RawMaterial',
        resource_id=material_id,
        details=f"Created raw material {material_record['material_name']} ({qty} {material_record['unit']})"
    )

    return material_record, None, 201


def update_material(material_id, data, current_user):
    doc_ref = db.collection(Config.COLLECTION_RAW_MATERIALS).document(material_id)
    doc = doc_ref.get()
    if not doc.exists:
        return None, "Raw material not found", 404

    updates = {}
    if 'material_name' in data and data['material_name']:
        updates['material_name'] = data['material_name'].strip()
    if 'supplier_id' in data and data['supplier_id']:
        supplier_id = data['supplier_id'].strip()
        sup_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(supplier_id).get()
        if not sup_doc.exists:
            return None, f"Supplier '{supplier_id}' does not exist", 404
        updates['supplier_id'] = supplier_id
    if 'quantity' in data:
        try:
            updates['quantity'] = float(data['quantity'])
        except (ValueError, TypeError):
            return None, "Quantity must be a valid number", 400
    if 'unit' in data and data['unit']:
        updates['unit'] = data['unit'].strip()

    if not updates:
        return None, "No valid update fields provided", 400

    doc_ref.update(updates)
    updated = doc_ref.get().to_dict()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='RawMaterial',
        resource_id=material_id,
        details=f"Updated raw material {material_id}"
    )

    return updated, None, 200


def delete_material(material_id, current_user):
    doc_ref = db.collection(Config.COLLECTION_RAW_MATERIALS).document(material_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False, "Raw material not found", 404

    # Check for dependent production batches
    batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('material_id', '==', material_id).get()
    if len(batches) > 0:
        return False, f"Cannot delete material {material_id}: Linked production batches exist.", 409

    doc_ref.delete()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='DELETE',
        resource='RawMaterial',
        resource_id=material_id,
        details=f"Deleted raw material {material_id}"
    )

    return True, None, 200
