from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from utils.logger import app_logger

def get_traceability_lineage(query_id):
    """
    Requirement 14:
    Multi-tier bidirectional traceability engine.
    Constructs full lineage chain: Supplier -> Raw Material -> Batch -> Product -> Compliance Records.
    Returns:
    {
        "product": {...},
        "batches": [...],
        "materials": [...],
        "suppliers": [...],
        "compliance": [...]
    }
    """
    clean_id = query_id.strip() if query_id else ""
    if not clean_id:
        return None, "Traceability identifier is required.", 400

    suppliers_map = {}
    materials_map = {}
    batches_map = {}
    product = None
    compliance_list = []
    entity_type = None

    # 1. Check Product match
    prod_doc = db.collection(Config.COLLECTION_PRODUCTS).document(clean_id).get()
    if prod_doc.exists:
        entity_type = "Product"
        product = prod_doc.to_dict()

        # Find batches for this product
        batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('product_id', '==', clean_id).get()
        for b_doc in batches:
            b_data = b_doc.to_dict()
            if b_data:
                batches_map[b_data.get('batch_id')] = b_data
                mat_id = b_data.get('material_id')
                if mat_id and mat_id not in materials_map:
                    m_doc = db.collection(Config.COLLECTION_RAW_MATERIALS).document(mat_id).get()
                    if m_doc.exists:
                        materials_map[mat_id] = m_doc.to_dict()
                        s_id = materials_map[mat_id].get('supplier_id')
                        if s_id and s_id not in suppliers_map:
                            s_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(s_id).get()
                            if s_doc.exists:
                                suppliers_map[s_id] = s_doc.to_dict()

        comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', clean_id).get()
        compliance_list = [c.to_dict() for c in comp_docs if c.to_dict()]

    # 2. Check Batch match
    if not entity_type:
        batch_doc = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(clean_id).get()
        if batch_doc.exists:
            entity_type = "ProductionBatch"
            b_data = batch_doc.to_dict()
            batches_map[b_data.get('batch_id')] = b_data

            p_id = b_data.get('product_id')
            if p_id:
                p_doc = db.collection(Config.COLLECTION_PRODUCTS).document(p_id).get()
                if p_doc.exists:
                    product = p_doc.to_dict()
                comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', p_id).get()
                compliance_list = [c.to_dict() for c in comp_docs if c.to_dict()]

            mat_id = b_data.get('material_id')
            if mat_id:
                m_doc = db.collection(Config.COLLECTION_RAW_MATERIALS).document(mat_id).get()
                if m_doc.exists:
                    materials_map[mat_id] = m_doc.to_dict()
                    s_id = materials_map[mat_id].get('supplier_id')
                    if s_id:
                        s_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(s_id).get()
                        if s_doc.exists:
                            suppliers_map[s_id] = s_doc.to_dict()

    # 3. Check Raw Material match
    if not entity_type:
        mat_doc = db.collection(Config.COLLECTION_RAW_MATERIALS).document(clean_id).get()
        if mat_doc.exists:
            entity_type = "RawMaterial"
            m_data = mat_doc.to_dict()
            materials_map[clean_id] = m_data

            s_id = m_data.get('supplier_id')
            if s_id:
                s_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(s_id).get()
                if s_doc.exists:
                    suppliers_map[s_id] = s_doc.to_dict()

            batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('material_id', '==', clean_id).get()
            for b_doc in batches:
                b_data = b_doc.to_dict()
                if b_data:
                    batches_map[b_data.get('batch_id')] = b_data
                    p_id = b_data.get('product_id')
                    if p_id and not product:
                        p_doc = db.collection(Config.COLLECTION_PRODUCTS).document(p_id).get()
                        if p_doc.exists:
                            product = p_doc.to_dict()
                        comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', p_id).get()
                        compliance_list = [c.to_dict() for c in comp_docs if c.to_dict()]

    # 4. Check Supplier match
    if not entity_type:
        sup_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(clean_id).get()
        if sup_doc.exists:
            entity_type = "Supplier"
            suppliers_map[clean_id] = sup_doc.to_dict()

            mat_docs = db.collection(Config.COLLECTION_RAW_MATERIALS).where('supplier_id', '==', clean_id).get()
            for m in mat_docs:
                m_data = m.to_dict()
                if m_data:
                    m_id = m_data.get('material_id')
                    materials_map[m_id] = m_data
                    batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('material_id', '==', m_id).get()
                    for b_doc in batches:
                        b_data = b_doc.to_dict()
                        if b_data:
                            batches_map[b_data.get('batch_id')] = b_data
                            p_id = b_data.get('product_id')
                            if p_id and not product:
                                p_doc = db.collection(Config.COLLECTION_PRODUCTS).document(p_id).get()
                                if p_doc.exists:
                                    product = p_doc.to_dict()
                                comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', p_id).get()
                                compliance_list = [c.to_dict() for c in comp_docs if c.to_dict()]

    if not entity_type:
        return None, f"No traceability record found matching identifier '{clean_id}'. Checked Products, Batches, Materials, and Suppliers.", 404

    suppliers_list = [serialize_value(s) for s in suppliers_map.values()]
    materials_list = [serialize_value(m) for m in materials_map.values()]
    batches_list = [serialize_value(b) for b in batches_map.values()]
    product_serialized = serialize_value(product)
    compliance_serialized = [serialize_value(c) for c in compliance_list]

    result = {
        "query_id": clean_id,
        "matched_entity_type": entity_type,
        "chain_intact": bool(suppliers_list and materials_list and batches_list and product_serialized),
        "product": product_serialized,
        "batches": batches_list,
        "materials": materials_list,
        "suppliers": suppliers_list,
        "compliance": compliance_serialized,
        "traceability": {
            "supplier": suppliers_list[0] if suppliers_list else None,
            "material": materials_list[0] if materials_list else None,
            "batch": batches_list[0] if batches_list else None,
            "product": product_serialized,
            "compliance": compliance_serialized
        }
    }

    return result, None, 200
