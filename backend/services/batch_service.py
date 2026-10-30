import threading
from datetime import datetime, timezone
from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from services.activity_log_service import log_activity
from utils.validators import validate_required_fields, validate_batch_status, VALID_BATCH_STATUSES

_inventory_lock = threading.Lock()


class InventoryTransactionError(Exception):
    """Raised for business logic errors during inventory transactions."""
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _run_inventory_transaction(transaction_func):
    """
    Executes an atomic inventory operation across multiple documents.
    Uses Cloud Firestore's native multi-instance cross-process atomic transactions
    with optimistic concurrency control in live Firestore, or local transaction
    with thread locking in local mock mode.
    """
    is_local_mock = hasattr(db, '_persistence_file')
    if is_local_mock:
        with _inventory_lock:
            tx = db.transaction()
            result = transaction_func(tx)
            tx.commit()
            return result
    else:
        from google.cloud import firestore

        @firestore.transactional
        def _exec(transaction):
            return transaction_func(transaction)

        tx = db.transaction()
        return _exec(tx)


def _get_material_ref_and_doc(material_id):
    """Retrieves document reference and snapshot for raw material by ID or field query."""
    mat_ref = db.collection(Config.COLLECTION_RAW_MATERIALS).document(material_id)
    mat_doc = mat_ref.get()
    if not mat_doc.exists:
        matched = db.collection(Config.COLLECTION_RAW_MATERIALS).where('material_id', '==', material_id).get()
        for d in matched:
            return d.reference, d
    return mat_ref, mat_doc


from utils.pagination import paginate_records

def get_all_batches(page=1, page_size=10, sort_by='created_at', sort_order='desc', search=None, status=None, is_paginated=False):
    col = db.collection(Config.COLLECTION_PRODUCTION_BATCHES)
    if status:
        docs = col.where('status', '==', status).get()
    else:
        docs = col.get()

    items = [serialize_value(doc.to_dict()) for doc in docs if doc.to_dict()]

    if search:
        s = search.lower()
        items = [
            b for b in items
            if s in (b.get('batch_id') or '').lower() or
               s in (b.get('product_id') or '').lower() or
               s in (b.get('material_id') or '').lower() or
               s in (b.get('status') or '').lower() or
               s in str(b.get('quantity') or '')
        ]

    return paginate_records(
        items=items,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        tie_breaker_field='batch_id',
        is_paginated=is_paginated
    )


def get_batch_by_id(batch_id):
    doc = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(batch_id).get()
    if doc.exists:
        return serialize_value(doc.to_dict())
    matched = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('batch_id', '==', batch_id).get()
    for d in matched:
        if d.exists or d.to_dict():
            return serialize_value(d.to_dict())
    return None


