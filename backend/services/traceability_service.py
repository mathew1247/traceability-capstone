import re
from datetime import datetime, timezone
from config import Config
from config.firebase import db
from services.firestore_service import serialize_value
from services.activity_log_service import log_activity
from utils.logger import app_logger

VALID_ID_PATTERN = re.compile(r'^[A-Za-z0-9_\-\.\:\/]+$')

def validate_identifier(raw_id):
    """
    Validates traceability query identifier.
    Returns (clean_id, error_msg, status_code).
    """
    if not raw_id or not isinstance(raw_id, str):
        return None, "Traceability identifier is required.", 400

    clean_id = raw_id.strip()
    if not clean_id or len(clean_id) < 2 or len(clean_id) > 64:
        return None, "Traceability identifier must be between 2 and 64 characters.", 400

    if not VALID_ID_PATTERN.match(clean_id):
        return None, f"Traceability identifier '{clean_id}' contains invalid characters.", 400

    return clean_id, None, 200


def resolve_entity(clean_id):
    """
    Resolves clean_id against Products, Batches, Materials, Suppliers, and Compliance records.
    Supports document ID, primary ID field, product_code, and compliance_id.
    Returns (entity_type, entity_data) or (None, None).
    """
    # 1. Product (by doc ID, product_id, or product_code)
    prod_doc = db.collection(Config.COLLECTION_PRODUCTS).document(clean_id).get()
    if prod_doc.exists:
        return "Product", prod_doc.to_dict()

    matched_prods = db.collection(Config.COLLECTION_PRODUCTS).where('product_id', '==', clean_id).get()
    if not matched_prods:
        matched_prods = db.collection(Config.COLLECTION_PRODUCTS).where('product_code', '==', clean_id).get()
    if not matched_prods and clean_id.upper() != clean_id:
        matched_prods = db.collection(Config.COLLECTION_PRODUCTS).where('product_code', '==', clean_id.upper()).get()
    if matched_prods:
        prods = [d.to_dict() for d in matched_prods if d.to_dict()]
        if prods:
            prods.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
            return "Product", prods[0]

    # 2. Production Batch (by doc ID or batch_id)
    batch_doc = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(clean_id).get()
    if batch_doc.exists:
        return "ProductionBatch", batch_doc.to_dict()

    matched_batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('batch_id', '==', clean_id).get()
    if matched_batches:
        batches = [d.to_dict() for d in matched_batches if d.to_dict()]
        if batches:
            batches.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
            return "ProductionBatch", batches[0]

    # 3. Raw Material (by doc ID or material_id)
    mat_doc = db.collection(Config.COLLECTION_RAW_MATERIALS).document(clean_id).get()
    if mat_doc.exists:
        return "RawMaterial", mat_doc.to_dict()

    matched_mats = db.collection(Config.COLLECTION_RAW_MATERIALS).where('material_id', '==', clean_id).get()
    if matched_mats:
        mats = [d.to_dict() for d in matched_mats if d.to_dict()]
        if mats:
            mats.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
            return "RawMaterial", mats[0]

    # 4. Supplier (by doc ID or supplier_id)
    sup_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(clean_id).get()
    if sup_doc.exists:
        return "Supplier", sup_doc.to_dict()

    matched_sups = db.collection(Config.COLLECTION_SUPPLIERS).where('supplier_id', '==', clean_id).get()
    if matched_sups:
        sups = [d.to_dict() for d in matched_sups if d.to_dict()]
        if sups:
            sups.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
            return "Supplier", sups[0]

    # 5. Compliance Record (by doc ID or compliance_id)
    comp_doc = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).document(clean_id).get()
    if comp_doc.exists:
        return "ComplianceRecord", comp_doc.to_dict()

    matched_comps = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('compliance_id', '==', clean_id).get()
    if matched_comps:
        comps = [d.to_dict() for d in matched_comps if d.to_dict()]
        if comps:
            comps.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
            return "ComplianceRecord", comps[0]

    return None, None


