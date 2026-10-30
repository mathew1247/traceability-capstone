from datetime import datetime, timezone
from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from services.activity_log_service import log_activity
from utils.validators import validate_required_fields, validate_product_status
from utils.pagination import paginate_records

def get_all_products(page=1, page_size=10, sort_by='created_at', sort_order='desc', search=None, status=None, is_paginated=False):
    col = db.collection(Config.COLLECTION_PRODUCTS)
    if status:
        docs = col.where('status', '==', status).get()
    else:
        docs = col.get()

    items = [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]

    if search:
        s = search.lower()
        items = [
            p for p in items
            if s in (p.get('product_name') or '').lower() or
               s in (p.get('product_code') or '').lower() or
               s in (p.get('product_id') or '').lower() or
               s in (p.get('description') or '').lower()
        ]

    return paginate_records(
        items=items,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        tie_breaker_field='product_id',
        is_paginated=is_paginated
    )


def get_product_by_id(product_id):
    doc = db.collection(Config.COLLECTION_PRODUCTS).document(product_id).get()
    if doc.exists:
        return serialize_value(doc.to_dict())
    matched = db.collection(Config.COLLECTION_PRODUCTS).where('product_id', '==', product_id).get()
    for d in matched:
        if d.exists or d.to_dict():
            return serialize_value(d.to_dict())
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

    from services.id_service import allocate_sequential_id
    product_id = allocate_sequential_id('products')

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
        matched = db.collection(Config.COLLECTION_PRODUCTS).where('product_id', '==', product_id).get()
        for d in matched:
            doc_ref = d.reference
            doc = d
            break
    if not doc.exists:
        return None, "Product not found", 404

    existing_data = doc.to_dict()
    updates = {}

    if 'product_name' in data:
        name_val = str(data['product_name']).strip() if data['product_name'] is not None else ""
        if not name_val:
            return None, "Product name cannot be empty", 400
        updates['product_name'] = name_val

    if 'product_code' in data:
        code_val = str(data['product_code']).strip().upper() if data['product_code'] is not None else ""
        if not code_val:
            return None, "Product code cannot be empty", 400
        if code_val != existing_data.get('product_code'):
            code_matches = db.collection(Config.COLLECTION_PRODUCTS).where('product_code', '==', code_val).get()
            for m in code_matches:
                m_data = m.to_dict()
                if m_data and m_data.get('product_id') != product_id and m.id != product_id:
                    return None, f"Product code '{code_val}' already in use.", 409
            updates['product_code'] = code_val

    if 'description' in data:
        updates['description'] = str(data['description']).strip() if data['description'] is not None else ""

    if 'status' in data:
        st_val = str(data['status']).strip() if data['status'] is not None else ""
        if not validate_product_status(st_val):
            return None, f"Invalid product status '{st_val}'.", 400
        updates['status'] = st_val

    if not updates:
        return None, "No valid update fields provided", 400

    doc_ref.update(updates)
    updated = serialize_value(doc_ref.get().to_dict())

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='Product',
        resource_id=product_id,
        details=f"Updated product {product_id} fields: {list(updates.keys())}"
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

    comp_records = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', product_id).get()
    if len(comp_records) > 0:
        return False, f"Cannot delete product {product_id}: Linked compliance certification dossiers exist.", 409

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