def create_batch(data, current_user):
    missing = validate_required_fields(data, ['product_id', 'material_id', 'quantity'])
    if missing:
        return None, f"Missing required fields: {', '.join(missing)}", 400

    product_id = data['product_id'].strip()
    material_id = data['material_id'].strip()

    # Verify product_id exists
    prod_doc = db.collection(Config.COLLECTION_PRODUCTS).document(product_id).get()
    if not prod_doc.exists:
        matched_prod = db.collection(Config.COLLECTION_PRODUCTS).where('product_id', '==', product_id).get()
        if not matched_prod:
            return None, f"Product '{product_id}' does not exist.", 404

    # Validate quantity
    try:
        qty = int(data['quantity'])
        if qty <= 0:
            return None, "Quantity must be greater than 0.", 400
    except (ValueError, TypeError):
        return None, "Quantity must be an integer.", 400

    status = data.get('status', 'Pending')
    if not validate_batch_status(status):
        return None, f"Invalid batch status '{status}'. Valid: {', '.join(sorted(VALID_BATCH_STATUSES))}.", 400

    # Idempotency check: avoid double stock deductions on retry
    idempotency_key = data.get('idempotency_key')
    if idempotency_key:
        matched_existing = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('idempotency_key', '==', str(idempotency_key)).get()
        for eb in matched_existing:
            if eb.exists:
                return serialize_value(eb.to_dict()), None, 200

    mat_ref, mat_doc = _get_material_ref_and_doc(material_id)
    if not mat_doc or not mat_doc.exists:
        return None, f"Raw material '{material_id}' does not exist.", 404

    from services.id_service import allocate_sequential_id
    batch_id = allocate_sequential_id('batches')

    now_iso = datetime.now(timezone.utc).isoformat()
    prod_date = data.get('production_date') or now_iso.split('T')[0]
    req_unit = data.get('unit')
    batch_ref = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(batch_id)

    def _create_tx(tx):
        # Reads
        mat_snap = mat_ref.get(transaction=tx)
        if not mat_snap or not mat_snap.exists:
            raise InventoryTransactionError(f"Raw material '{material_id}' does not exist.", 404)

        mat_data = mat_snap.to_dict() or {}
        available_qty = float(mat_data.get('quantity', 0.0))
        mat_unit = mat_data.get('unit', '')

        # Validate unit compatibility if specified
        if req_unit and mat_unit and str(req_unit).strip().lower() != str(mat_unit).strip().lower():
            raise InventoryTransactionError(
                f"Unit mismatch: requested '{req_unit}', but raw material '{material_id}' is tracked in '{mat_unit}'.",
                400
            )

        # Enforce inventory limit
        if qty > available_qty:
            raise InventoryTransactionError(
                f"Insufficient inventory for raw material '{material_id}'. Available: {available_qty} {mat_unit}, requested: {qty}.",
                400
            )

        new_mat_qty = round(available_qty - qty, 4)

        batch_record = {
            "batch_id": batch_id,
            "product_id": product_id,
            "material_id": material_id,
            "quantity": qty,
            "unit": mat_unit or "units",
            "allocated_material_qty": qty,
            "production_date": prod_date,
            "status": status,
            "created_at": now_iso
        }
        if idempotency_key:
            batch_record["idempotency_key"] = str(idempotency_key)

        # Writes
        tx.update(mat_ref, {"quantity": new_mat_qty})
        tx.set(batch_ref, batch_record)
        return batch_record, new_mat_qty, mat_unit

    try:
        batch_record, new_mat_qty, mat_unit = _run_inventory_transaction(_create_tx)
    except InventoryTransactionError as ite:
        return None, ite.message, ite.status_code
    except Exception as e:
        return None, f"Failed to create batch: {str(e)}", 500

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='CREATE',
        resource='ProductionBatch',
        resource_id=batch_id,
        details=f"Created production batch {batch_id} for product {product_id}; deducted {qty} {mat_unit} from material {material_id} (remaining: {new_mat_qty})"
    )

    return batch_record, None, 201