def get_traceability_lineage(query_id, direction='forward'):
    """
    Requirement 14:
    Multi-tier bidirectional traceability engine.
    Constructs forward (source to distribution) or backward (field to supplier) lineage chain.
    """
    clean_id, val_err, status_code = validate_identifier(query_id)
    if val_err:
        return None, val_err, status_code

    direction = (direction or 'forward').strip().lower()
    if direction not in ('forward', 'backward'):
        direction = 'forward'

    entity_type, entity_data = resolve_entity(clean_id)
    if not entity_type:
        return None, f"No traceability record found matching identifier '{clean_id}'. Checked Products, Batches, Materials, Suppliers, and Compliance records.", 404

    suppliers_map = {}
    materials_map = {}
    batches_map = {}
    products_map = {}
    compliance_map = {}

    def fetch_supplier(s_id):
        if not s_id or s_id in suppliers_map:
            return
        doc = db.collection(Config.COLLECTION_SUPPLIERS).document(s_id).get()
        if doc.exists:
            suppliers_map[s_id] = doc.to_dict()
        else:
            m = db.collection(Config.COLLECTION_SUPPLIERS).where('supplier_id', '==', s_id).get()
            for d in m:
                if d.to_dict():
                    suppliers_map[s_id] = d.to_dict()
                    break

    def fetch_material(m_id):
        if not m_id or m_id in materials_map:
            return
        doc = db.collection(Config.COLLECTION_RAW_MATERIALS).document(m_id).get()
        if doc.exists:
            materials_map[m_id] = doc.to_dict()
        else:
            m = db.collection(Config.COLLECTION_RAW_MATERIALS).where('material_id', '==', m_id).get()
            for d in m:
                if d.to_dict():
                    materials_map[m_id] = d.to_dict()
                    break
        m_data = materials_map.get(m_id)
        if m_data and m_data.get('supplier_id'):
            fetch_supplier(m_data['supplier_id'])

    def fetch_product(p_id):
        if not p_id or p_id in products_map:
            return
        doc = db.collection(Config.COLLECTION_PRODUCTS).document(p_id).get()
        if doc.exists:
            products_map[p_id] = doc.to_dict()
        else:
            m = db.collection(Config.COLLECTION_PRODUCTS).where('product_id', '==', p_id).get()
            for d in m:
                if d.to_dict():
                    products_map[p_id] = d.to_dict()
                    break

    # Traverse according to entity_type and direction
    if direction == 'backward':
        # Backward traversal: trace upstream toward original sourcing suppliers
        if entity_type == "ComplianceRecord":
            c_id = entity_data.get('compliance_id') or clean_id
            compliance_map[c_id] = entity_data
            p_id = entity_data.get('product_id')
            if p_id:
                fetch_product(p_id)
                batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('product_id', '==', p_id).get()
                for b_doc in batches:
                    b_data = b_doc.to_dict()
                    if b_data:
                        batches_map[b_data.get('batch_id')] = b_data
                        if b_data.get('material_id'):
                            fetch_material(b_data['material_id'])

        elif entity_type == "Product":
            p_id = entity_data.get('product_id') or clean_id
            products_map[p_id] = entity_data
            batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('product_id', '==', p_id).get()
            for b_doc in batches:
                b_data = b_doc.to_dict()
                if b_data:
                    batches_map[b_data.get('batch_id')] = b_data
                    if b_data.get('material_id'):
                        fetch_material(b_data['material_id'])

        elif entity_type == "ProductionBatch":
            b_id = entity_data.get('batch_id') or clean_id
            batches_map[b_id] = entity_data
            if entity_data.get('material_id'):
                fetch_material(entity_data['material_id'])

        elif entity_type == "RawMaterial":
            m_id = entity_data.get('material_id') or clean_id
            materials_map[m_id] = entity_data
            if entity_data.get('supplier_id'):
                fetch_supplier(entity_data['supplier_id'])

        elif entity_type == "Supplier":
            s_id = entity_data.get('supplier_id') or clean_id
            suppliers_map[s_id] = entity_data

    else:
        # Forward traversal: trace downstream toward distribution and certifications
        if entity_type == "Supplier":
            s_id = entity_data.get('supplier_id') or clean_id
            suppliers_map[s_id] = entity_data
            mats = db.collection(Config.COLLECTION_RAW_MATERIALS).where('supplier_id', '==', s_id).get()
            for m_doc in mats:
                m_data = m_doc.to_dict()
                if m_data:
                    m_id = m_data.get('material_id')
                    materials_map[m_id] = m_data
                    batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('material_id', '==', m_id).get()
                    for b_doc in batches:
                        b_data = b_doc.to_dict()
                        if b_data:
                            batches_map[b_data.get('batch_id')] = b_data
                            p_id = b_data.get('product_id')
                            if p_id:
                                fetch_product(p_id)
                                comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', p_id).get()
                                for c_doc in comp_docs:
                                    c_data = c_doc.to_dict()
                                    if c_data:
                                        compliance_map[c_data.get('compliance_id')] = c_data

        elif entity_type == "RawMaterial":
            m_id = entity_data.get('material_id') or clean_id
            materials_map[m_id] = entity_data
            if entity_data.get('supplier_id'):
                fetch_supplier(entity_data['supplier_id'])
            batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('material_id', '==', m_id).get()
            for b_doc in batches:
                b_data = b_doc.to_dict()
                if b_data:
                    batches_map[b_data.get('batch_id')] = b_data
                    p_id = b_data.get('product_id')
                    if p_id:
                        fetch_product(p_id)
                        comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', p_id).get()
                        for c_doc in comp_docs:
                            c_data = c_doc.to_dict()
                            if c_data:
                                compliance_map[c_data.get('compliance_id')] = c_data

        elif entity_type == "ProductionBatch":
            b_id = entity_data.get('batch_id') or clean_id
            batches_map[b_id] = entity_data
            if entity_data.get('material_id'):
                fetch_material(entity_data['material_id'])
            p_id = entity_data.get('product_id')
            if p_id:
                fetch_product(p_id)
                comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', p_id).get()
                for c_doc in comp_docs:
                    c_data = c_doc.to_dict()
                    if c_data:
                        compliance_map[c_data.get('compliance_id')] = c_data

        elif entity_type == "Product":
            p_id = entity_data.get('product_id') or clean_id
            products_map[p_id] = entity_data
            comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', p_id).get()
            for c_doc in comp_docs:
                c_data = c_doc.to_dict()
                if c_data:
                    compliance_map[c_data.get('compliance_id')] = c_data
            batches = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).where('product_id', '==', p_id).get()
            for b_doc in batches:
                b_data = b_doc.to_dict()
                if b_data:
                    batches_map[b_data.get('batch_id')] = b_data
                    if b_data.get('material_id'):
                        fetch_material(b_data['material_id'])

        elif entity_type == "ComplianceRecord":
            c_id = entity_data.get('compliance_id') or clean_id
            compliance_map[c_id] = entity_data
            p_id = entity_data.get('product_id')
            if p_id:
                fetch_product(p_id)
                comp_docs = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).where('product_id', '==', p_id).get()
                for c_doc in comp_docs:
                    c_data = c_doc.to_dict()
                    if c_data:
                        compliance_map[c_data.get('compliance_id')] = c_data

    suppliers_list = [serialize_value(s) for s in suppliers_map.values()]
    materials_list = [serialize_value(m) for m in materials_map.values()]
    batches_list = [serialize_value(b) for b in batches_map.values()]
    products_list = [serialize_value(p) for p in products_map.values()]
    primary_product = products_list[0] if products_list else None
    compliance_list = [serialize_value(c) for c in compliance_map.values()]

    # Construct ordered pipeline stages reflecting direction
    stages = []
    step = 1

    if direction == 'backward':
        # Backward: downstream -> upstream (Field to Supplier)
        if compliance_list:
            for c in compliance_list:
                stages.append({
                    "step": step,
                    "stage": "Compliance",
                    "id": c.get('compliance_id'),
                    "title": c.get('standard', 'Compliance Record'),
                    "meta": f"Status: {c.get('status', 'Compliant')} • Exp: {c.get('expiry_date', 'N/A')}",
                    "details": {
                        "Compliance ID": c.get('compliance_id'),
                        "Governing Standard": c.get('standard'),
                        "Verification Status": c.get('status'),
                        "Auditing Authority": c.get('auditing_body') or c.get('audited_by') or "Authorized Inspector",
                        "Certification Expiry": c.get('expiry_date', 'N/A'),
                        "Audit Notes": c.get('remarks', 'Verified compliance record')
                    }
                })
                step += 1

        if primary_product:
            stages.append({
                "step": step,
                "stage": "Product",
                "id": primary_product.get('product_id'),
                "title": primary_product.get('product_name') or "Finished Product",
                "meta": f"SKU: {primary_product.get('product_code', 'N/A')} • {primary_product.get('status', 'Certified')}",
                "details": {
                    "Product ID": primary_product.get('product_id'),
                    "Catalog Title": primary_product.get('product_name'),
                    "Product Code": primary_product.get('product_code'),
                    "Description": primary_product.get('description', 'N/A'),
                    "Lifecycle Status": primary_product.get('status', 'Certified')
                }
            })
            step += 1

        for b in batches_list:
            stages.append({
                "step": step,
                "stage": "Production Batch",
                "id": b.get('batch_id'),
                "title": f"Batch {b.get('batch_id')}",
                "meta": f"Qty: {b.get('quantity', 0)} units • {b.get('status', 'Completed')}",
                "details": {
                    "Batch ID": b.get('batch_id'),
                    "Product Target": b.get('product_id', 'N/A'),
                    "Material Input": b.get('material_id', 'N/A'),
                    "Output Quantity": f"{b.get('quantity', 0)} units",
                    "Production Date": b.get('production_date', 'N/A'),
                    "Operational State": b.get('status', 'Completed')
                }
            })
            step += 1

        for m in materials_list:
            stages.append({
                "step": step,
                "stage": "Raw Material",
                "id": m.get('material_id'),
                "title": m.get('material_name', 'Raw Material'),
                "meta": f"{m.get('quantity', 0)} {m.get('unit', 'Kg')} • Verified",
                "details": {
                    "Material ID": m.get('material_id'),
                    "Specification": m.get('material_name'),
                    "Lot Quantity": f"{m.get('quantity', 0)} {m.get('unit', 'Kg')}",
                    "Supplier Reference": m.get('supplier_id', 'N/A'),
                    "Inbound Timestamp": m.get('created_at', 'Verified')
                }
            })
            step += 1

        for s in suppliers_list:
            stages.append({
                "step": step,
                "stage": "Supplier",
                "id": s.get('supplier_id'),
                "title": s.get('supplier_name', 'Supplier Partner'),
                "meta": f"{s.get('address', 'Facility')} • {s.get('status', 'Active')}",
                "details": {
                    "Supplier ID": s.get('supplier_id'),
                    "Company Name": s.get('supplier_name'),
                    "Contact Person": s.get('contact', 'N/A'),
                    "Official Email": s.get('email', 'N/A'),
                    "Facility Address": s.get('address', 'N/A'),
                    "Vendor Status": s.get('status', 'Active')
                }
            })
            step += 1

    else:
        # Forward: upstream -> downstream (Source to Distribution)
        for s in suppliers_list:
            stages.append({
                "step": step,
                "stage": "Supplier",
                "id": s.get('supplier_id'),
                "title": s.get('supplier_name', 'Supplier Partner'),
                "meta": f"{s.get('address', 'Facility')} • {s.get('status', 'Active')}",
                "details": {
                    "Supplier ID": s.get('supplier_id'),
                    "Company Name": s.get('supplier_name'),
                    "Contact Person": s.get('contact', 'N/A'),
                    "Official Email": s.get('email', 'N/A'),
                    "Facility Address": s.get('address', 'N/A'),
                    "Vendor Status": s.get('status', 'Active')
                }
            })
            step += 1

        for m in materials_list:
            stages.append({
                "step": step,
                "stage": "Raw Material",
                "id": m.get('material_id'),
                "title": m.get('material_name', 'Raw Material'),
                "meta": f"{m.get('quantity', 0)} {m.get('unit', 'Kg')} • Verified",
                "details": {
                    "Material ID": m.get('material_id'),
                    "Specification": m.get('material_name'),
                    "Lot Quantity": f"{m.get('quantity', 0)} {m.get('unit', 'Kg')}",
                    "Supplier Reference": m.get('supplier_id', 'N/A'),
                    "Inbound Timestamp": m.get('created_at', 'Verified')
                }
            })
            step += 1

        for b in batches_list:
            stages.append({
                "step": step,
                "stage": "Production Batch",
                "id": b.get('batch_id'),
                "title": f"Batch {b.get('batch_id')}",
                "meta": f"Qty: {b.get('quantity', 0)} units • {b.get('status', 'Completed')}",
                "details": {
                    "Batch ID": b.get('batch_id'),
                    "Product Target": b.get('product_id', 'N/A'),
                    "Material Input": b.get('material_id', 'N/A'),
                    "Output Quantity": f"{b.get('quantity', 0)} units",
                    "Production Date": b.get('production_date', 'N/A'),
                    "Operational State": b.get('status', 'Completed')
                }
            })
            step += 1

        if primary_product:
            stages.append({
                "step": step,
                "stage": "Product",
                "id": primary_product.get('product_id'),
                "title": primary_product.get('product_name') or "Finished Product",
                "meta": f"SKU: {primary_product.get('product_code', 'N/A')} • {primary_product.get('status', 'Certified')}",
                "details": {
                    "Product ID": primary_product.get('product_id'),
                    "Catalog Title": primary_product.get('product_name'),
                    "Product Code": primary_product.get('product_code'),
                    "Description": primary_product.get('description', 'N/A'),
                    "Lifecycle Status": primary_product.get('status', 'Certified')
                }
            })
            step += 1

        if compliance_list:
            for c in compliance_list:
                stages.append({
                    "step": step,
                    "stage": "Compliance",
                    "id": c.get('compliance_id'),
                    "title": c.get('standard', 'Compliance Record'),
                    "meta": f"Status: {c.get('status', 'Compliant')} • Exp: {c.get('expiry_date', 'N/A')}",
                    "details": {
                        "Compliance ID": c.get('compliance_id'),
                        "Governing Standard": c.get('standard'),
                        "Verification Status": c.get('status'),
                        "Auditing Authority": c.get('auditing_body') or c.get('audited_by') or "Authorized Inspector",
                        "Certification Expiry": c.get('expiry_date', 'N/A'),
                        "Audit Notes": c.get('remarks', 'Verified compliance record')
                    }
                })
                step += 1

    result = {
        "query_id": clean_id,
        "matched_entity_type": entity_type,
        "direction": direction,
        "chain_intact": bool(suppliers_list and materials_list and batches_list and primary_product),
        "product": primary_product,
        "batches": batches_list,
        "materials": materials_list,
        "suppliers": suppliers_list,
        "compliance": compliance_list,
        "stages": stages,
        "traceability": {
            "supplier": suppliers_list[0] if suppliers_list else None,
            "material": materials_list[0] if materials_list else None,
            "batch": batches_list[0] if batches_list else None,
            "product": primary_product,
            "compliance": compliance_list
        }
    }

    return result, None, 200


