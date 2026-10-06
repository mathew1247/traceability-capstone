from datetime import datetime, timezone
from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from services.activity_log_service import log_activity
from utils.validators import validate_required_fields, validate_product_status

def get_all_products():
    docs = db.collection(Config.COLLECTION_PRODUCTS).get()
    return [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]


def get_product_by_id(product_id):
    doc = db.collection(Config.COLLECTION_PRODUCTS).document(product_id).get()
    if doc.exists:
        return serialize_value(doc.to_dict())
    return None


def create_product(data, current_user):
    missing = validate_required_fields(data, ['product_name', 'product_code', 'description'])
    if missing:
        return None, f"Missing required fields: {', '.join(missing)}", 400

    product_code = data['product_code'].strip().upper()

    # Requirement 12: Product code must be unique
    existing_code = db.collection(Config.COLLECTION_PRODUCTS).where('product_code', '==', product_code).get()
    for _ in existing_code:
        return None, f"A product with code '{product_code}' already exists.", 409

    status = data.get('status', 'In Production')
    if not validate_product_status(status):
        return None, f"Invalid product status '{status}'. Valid: 'In Production', 'Certified', 'Quarantined'.", 400

    existing_count = len(get_all_products())
    product_id = f"PRD{101 + existing_count}"

    now_iso = datetime.now(timezone.utc).isoformat()
    product_record = {
        "product_id": product_id,
        "product_name": data['product_name'].strip(),
        "product_code": product_code,
        "description": data['description'].strip(),
        "status": status,
        "created_at": now_iso
    }

    db.collection(Config.COLLECTION_PRODUCTS).document(product_id).set(product_record)

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='CREATE',
        resource='Product',
        resource_id=product_id,
        details=f"Created product {product_record['product_name']} ({product_code})"
    )

    return product_record, None, 201


def update_product(product_id, data, current_user):
    doc_ref = db.collection(Config.COLLECTION_PRODUCTS).document(product_id)
    doc = doc_ref.get()
    if not doc.exists:
        return None, "Product not found", 404

    existing_data = doc.to_dict()
    updates = {}

    if 'product_name' in data and data['product_name']:
        updates['product_name'] = data['product_name'].strip()
    if 'product_code' in data and data['product_code']:
        new_code = data['product_code'].strip().upper()
        if new_code != existing_data.get('product_code'):
            code_matches = db.collection(Config.COLLECTION_PRODUCTS).where('product_code', '==', new_code).get()
            for _ in code_matches:
                return None, f"Product code '{new_code}' already in use.", 409
            updates['product_code'] = new_code
    if 'description' in data and data['description']:
        updates['description'] = data['description'].strip()
    if 'status' in data and data['status']:
        if not validate_product_status(data['status']):
            return None, "Invalid product status", 400
        updates['status'] = data['status']

    if not updates:
        return None, "No valid update fields provided", 400

    doc_ref.update(updates)
    updated = doc_ref.get().to_dict()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='Product',
        resource_id=product_id,
        details=f"Updated product {product_id}"
    )

    return updated, None, 200


def delete_product(product_id, current_user):
    doc_ref = db.collection(Config.COLLECTION_PRODUCTS).document(product_id)
    doc = doc_ref.get()
    if not doc.exists:
        return False, "Product not found", 404

    # Check for dependent batches or compliance records
    batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('product_id', '==', product_id).get()
    if len(batches) > 0:
        return False, f"Cannot delete product {product_id}: Linked production batches exist.", 409

    doc_ref.delete()

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='DELETE',
        resource='Product',
        resource_id=product_id,
        details=f"Deleted product {product_id}"
    )

    return True, None, 200
