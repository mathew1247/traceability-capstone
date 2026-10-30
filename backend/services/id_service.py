"""
Sentinel-Trace Atomic ID Allocation Service
Guarantees collision-free, monotonic, human-readable identifier generation
using Firestore transactions.

Eliminates collection-length-based ID generation (e.g. PRD101 + len)
which causes severe collisions on deletion, concurrency, or failed requests.
"""

import threading
import logging
import re
from config import Config
from config.firebase import db

logger = logging.getLogger('sentinel-trace')

_local_lock = threading.Lock()

# Entity configuration: collection name, ID prefix, starting base offset
ENTITY_SPECS = {
    'products': {
        'collection': Config.COLLECTION_PRODUCTS,
        'id_field': 'product_id',
        'prefix': 'PRD',
        'base': 100
    },
    'batches': {
        'collection': Config.COLLECTION_PRODUCTION_BATCHES,
        'id_field': 'batch_id',
        'prefix': 'BAT',
        'base': 200
    },
    'materials': {
        'collection': Config.COLLECTION_RAW_MATERIALS,
        'id_field': 'material_id',
        'prefix': 'RM',
        'base': 300
    },
    'suppliers': {
        'collection': Config.COLLECTION_SUPPLIERS,
        'id_field': 'supplier_id',
        'prefix': 'SUP',
        'base': 100
    },
    'compliance': {
        'collection': Config.COLLECTION_COMPLIANCE_RECORDS,
        'id_field': 'compliance_id',
        'prefix': 'CMP',
        'base': 400
    }
}

COLLECTION_COUNTERS = '_counters'


def _find_highest_existing_sequence(collection_name, prefix, base_offset):
    """
    Scans the collection once during counter initialization to find the maximum
    numeric suffix currently present in document IDs or primary ID fields.
    """
    try:
        docs = db.collection(collection_name).get()
        max_seq = base_offset
        pattern = re.compile(rf'^{prefix}(\d+)$')

        for d in docs:
            doc_id = d.id
            m = pattern.match(doc_id)
            if m:
                val = int(m.group(1))
                if val > max_seq:
                    max_seq = val
            # Also check data dictionary primary ID if present
            data = d.to_dict() if hasattr(d, 'to_dict') else None
            if data:
                for k, v in data.items():
                    if isinstance(v, str):
                        m2 = pattern.match(v)
                        if m2:
                            val2 = int(m2.group(1))
                            if val2 > max_seq:
                                max_seq = val2

        return max_seq
    except Exception as e:
        logger.warning(f"Error finding highest existing sequence for {collection_name}: {e}")
        return base_offset


def allocate_sequential_id(entity_key):
    """
    Allocates the next unique, monotonic identifier for an entity type.
    Uses a Firestore transaction in live Cloud Firestore, or a thread lock
    in LocalFirestoreClient mode.
    Guarantees:
    - Never reuses deleted IDs.
    - Zero collisions under concurrent requests.
    - Preserves human-readable format (e.g. PRD101, BAT201, RM301, SUP101, CMP401).
    """
    if entity_key not in ENTITY_SPECS:
        raise ValueError(f"Unknown entity key '{entity_key}'. Valid: {list(ENTITY_SPECS.keys())}")

    spec = ENTITY_SPECS[entity_key]
    collection_name = spec['collection']
    prefix = spec['prefix']
    base_offset = spec['base']

    counter_ref = db.collection(COLLECTION_COUNTERS).document(entity_key)

    is_local_mock = hasattr(db, '_persistence_file')

    if is_local_mock:
        with _local_lock:
            doc = counter_ref.get()
            if doc.exists:
                current_seq = doc.to_dict().get('current_sequence', base_offset)
            else:
                current_seq = _find_highest_existing_sequence(collection_name, prefix, base_offset)

            next_seq = current_seq + 1
            candidate_id = f"{prefix}{next_seq}"

            # Ensure candidate does not already exist
            while db.collection(collection_name).document(candidate_id).get().exists:
                next_seq += 1
                candidate_id = f"{prefix}{next_seq}"

            counter_ref.set({'current_sequence': next_seq})
            return candidate_id

    # Live Cloud Firestore: Execute atomic transaction
    from google.cloud import firestore

    @firestore.transactional
    def _allocate_in_transaction(transaction):
        snapshot = counter_ref.get(transaction=transaction)
        if snapshot.exists:
            current_seq = snapshot.get('current_sequence')
        else:
            current_seq = _find_highest_existing_sequence(collection_name, prefix, base_offset)

        next_seq = current_seq + 1
        candidate_id = f"{prefix}{next_seq}"

        # Collision avoidance check
        target_ref = db.collection(collection_name).document(candidate_id)
        target_snap = target_ref.get(transaction=transaction)
        while target_snap.exists:
            next_seq += 1
            candidate_id = f"{prefix}{next_seq}"
            target_ref = db.collection(collection_name).document(candidate_id)
            target_snap = target_ref.get(transaction=transaction)

        transaction.set(counter_ref, {'current_sequence': next_seq})
        return candidate_id

    transaction = db.transaction()
    allocated_id = _allocate_in_transaction(transaction)
    return allocated_id
