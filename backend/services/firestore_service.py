import logging
from datetime import datetime, date
from config.firebase import db

logger = logging.getLogger('sentinel-trace')

def serialize_value(val):
    """
    Converts Firestore Timestamps and datetime objects to ISO 8601 strings.
    Handles nested dicts and lists recursively.
    """
    if val is None:
        return None
    
    # Firestore Datetime / Timestamp
    if hasattr(val, 'isoformat') and callable(val.isoformat):
        return val.isoformat()
    
    # Datetime / Date fallback
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    
    if isinstance(val, dict):
        return {k: serialize_value(v) for k, v in val.items()}
    
    if isinstance(val, list):
        return [serialize_value(item) for item in val]
        
    return val


def serialize_document(doc_snapshot):
    """
    Safely serializes a DocumentSnapshot to a dictionary with formatted timestamps.
    """
    if not doc_snapshot or not doc_snapshot.exists:
        return None
    data = doc_snapshot.to_dict()
    if data is None:
        return None
    # Ensure doc_id is included if not in dict
    serialized = serialize_value(data)
    if 'id' not in serialized and '_id' not in serialized:
        serialized['_doc_id'] = doc_snapshot.id
    return serialized


def create_document(collection_name, doc_id, data):
    """
    Creates or overwrites a document in the given Firestore collection.
    """
    ref = db.collection(collection_name).document(doc_id)
    ref.set(data)
    created = ref.get()
    return serialize_document(created)


def get_document(collection_name, doc_id):
    """
    Retrieves a single document by ID from the specified collection.
    """
    ref = db.collection(collection_name).document(doc_id)
    snapshot = ref.get()
    if snapshot.exists:
        return serialize_document(snapshot)
    return None


def document_exists(collection_name, doc_id):
    """
    Checks if a document exists in a collection.
    """
    ref = db.collection(collection_name).document(doc_id)
    return ref.get().exists


def get_documents(collection_name, filters=None, order_by=None, direction='ASCENDING', limit=None):
    """
    Retrieves multiple documents from a collection with optional filters.
    filters: list of tuples [('field', '==', value), ...]
    """
    col_ref = db.collection(collection_name)
    query = col_ref

    if filters:
        for f in filters:
            if len(f) == 3:
                field, op, value = f
                query = query.where(field, op, value)

    if order_by:
        query = query.order_by(order_by, direction=direction)

    if limit and limit > 0:
        query = query.limit(limit)

    docs = query.get() if hasattr(query, 'get') else query.stream()
    return [serialize_document(doc) for doc in docs if doc.exists]


def update_document(collection_name, doc_id, updates):
    """
    Updates specific fields of an existing document.
    """
    ref = db.collection(collection_name).document(doc_id)
    snapshot = ref.get()
    if not snapshot.exists:
        return None
    ref.update(updates)
    updated = ref.get()
    return serialize_document(updated)


def delete_document(collection_name, doc_id):
    """
    Deletes a document from the specified collection.
    """
    ref = db.collection(collection_name).document(doc_id)
    snapshot = ref.get()
    if not snapshot.exists:
        return False
    ref.delete()
    return True
