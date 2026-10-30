"""
Phase 3 Comprehensive Regression Test Suite for Sentinel-Trace
Verifies:
1. ID allocation after deletion (monotonic sequential allocation without reuse).
2. Duplicate-ID prevention and unique constraints.
3. Concurrent ID allocation (multi-threaded race-condition resistance).
4. Invalid relationship references (404 on missing foreign keys).
5. Deletion of referenced records (409 Conflict on products, materials, suppliers, sole admin, compliance auditors).
6. Existing record updates across all 6 entities without creating duplicates.
7. Unauthorized edit and delete requests (403 Forbidden).
8. Existing API compatibility and schema integrity.
"""

import sys
import os
import unittest
import concurrent.futures
from pathlib import Path

# Explicitly use local engine for hermetic test execution
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config.firebase import db
from config import Config
from services.id_service import allocate_sequential_id
from services.product_service import create_product, update_product, delete_product, get_product_by_id
from services.batch_service import create_batch, update_batch, delete_batch, get_batch_by_id
from services.material_service import create_material, update_material, delete_material, get_material_by_id
from services.supplier_service import create_supplier, update_supplier, delete_supplier, get_supplier_by_id
from services.compliance_service import create_compliance_record, update_compliance_record, delete_compliance_record, get_compliance_by_id
from services.auth_service import create_user, update_user, delete_user, get_user_by_id