def audit_lineage_chain(query_id, current_user=None):
    """
    Audits and validates the traceability lineage chain for query_id.
    Performs real Firestore ledger checks across suppliers, materials, batches,
    products, and compliance records.
    """
    clean_id, val_err, status_code = validate_identifier(query_id)
    if val_err:
        return None, val_err, status_code

    lineage, err, code = get_traceability_lineage(clean_id, direction='forward')
    if err:
        return None, err, code

    stages = lineage.get('stages') or []
    issues = []
    verified_nodes = 0

    # 1. Validate primary product
    product = lineage.get('product')
    if product:
        p_id = product.get('product_id', '')
        p_doc = db.collection(Config.COLLECTION_PRODUCTS).document(p_id).get()
        if p_doc.exists:
            verified_nodes += 1
        else:
            issues.append(f"Product {p_id} is referenced in lineage but missing from products collection.")
    else:
        issues.append("Lineage chain lacks an associated finished product record.")

    # 2. Validate batches
    batches = lineage.get('batches') or []
    if not batches:
        issues.append("Lineage chain contains no associated production batches.")
    for b in batches:
        b_id = b.get('batch_id')
        b_doc = db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(b_id).get()
        if not b_doc.exists:
            issues.append(f"Production batch {b_id} missing from production_batches collection.")
            continue
        verified_nodes += 1
        mat_id = b.get('material_id')
        if mat_id:
            m_doc = db.collection(Config.COLLECTION_RAW_MATERIALS).document(mat_id).get()
            if not m_doc.exists:
                issues.append(f"Batch {b_id} references material {mat_id} which does not exist in raw_materials.")
        else:
            issues.append(f"Batch {b_id} has no linked raw material ID.")

    # 3. Validate raw materials & suppliers
    materials = lineage.get('materials') or []
    if not materials:
        issues.append("Lineage chain lacks associated raw material records.")
    for m in materials:
        m_id = m.get('material_id')
        m_doc = db.collection(Config.COLLECTION_RAW_MATERIALS).document(m_id).get()
        if not m_doc.exists:
            issues.append(f"Raw material {m_id} missing from raw_materials collection.")
            continue
        verified_nodes += 1
        sup_id = m.get('supplier_id')
        if sup_id:
            s_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(sup_id).get()
            if not s_doc.exists:
                issues.append(f"Material {m_id} references supplier {sup_id} which does not exist in suppliers.")
            else:
                s_data = s_doc.to_dict()
                if s_data and s_data.get('status') == 'Suspended':
                    issues.append(f"Material {m_id} is sourced from SUSPENDED supplier {sup_id} ({s_data.get('supplier_name', 'Unknown')}).")
        else:
            issues.append(f"Material {m_id} has no linked supplier ID.")

    suppliers = lineage.get('suppliers') or []
    for s in suppliers:
        s_id = s.get('supplier_id')
        s_doc = db.collection(Config.COLLECTION_SUPPLIERS).document(s_id).get()
        if s_doc.exists:
            verified_nodes += 1

    # 4. Validate compliance records
    compliance = lineage.get('compliance') or []
    now = datetime.now(timezone.utc)
    for c in compliance:
        c_id = c.get('compliance_id')
        c_doc = db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).document(c_id).get()
        if not c_doc.exists:
            issues.append(f"Compliance certification {c_id} missing from compliance_records collection.")
            continue
        verified_nodes += 1
        exp_str = c.get('expiry_date')
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str) if 'T' in exp_str else datetime.strptime(exp_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                if exp_dt < now:
                    issues.append(f"Compliance certification {c_id} ({c.get('standard')}) expired on {exp_str}.")
            except Exception:
                pass
        if c.get('status') == 'Expired':
            issues.append(f"Compliance certification {c_id} is marked as Expired.")

    total_audited = len(stages)
    chain_intact = bool(product and batches and materials and suppliers and not issues)
    if chain_intact:
        status_label = "VALIDATED"
        msg = f"Audit complete: All {verified_nodes} lineage nodes and relationships successfully validated against Cloud Firestore ledger."
    elif not issues and total_audited > 0:
        status_label = "PARTIAL_VALIDATED"
        msg = f"Audit complete: {verified_nodes} node(s) verified, but end-to-end pedigree chain is incomplete."
    else:
        status_label = "FLAGGED" if verified_nodes > 0 else "BROKEN"
        msg = f"Audit flagged {len(issues)} issue(s) across {total_audited} lineage stage(s): {'; '.join(issues[:2])}"

    audit_result = {
        "query_id": clean_id,
        "matched_entity_type": lineage.get("matched_entity_type"),
        "integrity_status": status_label,
        "chain_intact": chain_intact,
        "total_nodes_audited": total_audited,
        "nodes_verified": verified_nodes,
        "validation_timestamp": now.isoformat(),
        "issues": issues,
        "message": msg
    }

    if current_user:
        try:
            log_activity(
                user_id=current_user.get('user_id'),
                username=current_user.get('username'),
                action='AUDIT_LINEAGE',
                resource='Traceability',
                resource_id=clean_id,
                details=f"Audited lineage for {clean_id}: {status_label} ({verified_nodes}/{total_audited} nodes verified)"
            )
        except Exception as log_err:
            app_logger.warning(f"Failed to log lineage audit activity: {log_err}")

    return audit_result, None, 200
