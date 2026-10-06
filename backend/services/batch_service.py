from datetime import datetime, timezone
from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from services.activity_log_service import log_activity
from utils.validators import validate_required_fields, validate_batch_status

def get_all_batches():
    docs = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).get()
    return [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]


def get_batch_by_id(batch_id):
    doc = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(batch_id).get()
    if doc.exists:
        return serialize_value(doc.to_dict())
    return None


def create_batch(data, current_user):
    missing = validate_required_fields(data, ['product_id', 'material_id', 'quantity'])
    if missing:
        return None, f"Missing required fields: {', '.join(missing)}", 400

    product_id = data['product_id'].strip()
    material_id = data['material_id'].strip()

    # Requirement 13: Verify product_id exists
    prod_doc = db.collection(Config.COLLECTION_PRODUCTS).document(product_id).get()
    if not prod_doc.exists:
        return None, f"Product '{product_id}' does not exist.", 404

    # Requirement 13: Verify material_id exists
    mat_doc = db.collection(Config.COLLECTION_RAW_MATERIALS).document(material_id).get()
    if not mat_doc.exists:
        return None, f"Raw material '{material_id}' does not exist.", 404

    try:
        qty = int(data['quantity'])
    except (ValueError, TypeError):
        return None, "Quantity must be an integer.", 400

    status = data.get('status', 'Pending')
    if not validate_batch_status(status):
        return None, f"Invalid batch status '{status}'. Valid: 'Completed', 'In QA Inspection', 'Passed', 'Running', 'Pending'.", 400

    existing_count = len(get_all_batches())
    batch_id = f"BAT{201 + existing_count}"

    now_iso = datetime.now(timezone.utc).isoformat()
    prod_date = data.get('production_date') or now_iso.split('T')[0]

    batch_record = {
        "batch_id": batch_id,
        "product_id": product_id,
        "material_id": material_id,
        "quantity": qty,
        "production_date": prod_date,
        "status": status,
        "created_at": now_iso
    }

    db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(batch_id).set(batch_record)

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='CREATE',
        resource='ProductionBatch',
        resource_id=batch_id,
        details=f"Created production batch {batch_id} for product {product_id} with material {material_id}"
    )

    return batch_record, None, 201


def update_batch(batch_id, data, current_user):
    doc_ref = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(batch_id)
    doc = doc_ref.get()
    if not doc.exists:
        return None, "Production batch not found", 404

    updates = {}
    if 'product_id' in data and data['product_id']:
        p_id = data['product_id'].strip()
        if not db.collection(Config.COLLECTION_PRODUCTS).document(p_id).get().exists:
            return None, f"Product '{p_id}' does not exist", 404
        updates['product_id'] = p_id

    if 'material_id' in data and data['material_id']:
        m_id = data['material_id'].strip()
        if not db.collection(Config.COLLECTION_RAW_MATERIALS).document(m_id).get().exists:
            return None, f"Raw material '{m_id}' does not exist", 404
        updates['material_id'] = m_id

    if 'quantity' in data:
        try:
            updates['quantity'] = int(data['quantity'])
        except (ValueError, TypeError):
            return None, "Quantity must be an integer", 400

    if 'production_date' in data and data['production_date']:
        updates['production_date'] = data['production_date'].strip()

    if 'status' in data and data['status']:
        if not validate_batch_status(data['status']):
            return None, "Invalid batch status", 400
        updates['status'] = data['status']

    if not updates:
        return None, "No valid update fields provided", 400

    doc_ref.update(updates)
    updated = doc_ref.get().to_dict()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='ProductionBatch',
        resource_id=batch_id,
        details=f"Updated batch {batch_id} to status {updated.get('status')}"
    )

    return updated, None, 200


def delete_batch(batch_id, current_user):
    doc_ref = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(batch_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False, "Batch not found", 404

    doc_ref.delete()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='DELETE',
        resource='ProductionBatch',
        resource_id=batch_id,
        details=f"Deleted batch {batch_id}"
    )

    return True, None, 200