class Phase3RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Seed hermetic database before tests
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def get_token(self, email="admin@sentineltrace.local", password="ChangeMe123!"):
        res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })
        data = res.get_json()
        if data.get('success') and 'data' in data:
            return data['data']['token']
        return None

    # -------------------------------------------------------------
    # 1. ID ALLOCATION AFTER DELETION
    # -------------------------------------------------------------
    def test_01_id_allocation_after_deletion(self):
        """Verify that deleting a record does NOT cause the next allocated ID to collide with or reuse deleted IDs."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        
        # Create a product
        prod1, err1, code1 = create_product({
            "product_name": "Allocation Probe Prod 1",
            "product_code": "PROBE-SKU-1",
            "description": "Probe 1 testing description",
            "status": "In Production"
        }, admin_user)
        self.assertIsNone(err1)
        id1 = prod1['product_id']
        num1 = int(id1.replace('PRD', ''))

        # Delete product 1
        del_ok, del_err, del_code = delete_product(id1, admin_user)
        self.assertTrue(del_ok)
        self.assertEqual(del_code, 200)

        # Create a second product
        prod2, err2, code2 = create_product({
            "product_name": "Allocation Probe Prod 2",
            "product_code": "PROBE-SKU-2",
            "description": "Probe 2 testing description",
            "status": "In Production"
        }, admin_user)
        self.assertIsNone(err2)
        id2 = prod2['product_id']
        num2 = int(id2.replace('PRD', ''))

        # The new ID MUST be strictly greater than num1, not num1 (no reuse of deleted ID)
        self.assertGreater(num2, num1, f"Expected monotonic ID growth: {id2} should be greater than {id1}")
        self.assertNotEqual(id1, id2)

        # Clean up prod2
        delete_product(id2, admin_user)

    # -------------------------------------------------------------
    # 2. DUPLICATE-ID PREVENTION & CONSTRAINTS
    # -------------------------------------------------------------
    def test_02_duplicate_product_code_prevention(self):
        """Verify that creating or updating a product with an existing product code returns 409 Conflict."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        
        # Product PRD101 has code TURB-A320-X in seeded data
        dup_prod, err, code = create_product({
            "product_name": "Duplicate Code Test",
            "product_code": "TURB-A320-X",
            "description": "Test duplicate code validation",
            "status": "In Production"
        }, admin_user)
        self.assertEqual(code, 409)
        self.assertIn("already exists", err.lower())

    def test_03_duplicate_email_user_prevention(self):
        """Verify that creating a user with an already registered email returns 409 Conflict."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        
        user, err, code = create_user(
            username="Duplicate Admin Clone",
            email="admin@sentineltrace.local",
            password="SomePassword123!",
            role="Admin",
            creator_user=admin_user
        )
        self.assertEqual(code, 409)
        self.assertIn("already exists", err.lower())

    # -------------------------------------------------------------
    # 3. CONCURRENT ID ALLOCATION
    # -------------------------------------------------------------
    def test_04_concurrent_id_allocation(self):
        """Verify multi-threaded ID allocation yields zero collisions and unique IDs."""
        num_threads = 12
        allocated_ids = []

        def worker():
            return allocate_sequential_id('suppliers')

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            for f in concurrent.futures.as_completed(futures):
                allocated_ids.append(f.result())

        self.assertEqual(len(allocated_ids), num_threads)
        unique_ids = set(allocated_ids)
        self.assertEqual(len(unique_ids), num_threads, f"Collision detected in concurrent allocation: {allocated_ids}")

    # -------------------------------------------------------------
    # 4. INVALID RELATIONSHIP REFERENCES (404 NOT FOUND)
    # -------------------------------------------------------------
    def test_05_batch_invalid_product_reference(self):
        """Creating a batch with non-existent product_id returns 404."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        batch, err, code = create_batch({
            "product_id": "PRD-NONEXISTENT-999",
            "material_id": "RM301",
            "quantity": 100
        }, admin_user)
        self.assertEqual(code, 404)
        self.assertIn("does not exist", err)

    def test_06_batch_invalid_material_reference(self):
        """Creating a batch with non-existent material_id returns 404."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        batch, err, code = create_batch({
            "product_id": "PRD101",
            "material_id": "RM-NONEXISTENT-999",
            "quantity": 100
        }, admin_user)
        self.assertEqual(code, 404)
        self.assertIn("does not exist", err)

    def test_07_material_invalid_supplier_reference(self):
        """Creating a material with non-existent supplier_id returns 404."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        mat, err, code = create_material({
            "material_name": "Titanium Carbonate",
            "supplier_id": "SUP-NONEXISTENT-999",
            "quantity": 50,
            "unit": "kg"
        }, admin_user)
        self.assertEqual(code, 404)
        self.assertIn("does not exist", err)

    def test_08_compliance_invalid_product_reference(self):
        """Creating a compliance record with non-existent product_id returns 404."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        comp, err, code = create_compliance_record({
            "product_id": "PRD-NONEXISTENT-999",
            "standard": "ISO 9001:2015",
            "status": "Compliant",
            "expiry_date": "2028-12-31"
        }, admin_user)
        self.assertEqual(code, 404)
        self.assertIn("does not exist", err)

    # -------------------------------------------------------------
    # 5. DELETION OF REFERENCED RECORDS (409 CONFLICT)
    # -------------------------------------------------------------
    def test_09_prevent_deletion_of_product_referenced_by_batch(self):
        """PRD101 is referenced by BAT201. Attempting to delete must return 409 Conflict."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        ok, err, code = delete_product("PRD101", admin_user)
        self.assertFalse(ok)
        self.assertEqual(code, 409)
        self.assertIn("linked production batches", err.lower())

    def test_10_prevent_deletion_of_product_referenced_by_compliance(self):
        """A product referenced by compliance records cannot be deleted (returns 409)."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        
        # Create unlinked product
        prod, _, _ = create_product({
            "product_name": "Compliance Linked Prod",
            "product_code": "COMP-LNK-01",
            "description": "Compliance linked product description",
            "status": "Certified"
        }, admin_user)
        pid = prod['product_id']

        # Link compliance record
        comp, _, _ = create_compliance_record({
            "product_id": pid,
            "standard": "RoHS",
            "status": "Compliant",
            "expiry_date": "2028-06-30"
        }, admin_user)
        cid = comp['compliance_id']

        # Try to delete product
        ok, err, code = delete_product(pid, admin_user)
        self.assertFalse(ok)
        self.assertEqual(code, 409)
        self.assertIn("compliance", err.lower())

        # Cleanup
        delete_compliance_record(cid, admin_user)
        delete_product(pid, admin_user)

    def test_11_prevent_deletion_of_material_referenced_by_batch(self):
        """RM301 is linked to BAT201. Deletion must return 409 Conflict."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        ok, err, code = delete_material("RM301", admin_user)
        self.assertFalse(ok)
        self.assertEqual(code, 409)
        self.assertIn("linked production batches", err.lower())

    def test_12_prevent_deletion_of_supplier_referenced_by_material(self):
        """SUP101 is linked to RM301. Deletion must return 409 Conflict."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        ok, err, code = delete_supplier("SUP101", admin_user)
        self.assertFalse(ok)
        self.assertEqual(code, 409)
        self.assertIn("linked raw materials", err.lower())

    def test_13_prevent_deletion_of_sole_active_admin(self):
        """The sole active Admin account cannot be deleted (returns 409). Self-deletion when multiple admins exist returns 400."""
        # Ensure only one active admin exists by deleting/suspending other admins
        active_admins = db.collection(Config.COLLECTION_USERS)\
                          .where('role', '==', 'Admin')\
                          .where('status', '==', 'Active')\
                          .get()
        other_admins = [a.id for a in active_admins if a.id != "USR-ADMIN01"]
        for o_id in other_admins:
            db.collection(Config.COLLECTION_USERS).document(o_id).update({"status": "Suspended"})

        admin_user = {"user_id": "USR-ADMIN01", "username": "Jack Mathew", "role": "Admin"}
        # Trying to delete the sole active admin USR-ADMIN01 must return 409
        ok, err, code = delete_user("USR-ADMIN01", admin_user)
        self.assertFalse(ok)
        self.assertEqual(code, 409)
        self.assertIn("sole active administrator", err.lower())

        # Restore other admins
        for o_id in other_admins:
            db.collection(Config.COLLECTION_USERS).document(o_id).update({"status": "Active"})

    def test_14_prevent_deletion_of_compliance_auditor_user(self):
        """A user account referenced as audited_by in compliance records cannot be deleted (returns 409)."""
        admin_user = {"user_id": "USR-ADMIN01", "username": "Jack Mathew", "role": "Admin"}
        
        # Create user
        auditor, _, _ = create_user(
            username="Dossier Auditor",
            email="dossier.auditor@sentineltrace.local",
            password="SecurePass123!#",
            role="Auditor",
            creator_user=admin_user
        )
        uid = auditor['user_id']

        # Create compliance record audited by this user
        comp, _, _ = create_compliance_record({
            "product_id": "PRD101",
            "standard": "GMP",
            "status": "Compliant",
            "expiry_date": "2027-11-20",
            "audited_by": uid
        }, admin_user)
        cid = comp['compliance_id']

        # Attempt to delete user
        ok, err, code = delete_user(uid, admin_user)
        self.assertFalse(ok)
        self.assertEqual(code, 409)
        self.assertIn("compliance records", err.lower())

        # Cleanup
        delete_compliance_record(cid, admin_user)
        delete_user(uid, admin_user)

    # -------------------------------------------------------------
    # 6. EXISTING RECORD UPDATES (NO DUPLICATES CREATED)
    # -------------------------------------------------------------
    def test_15_update_all_six_entities_in_place(self):
        """Verify in-place update for Product, Batch, Material, Supplier, Compliance, and User without creating duplicates."""
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Product PUT update
        res = self.client.put('/api/products/PRD102', headers=headers, json={
            "description": "Updated Medical Infusion Spec V2",
            "status": "Certified"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['data']['description'], "Updated Medical Infusion Spec V2")
        self.assertEqual(res.get_json()['data']['product_id'], "PRD102")

        # 2. Batch PUT update
        res = self.client.put('/api/batches/BAT202', headers=headers, json={
            "quantity": 420,
            "status": "In QA Inspection"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['data']['quantity'], 420)
        self.assertEqual(res.get_json()['data']['status'], "In QA Inspection")
        self.assertEqual(res.get_json()['data']['batch_id'], "BAT202")

        # 3. Material PUT update
        res = self.client.put('/api/materials/RM302', headers=headers, json={
            "quantity": 125.5
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['data']['quantity'], 125.5)
        self.assertEqual(res.get_json()['data']['material_id'], "RM302")

        # 4. Supplier PUT update
        res = self.client.put('/api/suppliers/SUP102', headers=headers, json={
            "contact": "Senior Metallurgist VP"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['data']['contact'], "Senior Metallurgist VP")
        self.assertEqual(res.get_json()['data']['supplier_id'], "SUP102")

        # 5. Compliance PUT update
        res = self.client.put('/api/compliance/CMP402', headers=headers, json={
            "status": "Compliant",
            "remarks": "Audited with calibrated XRF spectrometer"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['data']['status'], "Compliant")
        self.assertEqual(res.get_json()['data']['compliance_id'], "CMP402")

        # 6. User PUT update
        res = self.client.put('/api/admin/users/USR-INSPECT01', headers=headers, json={
            "username": "Sarah Connor Chief QA"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['data']['username'], "Sarah Connor Chief QA")
        self.assertEqual(res.get_json()['data']['user_id'], "USR-INSPECT01")

    # -------------------------------------------------------------
    # 7. UNAUTHORIZED EDIT AND DELETE REQUESTS (403 FORBIDDEN)
    # -------------------------------------------------------------
    def test_16_unauthorized_edit_and_delete_roles(self):
        """Verify that unauthorized roles receive 403 Forbidden on restricted PUT and DELETE operations."""
        op_token = self.get_token("operator@sentineltrace.local", "ChangeMe123!")
        op_headers = {"Authorization": f"Bearer {op_token}"}
        
        insp_token = self.get_token("inspector@sentineltrace.local", "ChangeMe123!")
        insp_headers = {"Authorization": f"Bearer {insp_token}"}

        # Operator cannot delete products (Admin or Inspector required)
        res = self.client.delete('/api/products/PRD102', headers=op_headers)
        self.assertEqual(res.status_code, 403)

        # Operator cannot delete batches (Admin or Inspector required)
        res = self.client.delete('/api/batches/BAT202', headers=op_headers)
        self.assertEqual(res.status_code, 403)

        # Inspector cannot delete suppliers (Admin required)
        res = self.client.delete('/api/suppliers/SUP102', headers=insp_headers)
        self.assertEqual(res.status_code, 403)

        # Inspector cannot delete compliance records (Admin required)
        res = self.client.delete('/api/compliance/CMP402', headers=insp_headers)
        self.assertEqual(res.status_code, 403)

        # Inspector cannot edit or delete users (Admin required)
        res = self.client.put('/api/admin/users/USR-INSPECT01', headers=insp_headers, json={"role": "Admin"})
        self.assertEqual(res.status_code, 403)

        res = self.client.delete('/api/admin/users/USR-INSPECT01', headers=insp_headers)
        self.assertEqual(res.status_code, 403)

    # -------------------------------------------------------------
    # 8. API COMPATIBILITY & SCHEMA VERIFICATION
    # -------------------------------------------------------------
    def test_17_api_compatibility_schema(self):
        """Verify API schema integrity across entities."""
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Products
        res = self.client.get('/api/products', headers=headers)
        self.assertEqual(res.status_code, 200)
        items = res.get_json()['data']
        self.assertGreaterEqual(len(items), 1)
        self.assertIn('product_id', items[0])
        self.assertIn('product_name', items[0])
        self.assertIn('product_code', items[0])

        # Batches
        res = self.client.get('/api/batches', headers=headers)
        self.assertEqual(res.status_code, 200)
        items = res.get_json()['data']
        self.assertGreaterEqual(len(items), 1)
        self.assertIn('batch_id', items[0])
        self.assertIn('product_id', items[0])
        self.assertIn('material_id', items[0])

        # Materials
        res = self.client.get('/api/materials', headers=headers)
        self.assertEqual(res.status_code, 200)
        items = res.get_json()['data']
        self.assertGreaterEqual(len(items), 1)
        self.assertIn('material_id', items[0])
        self.assertIn('material_name', items[0])
        self.assertIn('supplier_id', items[0])

        # Suppliers
        res = self.client.get('/api/suppliers', headers=headers)
        self.assertEqual(res.status_code, 200)
        items = res.get_json()['data']
        self.assertGreaterEqual(len(items), 1)
        self.assertIn('supplier_id', items[0])
        self.assertIn('supplier_name', items[0])

        # Compliance
        res = self.client.get('/api/compliance', headers=headers)
        self.assertEqual(res.status_code, 200)
        items = res.get_json()['data']
        self.assertGreaterEqual(len(items), 1)
        self.assertIn('compliance_id', items[0])
        self.assertIn('standard', items[0])

        # Users
        res = self.client.get('/api/admin/users', headers=headers)
        self.assertEqual(res.status_code, 200)
        items = res.get_json()['data']
        self.assertGreaterEqual(len(items), 1)
        self.assertIn('user_id', items[0])
        self.assertIn('email', items[0])
        self.assertNotIn('password_hash', items[0])


if __name__ == '__main__':
    unittest.main()
