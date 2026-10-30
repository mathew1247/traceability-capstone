"""
Live Firestore CRUD Integration Test Suite
Verifies end-to-end CRUD operations, referential integrity, and safe cleanup
against the configured Google Cloud Firestore project (capstone-8ee41).

Safety requirements:
- Strictly verifies that real Cloud Firestore (not mock/local persistence) is active.
- Uses dedicated test records with unique random codes/names.
- Verifies foreign-key validation (Product -> Batch, Material -> Batch, Supplier -> Material).
- Deletes all created test records in teardown/finally blocks.
- Never prints or logs credentials, private keys, or tokens.
"""

import os
import sys
import unittest
import uuid
from pathlib import Path

# Ensure live Cloud Firestore is used for integration testing
if 'USE_LOCAL_FIRESTORE' in os.environ:
    del os.environ['USE_LOCAL_FIRESTORE']

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from config import Config
from config.firebase import init_firebase, db, check_firestore_connectivity
from services.supplier_service import (
    create_supplier,
    get_supplier_by_id,
    update_supplier,
    delete_supplier,
    verify_supplier_documents
)
from services.material_service import (
    create_material,
    get_material_by_id,
    update_material,
    delete_material
)
from services.product_service import (
    create_product,
    get_product_by_id,
    update_product,
    delete_product
)
from services.batch_service import (
    create_batch,
    get_batch_by_id,
    update_batch,
    delete_batch
)
from services.compliance_service import (
    create_compliance_record,
    get_compliance_by_id,
    update_compliance_record,
    delete_compliance_record
)
from services.auth_service import (
    create_user,
    get_user_by_id,
    update_user,
    delete_user
)
from services.alert_service import (
    create_alert,
    get_alert_by_id,
    update_alert_action
)
from services.traceability_service import (
    get_traceability_lineage,
    audit_lineage_chain
)


class FirestoreCrudIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Ensure live Cloud Firestore is active (reset if previous test set mock)
        import config.firebase as fb
        if hasattr(fb.db, '_persistence_file') or not fb._firebase_initialized:
            if 'USE_LOCAL_FIRESTORE' in os.environ:
                del os.environ['USE_LOCAL_FIRESTORE']
            fb._firebase_initialized = False
            fb.db = None
            fb.init_firebase()

        if hasattr(fb.db, '_persistence_file'):
            raise RuntimeError("Integration tests must run against live Cloud Firestore, but local storage engine is active!")

        # 2. Verify project ID matches capstone-8ee41
        diag = check_firestore_connectivity()
        if not diag.get('firestore_accessible'):
            raise RuntimeError(f"Cloud Firestore is not accessible: {diag.get('message')}")
        if diag.get('configured_project_id') != 'capstone-8ee41':
            raise RuntimeError(f"Configured project ID is '{diag.get('configured_project_id')}', expected 'capstone-8ee41'")

        cls.admin_user = {
            "user_id": "USR-ADMIN01",
            "username": "Jack Mathew",
            "role": "Admin",
            "email": "admin@sentineltrace.local"
        }

        # Track all created IDs for guaranteed cleanup
        cls.created_suppliers = []
        cls.created_materials = []
        cls.created_products = []
        cls.created_batches = []
        cls.created_compliance = []
        cls.created_users = []
        cls.created_alerts = []

    @classmethod
    def tearDownClass(cls):
        """Guaranteed cleanup of any remaining test records in reverse dependency order."""
        # Clean compliance records
        for cid in cls.created_compliance:
            try:
                db.collection(Config.COLLECTION_COMPLIANCE_RECORDS).document(cid).delete()
            except Exception:
                pass

        # Clean batches
        for bid in cls.created_batches:
            try:
                db.collection(Config.COLLECTION_PRODUCTION_BATCHES).document(bid).delete()
            except Exception:
                pass

        # Clean products
        for pid in cls.created_products:
            try:
                db.collection(Config.COLLECTION_PRODUCTS).document(pid).delete()
            except Exception:
                pass

        # Clean raw materials
        for mid in cls.created_materials:
            try:
                db.collection(Config.COLLECTION_RAW_MATERIALS).document(mid).delete()
            except Exception:
                pass

        # Clean suppliers
        for sid in cls.created_suppliers:
            try:
                db.collection(Config.COLLECTION_SUPPLIERS).document(sid).delete()
            except Exception:
                pass

        # Clean users
        for uid in cls.created_users:
            try:
                db.collection(Config.COLLECTION_USERS).document(uid).delete()
            except Exception:
                pass

        # Clean alerts
        for aid in cls.created_alerts:
            try:
                db.collection(Config.COLLECTION_ALERTS).document(aid).delete()
            except Exception:
                pass

    def test_01_supplier_crud(self):
        """Verify Create, Read, Update for Supplier module in Firestore."""
        suffix = uuid.uuid4().hex[:6]
        sup_data = {
            "supplier_name": f"Test Ineg Supplier {suffix}",
            "contact": "Jane Doe",
            "email": f"integ.{suffix}@vendor.test",
            "address": "100 Industrial Parkway, Sector 4",
            "status": "Active"
        }

        # 1. Create
        record, err, code = create_supplier(sup_data, self.admin_user)
        self.assertIsNone(err)
        self.assertEqual(code, 201)
        self.assertIsNotNone(record)
        sup_id = record['supplier_id']
        self.__class__.created_suppliers.append(sup_id)

        # 2. Read
        fetched = get_supplier_by_id(sup_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['supplier_name'], sup_data['supplier_name'])
        self.assertEqual(fetched['email'], sup_data['email'])

        # 3. Update
        updated_data = {
            "contact": "Jane Doe-Smith",
            "address": "200 Advanced Parkway, Sector 7"
        }
        updated, u_err, u_code = update_supplier(sup_id, updated_data, self.admin_user)
        self.assertIsNone(u_err)
        self.assertEqual(u_code, 200)
        self.assertEqual(updated['contact'], "Jane Doe-Smith")
        self.assertEqual(updated['address'], "200 Advanced Parkway, Sector 7")

        # 4. Verify Read reflects update
        re_fetched = get_supplier_by_id(sup_id)
        self.assertEqual(re_fetched['contact'], "Jane Doe-Smith")

    def test_02_raw_material_crud(self):
        """Verify Raw Material CRUD and Supplier foreign-key reference in Firestore."""
        # Use existing created supplier or create one
        self.assertTrue(len(self.__class__.created_suppliers) > 0)
        sup_id = self.__class__.created_suppliers[0]

        suffix = uuid.uuid4().hex[:6]
        mat_data = {
            "material_name": f"Test Ingot {suffix}",
            "supplier_id": sup_id,
            "quantity": 250.5,
            "unit": "kg"
        }

        # 1. Create with valid supplier
        record, err, code = create_material(mat_data, self.admin_user)
        self.assertIsNone(err)
        self.assertEqual(code, 201)
        mat_id = record['material_id']
        self.__class__.created_materials.append(mat_id)

        # 2. Read
        fetched = get_material_by_id(mat_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['material_name'], mat_data['material_name'])
        self.assertEqual(fetched['supplier_id'], sup_id)

        # 3. Update
        updated, u_err, u_code = update_material(mat_id, {"quantity": 300.0, "unit": "kg"}, self.admin_user)
        self.assertIsNone(u_err)
        self.assertEqual(u_code, 200)
        self.assertEqual(updated['quantity'], 300.0)

        # 4. Create with non-existent supplier must be rejected (404)
        bad_mat_data = {
            "material_name": f"Invalid Material {suffix}",
            "supplier_id": "NON-EXISTENT-SUP-9999",
            "quantity": 10,
            "unit": "units"
        }
        _, bad_err, bad_code = create_material(bad_mat_data, self.admin_user)
        self.assertIsNotNone(bad_err)
        self.assertEqual(bad_code, 404)

    def test_03_product_crud(self):
        """Verify Product CRUD and unique product_code enforcement in Firestore."""
        suffix = uuid.uuid4().hex[:6]
        code = f"PRD-TEST-{suffix.upper()}"
        prod_data = {
            "product_name": f"Integ Test Enclosure {suffix}",
            "product_code": code,
            "description": "High integrity security enclosure for OT nodes",
            "status": "In Production"
        }

        # 1. Create
        record, err, status_code = create_product(prod_data, self.admin_user)
        self.assertIsNone(err)
        self.assertEqual(status_code, 201)
        prod_id = record['product_id']
        self.__class__.created_products.append(prod_id)

        # 2. Read
        fetched = get_product_by_id(prod_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['product_code'], code)

        # 3. Duplicate code rejection (409)
        _, dup_err, dup_code = create_product(prod_data, self.admin_user)
        self.assertIsNotNone(dup_err)
        self.assertEqual(dup_code, 409)

        # 4. Update
        updated, u_err, u_code = update_product(prod_id, {"status": "Certified"}, self.admin_user)
        self.assertIsNone(u_err)
        self.assertEqual(u_code, 200)
        self.assertEqual(updated['status'], "Certified")

    def test_04_production_batch_crud(self):
        """Verify Production Batch linking Product and Material in Firestore."""
        self.assertTrue(len(self.__class__.created_products) > 0)
        self.assertTrue(len(self.__class__.created_materials) > 0)
        prod_id = self.__class__.created_products[0]
        mat_id = self.__class__.created_materials[0]

        batch_data = {
            "product_id": prod_id,
            "material_id": mat_id,
            "quantity": 50,
            "status": "Running"
        }

        # 1. Create
        record, err, code = create_batch(batch_data, self.admin_user)
        self.assertIsNone(err)
        self.assertEqual(code, 201)
        batch_id = record['batch_id']
        self.__class__.created_batches.append(batch_id)

        # 2. Read
        fetched = get_batch_by_id(batch_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['product_id'], prod_id)
        self.assertEqual(fetched['material_id'], mat_id)

        # 3. Update
        updated, u_err, u_code = update_batch(batch_id, {"status": "Completed"}, self.admin_user)
        self.assertIsNone(u_err)
        self.assertEqual(u_code, 200)
        self.assertEqual(updated['status'], "Completed")

        # 4. Invalid foreign key rejection
        bad_batch = {
            "product_id": "PRD-NONEXISTENT-999",
            "material_id": mat_id,
            "quantity": 10
        }
        _, b_err, b_code = create_batch(bad_batch, self.admin_user)
        self.assertIsNotNone(b_err)
        self.assertEqual(b_code, 404)

    def test_05_compliance_record_crud(self):
        """Verify Compliance Record CRUD and product reference in Firestore."""
        self.assertTrue(len(self.__class__.created_products) > 0)
        prod_id = self.__class__.created_products[0]

        comp_data = {
            "product_id": prod_id,
            "standard": "ISO 9001:2015",
            "status": "Compliant",
            "expiry_date": "2027-12-31",
            "remarks": "Clean audit report verified"
        }

        # 1. Create
        record, err, code = create_compliance_record(comp_data, self.admin_user)
        self.assertIsNone(err)
        self.assertEqual(code, 201)
        comp_id = record['compliance_id']
        self.__class__.created_compliance.append(comp_id)

        # 2. Read
        fetched = get_compliance_by_id(comp_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['product_id'], prod_id)
        self.assertEqual(fetched['standard'], "ISO 9001:2015")

        # 3. Update
        updated, u_err, u_code = update_compliance_record(comp_id, {"remarks": "Annual audit complete"}, self.admin_user)
        self.assertIsNone(u_err)
        self.assertEqual(u_code, 200)
        self.assertEqual(updated['remarks'], "Annual audit complete")

    def test_06_traceability_graph_and_lineage_audit(self):
        """Verify real multi-tier relationship traversal in Firestore."""
        prod_id = self.__class__.created_products[0]

        # 1. Graph traversal
        tree, err, code = get_traceability_lineage(prod_id, direction='backward')
        self.assertIsNone(err)
        self.assertEqual(code, 200)
        self.assertEqual(tree.get('query_id'), prod_id)
        self.assertEqual(tree.get('matched_entity_type'), 'Product')
        self.assertTrue(tree.get('chain_intact'))

        # 2. Lineage chain audit
        audit_res, a_err, a_code = audit_lineage_chain(prod_id, self.admin_user)
        self.assertIsNone(a_err)
        self.assertEqual(a_code, 200)
        self.assertTrue(audit_res.get('chain_intact'))
        self.assertEqual(audit_res.get('integrity_status'), "VALIDATED")

        # 3. Vendor document verification
        sup_id = self.__class__.created_suppliers[0]
        v_res, v_err, v_code = verify_supplier_documents(sup_id, self.admin_user)
        self.assertIsNone(v_err)
        self.assertEqual(v_code, 200)
        self.assertTrue(v_res.get('verified'))

    def test_07_referential_integrity_and_cascade_prevention(self):
        """
        Verify referential integrity protections prevent orphaned records:
        - Product cannot be deleted while Batches reference it.
        - Material cannot be deleted while Batches reference it.
        - Supplier cannot be deleted while Materials reference it.
        """
        prod_id = self.__class__.created_products[0]
        mat_id = self.__class__.created_materials[0]
        sup_id = self.__class__.created_suppliers[0]

        # Attempt deleting Product -> must fail with 409
        ok, err, code = delete_product(prod_id, self.admin_user)
        self.assertFalse(ok)
        self.assertEqual(code, 409)

        # Attempt deleting Material -> must fail with 409
        ok, err, code = delete_material(mat_id, self.admin_user)
        self.assertFalse(ok)
        self.assertEqual(code, 409)

        # Attempt deleting Supplier -> must fail with 409
        ok, err, code = delete_supplier(sup_id, self.admin_user)
        self.assertFalse(ok)
        self.assertEqual(code, 409)

    def test_08_ordered_resource_deletion(self):
        """Verify successful deletion when dependencies are removed in correct reverse order."""
        comp_id = self.__class__.created_compliance.pop(0)
        batch_id = self.__class__.created_batches.pop(0)
        prod_id = self.__class__.created_products.pop(0)
        mat_id = self.__class__.created_materials.pop(0)
        sup_id = self.__class__.created_suppliers.pop(0)

        # 1. Delete compliance record
        c_ok, c_err, c_code = delete_compliance_record(comp_id, self.admin_user)
        self.assertTrue(c_ok)
        self.assertEqual(c_code, 200)
        self.assertIsNone(get_compliance_by_id(comp_id))

        # 2. Delete batch
        b_ok, b_err, b_code = delete_batch(batch_id, self.admin_user)
        self.assertTrue(b_ok)
        self.assertEqual(b_code, 200)
        self.assertIsNone(get_batch_by_id(batch_id))

        # 3. Product can now be deleted safely
        p_ok, p_err, p_code = delete_product(prod_id, self.admin_user)
        self.assertTrue(p_ok)
        self.assertEqual(p_code, 200)
        self.assertIsNone(get_product_by_id(prod_id))

        # 4. Material can now be deleted safely
        m_ok, m_err, m_code = delete_material(mat_id, self.admin_user)
        self.assertTrue(m_ok)
        self.assertEqual(m_code, 200)
        self.assertIsNone(get_material_by_id(mat_id))

        # 5. Supplier can now be deleted safely
        s_ok, s_err, s_code = delete_supplier(sup_id, self.admin_user)
        self.assertTrue(s_ok)
        self.assertEqual(s_code, 200)
        self.assertIsNone(get_supplier_by_id(sup_id))

    def test_09_user_crud(self):
        """Verify User CRUD, secure password hashing, and clean deletion in Firestore."""
        suffix = uuid.uuid4().hex[:6]
        user_email = f"test.user.{suffix}@sentineltrace.local"

        # 1. Create
        record, err, code = create_user(
            username=f"Test Auditor {suffix}",
            email=user_email,
            password="SecurePass123!#",
            role="Auditor",
            creator_user=self.admin_user
        )
        self.assertIsNone(err)
        self.assertEqual(code, 201)
        self.assertNotIn('password_hash', record)  # Password hash never leaked
        uid = record['user_id']
        self.__class__.created_users.append(uid)

        # 2. Read
        fetched = get_user_by_id(uid)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['email'], user_email)
        self.assertEqual(fetched['role'], "Auditor")

        # 3. Update
        updated, u_err, u_code = update_user(uid, {"status": "Suspended"}, self.admin_user)
        self.assertIsNone(u_err)
        self.assertEqual(u_code, 200)
        self.assertEqual(updated['status'], "Suspended")

        # 4. Delete
        d_ok, d_err, d_code = delete_user(uid, self.admin_user)
        self.assertTrue(d_ok)
        self.assertEqual(d_code, 200)
        self.assertIsNone(get_user_by_id(uid))
        self.__class__.created_users.remove(uid)

    def test_10_alert_lifecycle(self):
        """Verify Alert creation, reading, acknowledging, and cleanup in Firestore."""
        suffix = uuid.uuid4().hex[:6]
        alert_msg = f"Integration test alert observation {suffix}"

        # 1. Create alert
        alert = create_alert(
            severity="Notice",
            source="IntegrationTest",
            message=alert_msg,
            resource_id=f"RES-{suffix}"
        )
        self.assertIsNotNone(alert)
        aid = alert['alert_id']
        self.__class__.created_alerts.append(aid)

        # 2. Read alert
        fetched = get_alert_by_id(aid)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['message'], alert_msg)
        self.assertEqual(fetched['status'], "Active")

        # 3. Acknowledge alert
        updated, u_err = update_alert_action(
            alert_id=aid,
            action="Acknowledge",
            user_id=self.admin_user['user_id'],
            username=self.admin_user['username'],
            user_email="integ@test.local"
        )
        self.assertIsNone(u_err)
        self.assertEqual(updated['status'], "Acknowledged")

        # 4. Clean up test alert
        db.collection(Config.COLLECTION_ALERTS).document(aid).delete()
        self.assertIsNone(get_alert_by_id(aid))
        self.__class__.created_alerts.remove(aid)


if __name__ == '__main__':
    unittest.main()
