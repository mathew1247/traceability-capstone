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
    matched = db.collection(Config.COLLECTION_RAW_MATERIALS).where('material_id', '==', material_id).get()
    for d in matched:
        if d.exists or d.to_dict():
            return serialize_value(d.to_dict())
    return None


def create_material(data, current_user):
    missing = validate_required_fields(data, ['material_name', 'supplier_id', 'quantity', 'unit'])
    if missing:
        return None, f"Missing required fields: {', '.join(missing)}", 400

    supplier_id = data['supplier_id'].strip()
    
    # Requirement 11: Verify supplier_id exists
    supplier_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(supplier_id).get()
    if not supplier_doc.exists:
        matched = db.collection(Config.COLLECTION_SUPPLIERS).where('supplier_id', '==', supplier_id).get()
        if not matched:
            return None, f"Supplier with ID '{supplier_id}' does not exist.", 404

    from services.id_service import allocate_sequential_id
    material_id = allocate_sequential_id('materials')

    try:
        qty = float(data['quantity'])
        if qty < 0:
            return None, "Quantity cannot be negative.", 400
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
        matched = db.collection(Config.COLLECTION_RAW_MATERIALS).where('material_id', '==', material_id).get()
        for d in matched:
            doc_ref = d.reference
            doc = d
            break
    if not doc.exists:
        return None, "Raw material not found", 404

    updates = {}
    if 'material_name' in data:
        name_val = str(data['material_name']).strip() if data['material_name'] is not None else ""
        if not name_val:
            return None, "Material name cannot be empty", 400
        updates['material_name'] = name_val

    if 'supplier_id' in data:
        supplier_id = str(data['supplier_id']).strip()
        if not supplier_id:
            return None, "Supplier reference cannot be empty", 400
        sup_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(supplier_id).get()
        if not sup_doc or not sup_doc.exists:
            matched_sup = db.collection(Config.COLLECTION_SUPPLIERS).where('supplier_id', '==', supplier_id).get()
            if not matched_sup:
                return None, f"Supplier '{supplier_id}' does not exist", 404
        updates['supplier_id'] = supplier_id

    if 'quantity' in data:
        try:
            qty = float(data['quantity'])
            if qty < 0:
                return None, "Quantity cannot be negative", 400
            updates['quantity'] = qty
        except (ValueError, TypeError):
            return None, "Quantity must be a valid number", 400

    if 'unit' in data:
        unit_val = str(data['unit']).strip() if data['unit'] is not None else ""
        if not unit_val:
            return None, "Unit cannot be empty", 400
        updates['unit'] = unit_val

    if not updates:
        return None, "No valid update fields provided", 400

    doc_ref.update(updates)
    updated = serialize_value(doc_ref.get().to_dict())

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='RawMaterial',
        resource_id=material_id,
        details=f"Updated raw material {material_id} fields: {list(updates.keys())}"
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