def update_batch(batch_id, data, current_user):
    doc_ref = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(batch_id)
    doc = doc_ref.get()
    if not doc.exists:
        matched = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('batch_id', '==', batch_id).get()
        for d in matched:
            doc_ref = d.reference
            doc = d
            break
    if not doc.exists:
        return None, "Production batch not found", 404

    current_batch = doc.to_dict() or {}
    old_qty = int(current_batch.get('quantity', 0))
    old_mat_id = current_batch.get('material_id')

    updates = {}

    if 'product_id' in data:
        p_id = str(data['product_id']).strip()
        if not p_id:
            return None, "Product reference cannot be empty", 400
        p_doc = db.collection(Config.COLLECTION_PRODUCTS).document(p_id).get()
        if not p_doc or not p_doc.exists:
            matched_prod = db.collection(Config.COLLECTION_PRODUCTS).where('product_id', '==', p_id).get()
            if not matched_prod:
                return None, f"Product '{p_id}' does not exist", 404
        updates['product_id'] = p_id

    target_mat_id = old_mat_id
    target_qty = old_qty

    if 'quantity' in data:
        try:
            q_val = int(data['quantity'])
            if q_val <= 0:
                return None, "Quantity must be greater than 0", 400
            target_qty = q_val
        except (ValueError, TypeError):
            return None, "Quantity must be an integer", 400

    if 'material_id' in data:
        m_id = str(data['material_id']).strip()
        if not m_id:
            return None, "Material reference cannot be empty", 400
        target_mat_id = m_id

    if 'production_date' in data:
        updates['production_date'] = str(data['production_date']).strip() if data['production_date'] is not None else ""

    if 'status' in data:
        st_val = str(data['status']).strip() if data['status'] is not None else ""
        if not validate_batch_status(st_val):
            return None, f"Invalid batch status '{st_val}'. Valid: {', '.join(sorted(VALID_BATCH_STATUSES))}", 400
        updates['status'] = st_val

    mat_changed = target_mat_id != old_mat_id
    qty_changed = target_qty != old_qty

    if mat_changed:
        new_mat_ref, new_mat_doc = _get_material_ref_and_doc(target_mat_id)
        if not new_mat_doc or not new_mat_doc.exists:
            return None, f"Raw material '{target_mat_id}' does not exist", 404
        old_mat_ref, _ = _get_material_ref_and_doc(old_mat_id)
        updates['material_id'] = target_mat_id
        updates['quantity'] = target_qty
        updates['allocated_material_qty'] = target_qty
    elif qty_changed:
        mat_ref, _ = _get_material_ref_and_doc(old_mat_id)
        updates['quantity'] = target_qty
        updates['allocated_material_qty'] = target_qty

    if not updates:
        return None, "No valid update fields provided", 400

    def _update_tx(tx):
        # Reads
        b_snap = doc_ref.get(transaction=tx)
        if not b_snap.exists:
            raise InventoryTransactionError("Production batch not found", 404)

        if mat_changed:
            new_snap = new_mat_ref.get(transaction=tx)
            old_snap = old_mat_ref.get(transaction=tx)
            if not new_snap.exists:
                raise InventoryTransactionError(f"Raw material '{target_mat_id}' does not exist", 404)

            new_avail = float((new_snap.to_dict() or {}).get('quantity', 0.0))
            if target_qty > new_avail:
                raise InventoryTransactionError(
                    f"Insufficient inventory on new raw material '{target_mat_id}'. Available: {new_avail}, requested: {target_qty}.",
                    400
                )

            # Writes
            tx.update(new_mat_ref, {"quantity": round(new_avail - target_qty, 4)})
            if old_snap.exists:
                old_avail = float((old_snap.to_dict() or {}).get('quantity', 0.0))
                tx.update(old_mat_ref, {"quantity": round(old_avail + old_qty, 4)})

        elif qty_changed:
            mat_snap = mat_ref.get(transaction=tx)
            if mat_snap.exists:
                delta = target_qty - old_qty
                avail = float((mat_snap.to_dict() or {}).get('quantity', 0.0))
                if delta > 0:
                    if delta > avail:
                        raise InventoryTransactionError(
                            f"Insufficient inventory for raw material '{old_mat_id}'. Available: {avail}, additional needed: {delta}.",
                            400
                        )
                    tx.update(mat_ref, {"quantity": round(avail - delta, 4)})
                else:
                    tx.update(mat_ref, {"quantity": round(avail + abs(delta), 4)})

        tx.update(doc_ref, updates)

    try:
        _run_inventory_transaction(_update_tx)
    except InventoryTransactionError as ite:
        return None, ite.message, ite.status_code
    except Exception as e:
        return None, f"Failed to update batch: {str(e)}", 500

    updated = serialize_value(doc_ref.get().to_dict())

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='UPDATE',
        resource='ProductionBatch',
        resource_id=batch_id,
        details=f"Updated batch {batch_id} fields: {list(updates.keys())}"
    )

    return updated, None, 200


def delete_batch(batch_id, current_user):
    doc_ref = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(batch_id)
    doc = doc_ref.get()
    if not doc.exists:
        matched = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('batch_id', '==', batch_id).get()
        for d in matched:
            doc_ref = d.reference
            doc = d
            break
    if not doc.exists:
        return False, "Batch not found", 404

    batch_data = doc.to_dict() or {}
    status = batch_data.get('status')
    mat_id = batch_data.get('material_id')
    allocated_qty = batch_data.get('allocated_material_qty', batch_data.get('quantity', 0))

    mat_ref = None
    if status != 'Completed' and mat_id and allocated_qty > 0:
        mat_ref, _ = _get_material_ref_and_doc(mat_id)

    def _delete_tx(tx):
        # Reads
        b_snap = doc_ref.get(transaction=tx)
        if not b_snap.exists:
            raise InventoryTransactionError("Batch not found", 404)

        mat_snap = None
        if mat_ref:
            mat_snap = mat_ref.get(transaction=tx)

        # Writes
        if mat_snap and mat_snap.exists:
            curr_stock = float((mat_snap.to_dict() or {}).get('quantity', 0.0))
            tx.update(mat_ref, {"quantity": round(curr_stock + allocated_qty, 4)})

        tx.delete(doc_ref)

    try:
        _run_inventory_transaction(_delete_tx)
    except InventoryTransactionError as ite:
        return False, ite.message, ite.status_code
    except Exception as e:
        return False, f"Failed to delete batch: {str(e)}", 500

    log_activity(
        user_id=current_user.get('user_id'),
        username=current_user.get('username'),
        action='DELETE',
        resource='ProductionBatch',
        resource_id=batch_id,
        details=f"Deleted batch {batch_id}"
    )

    return True, None, 200
