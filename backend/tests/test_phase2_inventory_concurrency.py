"""
Phase 2 Functional Reliability & Data Integrity: Task Concurrency & Stock Integrity
File: backend/tests/test_phase2_inventory_concurrency.py

Comprehensive regression test suite verifying:
1. Normal valid stock deduction
2. Stock deduction exceeding available stock (preventing overspend)
3. Prevention of negative inventory (negative quantity, over-deduction)
4. Competing concurrent deductions against limited stock
5. Concurrent updates to the same batch (eliminating delta corruption & inventory leakage)
6. Duplicate submission behaviour (idempotent request handling)
7. Batch deletion and dependent record protection (active vs completed, material referential check)
8. Multi-document transaction atomicity (all-or-nothing on failure)
9. Consistency between batch quantities and calculated inventory totals
10. Invalid or nonexistent product/material references
11. Audit logging behaviour for successful vs failed operations
12. RBAC enforcement for stock-changing endpoints
"""

import sys
import os
import uuid
import unittest
import concurrent.futures
from unittest.mock import patch, MagicMock
from pathlib import Path

# Use local Firestore mock for hermetic testing
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config.firebase import db
from config import Config
from services.product_service import create_product
from services.material_service import create_material, get_material_by_id, delete_material
from services.batch_service import create_batch, update_batch, delete_batch, get_batch_by_id
from services.dashboard_service import get_dashboard_metrics


class InventoryConcurrencyAndIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        cls.operator_user = {"user_id": "USR-OP01", "username": "Operator", "role": "Operator"}
        cls.auditor_user = {"user_id": "USR-AUDIT01", "username": "Auditor", "role": "Auditor"}

    def get_token(self, email, password):
        res = self.client.post('/api/auth/login', json={"email": email, "password": password})
        self.assertEqual(res.status_code, 200, f"Login failed for {email}: {res.get_data(as_text=True)}")
        data = res.get_json()
        return data.get('token') or data.get('data', {}).get('token')

    def setUp(self):
        # Create fresh unique isolated material & product for each test
        test_uid = uuid.uuid4().hex[:6].upper()
        
        prod, _, _ = create_product({
            "product_name": f"Concurrency Turbine {test_uid}",
            "product_code": f"TURB-CC-{test_uid}",
            "description": "Concurrency & Stock Integrity Test Unit",
            "status": "In Production"
        }, self.admin_user)
        self.product_id = prod['product_id']

        mat, _, _ = create_material({
            "material_name": f"Concurrency Alloy {test_uid}",
            "supplier_id": "SUP101",
            "quantity": 500.0,
            "unit": "Kg"
        }, self.admin_user)
        self.material_id = mat['material_id']

    # -------------------------------------------------------------
    # 1. NORMAL VALID STOCK DEDUCTION
    # -------------------------------------------------------------
    def test_01_normal_valid_stock_deduction(self):
        mat_before = get_material_by_id(self.material_id)
        self.assertEqual(mat_before['quantity'], 500.0)

        batch, err, code = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 150,
            "status": "Running"
        }, self.admin_user)

        self.assertEqual(code, 201)
        self.assertIsNone(err)
        self.assertEqual(batch['allocated_material_qty'], 150)
        self.assertEqual(batch['quantity'], 150)

        # Verify stock was deducted: 500 - 150 = 350
        mat_after = get_material_by_id(self.material_id)
        self.assertEqual(mat_after['quantity'], 350.0)

    # -------------------------------------------------------------
    # 2. DEDUCTION EXCEEDING AVAILABLE STOCK
    # -------------------------------------------------------------
    def test_02_deduction_exceeding_available_stock_rejected(self):
        # Current stock is 500. Attempt to allocate 550.
        batch, err, code = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 550,
            "status": "Running"
        }, self.admin_user)

        self.assertEqual(code, 400)
        self.assertIsNone(batch)
        self.assertIn("Insufficient inventory", err)

        # Verify stock remains completely untouched
        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 500.0)

    # -------------------------------------------------------------
    # 3. PREVENTION OF NEGATIVE INVENTORY
    # -------------------------------------------------------------
    def test_03_prevention_of_negative_inventory(self):
        # 1. Negative batch quantity creation
        batch, err, code = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": -25
        }, self.admin_user)
        self.assertEqual(code, 400)
        self.assertIsNone(batch)

        # 2. Negative batch quantity update
        b_init, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 50
        }, self.admin_user)
        up_b, up_err, up_code = update_batch(b_init['batch_id'], {"quantity": -10}, self.admin_user)
        self.assertEqual(up_code, 400)
        self.assertIsNone(up_b)

        # 3. Direct negative material quantity update
        from services.material_service import update_material
        up_m, m_err, m_code = update_material(self.material_id, {"quantity": -50.0}, self.admin_user)
        self.assertEqual(m_code, 400)
        self.assertIsNone(up_m)

        # Stock must remain positive and intact (500 - 50 = 450)
        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 450.0)

    # -------------------------------------------------------------
    # 4. COMPETING DEDUCTIONS AGAINST LIMITED STOCK
    # -------------------------------------------------------------
    def test_04_competing_deductions_against_limited_stock(self):
        # Create a material with exactly 100 units
        mat, _, _ = create_material({
            "material_name": "Limited Stock Alloy",
            "supplier_id": "SUP101",
            "quantity": 100.0,
            "unit": "Kg"
        }, self.admin_user)
        m_id = mat['material_id']

        # 4 concurrent requests try to allocate 40 units each (total demand = 160 on 100 stock)
        results = []
        def worker(idx):
            return create_batch({
                "product_id": self.product_id,
                "material_id": m_id,
                "quantity": 40,
                "status": "Running"
            }, self.admin_user)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker, i) for i in range(4)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        successes = [r for r in results if r[2] == 201]
        rejections = [r for r in results if r[2] == 400]

        self.assertEqual(len(successes), 2, "Only 2 allocations of 40 can succeed on 100 stock")
        self.assertEqual(len(rejections), 2, "Remaining 2 allocations must be rejected")

        # Remaining stock must be exactly 100 - (2 * 40) = 20.0
        final_mat = get_material_by_id(m_id)
        self.assertEqual(final_mat['quantity'], 20.0)

    # -------------------------------------------------------------
    # 5. CONCURRENT UPDATES TO THE SAME BATCH
    # -------------------------------------------------------------
    def test_05_concurrent_updates_to_same_batch(self):
        # Create batch with 100 units (stock drops 500 -> 400)
        batch, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 100,
            "status": "Running"
        }, self.admin_user)
        b_id = batch['batch_id']

        # Two competing updates: one to 150 (demand +50), one to 120 (demand +20)
        def worker_update(new_qty):
            return update_batch(b_id, {"quantity": new_qty}, self.admin_user)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker_update, 150)
            f2 = executor.submit(worker_update, 120)
            res1 = f1.result()
            res2 = f2.result()

        self.assertEqual(res1[2], 200)
        self.assertEqual(res2[2], 200)

        # Inspect final state: the material stock must EXACTLY equal initial (500) minus final batch quantity
        final_batch = get_batch_by_id(b_id)
        final_qty = final_batch['quantity']
        self.assertIn(final_qty, (120, 150))

        final_mat = get_material_by_id(self.material_id)
        expected_stock = round(500.0 - final_qty, 4)
        self.assertEqual(final_mat['quantity'], expected_stock, "No inventory leakage on concurrent updates")

    # -------------------------------------------------------------
    # 6. DUPLICATE SUBMISSION / IDEMPOTENCY BEHAVIOUR
    # -------------------------------------------------------------
    def test_06_duplicate_submission_idempotency(self):
        idem_key = f"IDEM-CONCUR-{uuid.uuid4().hex[:8]}"
        payload = {
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 75,
            "idempotency_key": idem_key
        }

        # Submit first request
        b1, err1, code1 = create_batch(payload, self.admin_user)
        self.assertEqual(code1, 201)
        self.assertIsNotNone(b1)
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 425.0)

        # Concurrent or immediate duplicate replay with same idempotency key
        b2, err2, code2 = create_batch(payload, self.admin_user)
        self.assertEqual(code2, 200)
        self.assertEqual(b2['batch_id'], b1['batch_id'])

        # Stock must NOT be deducted again (still 425.0)
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 425.0)

    # -------------------------------------------------------------
    # 7. BATCH DELETION AND DEPENDENT RECORD PROTECTION
    # -------------------------------------------------------------
    def test_07_batch_deletion_and_material_dependent_records(self):
        # 1. Active batch deletion restores stock
        batch, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 80,
            "status": "Running"
        }, self.admin_user)
        b_id = batch['batch_id']
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 420.0)

        ok, _, code = delete_batch(b_id, self.admin_user)
        self.assertTrue(ok)
        self.assertEqual(code, 200)
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 500.0)

        # 2. Completed batch deletion does not refund stock
        b_comp, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 60,
            "status": "Running"
        }, self.admin_user)
        b_comp_id = b_comp['batch_id']
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 440.0)

        update_batch(b_comp_id, {"status": "Completed"}, self.admin_user)
        ok2, _, _ = delete_batch(b_comp_id, self.admin_user)
        self.assertTrue(ok2)
        # Stock remains at 440.0
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 440.0)

        # 3. Material deletion blocked when linked batches exist
        b_linked, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 40
        }, self.admin_user)
        ok3, err3, code3 = delete_material(self.material_id, self.admin_user)
        self.assertFalse(ok3)
        self.assertEqual(code3, 409)
        self.assertIn("Linked production batches exist", err3)

    # -------------------------------------------------------------
    # 8. FAILURE DURING MULTI-DOCUMENT TRANSACTION (ATOMICTY)
    # -------------------------------------------------------------
    def test_08_failure_during_multidoc_operation_rolls_back(self):
        mat_before = get_material_by_id(self.material_id)['quantity']

        # Simulate unexpected database write failure during batch commit
        with patch.object(db, 'transaction') as mock_tx_factory:
            mock_tx = MagicMock()
            mock_tx.commit.side_effect = Exception("Simulated Firestore commit failure")
            mock_tx_factory.return_value = mock_tx

            batch, err, code = create_batch({
                "product_id": self.product_id,
                "material_id": self.material_id,
                "quantity": 100
            }, self.admin_user)

            self.assertEqual(code, 500)
            self.assertIsNone(batch)
            self.assertIn("Failed to create batch", err)

        # Verify material quantity was not modified
        mat_after = get_material_by_id(self.material_id)['quantity']
        self.assertEqual(mat_before, mat_after)

    # -------------------------------------------------------------
    # 9. CONSISTENCY BETWEEN BATCH QUANTITIES AND INVENTORY TOTALS
    # -------------------------------------------------------------
    def test_09_consistency_between_batches_and_dashboard_totals(self):
        metrics_before = get_dashboard_metrics()
        initial_units = metrics_before['total_units_produced']
        initial_mat_qty = metrics_before['total_material_quantity']

        # Create two batches
        b1, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 100
        }, self.admin_user)
        b2, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 150
        }, self.admin_user)

        metrics_mid = get_dashboard_metrics()
        self.assertEqual(metrics_mid['total_units_produced'], initial_units + 250)
        self.assertEqual(round(metrics_mid['total_material_quantity'], 2), round(initial_mat_qty - 250, 2))

        # Adjust one batch from 150 to 90 (60 units refunded)
        update_batch(b2['batch_id'], {"quantity": 90}, self.admin_user)

        metrics_after = get_dashboard_metrics()
        self.assertEqual(metrics_after['total_units_produced'], initial_units + 190)
        self.assertEqual(round(metrics_after['total_material_quantity'], 2), round(initial_mat_qty - 190, 2))

    # -------------------------------------------------------------
    # 10. INVALID OR NONEXISTENT REFERENCES
    # -------------------------------------------------------------
    def test_10_invalid_or_nonexistent_references_rejected(self):
        # 1. Nonexistent product ID
        b, err, code = create_batch({
            "product_id": "PRD-NONEXISTENT-999",
            "material_id": self.material_id,
            "quantity": 50
        }, self.admin_user)
        self.assertEqual(code, 404)
        self.assertIn("does not exist", err)

        # 2. Nonexistent material ID
        b2, err2, code2 = create_batch({
            "product_id": self.product_id,
            "material_id": "RM-NONEXISTENT-999",
            "quantity": 50
        }, self.admin_user)
        self.assertEqual(code2, 404)
        self.assertIn("does not exist", err2)

        # 3. Update with nonexistent product
        b_valid, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 50
        }, self.admin_user)
        u1, uerr1, ucode1 = update_batch(b_valid['batch_id'], {"product_id": "PRD-MISSING"}, self.admin_user)
        self.assertEqual(ucode1, 404)

        # 4. Update with nonexistent material
        u2, uerr2, ucode2 = update_batch(b_valid['batch_id'], {"material_id": "RM-MISSING"}, self.admin_user)
        self.assertEqual(ucode2, 404)

    # -------------------------------------------------------------
    # 11. AUDIT BEHAVIOUR FOR SUCCESSFUL AND FAILED OPERATIONS
    # -------------------------------------------------------------
    def test_11_audit_behaviour_for_successful_and_failed_operations(self):
        # Successful batch creation creates audit entry
        b, _, code = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 45
        }, self.admin_user)
        self.assertEqual(code, 201)

        logs = db.collection(Config.COLLECTION_ACTIVITY_LOGS).where('resource_id', '==', b['batch_id']).get()
        create_logs = [l.to_dict() for l in logs if l.to_dict().get('action') == 'CREATE']
        self.assertEqual(len(create_logs), 1)
        self.assertIn("deducted 45", create_logs[0]['details'])

        # Failed batch creation (insufficient stock) must NOT log a CREATE entry claiming success
        initial_log_count = len(db.collection(Config.COLLECTION_ACTIVITY_LOGS).get())
        b_fail, _, code_fail = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 99999
        }, self.admin_user)
        self.assertEqual(code_fail, 400)
        self.assertIsNone(b_fail)

        final_logs = db.collection(Config.COLLECTION_ACTIVITY_LOGS).get()
        # No phantom CREATE audit log was written for the failed operation
        phantom_logs = [
            l.to_dict() for l in final_logs
            if l.to_dict().get('action') == 'CREATE' and "99999" in l.to_dict().get('details', '')
        ]
        self.assertEqual(len(phantom_logs), 0)

    # -------------------------------------------------------------
    # 12. RBAC ENFORCEMENT FOR STOCK-CHANGING ENDPOINTS
    # -------------------------------------------------------------
    def test_12_rbac_enforcement_for_stock_endpoints(self):
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        inspector_token = self.get_token("sarah.chen@sentineltrace.io", "password123")

        # 1. Unauthenticated request rejected with 401
        res = self.client.post('/api/batches', json={
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 10
        })
        self.assertEqual(res.status_code, 401)

        # 2. Operator token allows batch creation and update, but forbids delete
        operator_token = self.get_token("operator@sentineltrace.local", "ChangeMe123!")
        headers_op = {"Authorization": f"Bearer {operator_token}"}

        # Operator can create batch
        res_op_create = self.client.post('/api/batches', headers=headers_op, json={
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 15
        })
        self.assertEqual(res_op_create.status_code, 201)
        created_b_id = res_op_create.get_json()['data']['batch_id']

        # Operator can update batch
        res_op_update = self.client.put(f'/api/batches/{created_b_id}', headers=headers_op, json={
            "quantity": 20
        })
        self.assertEqual(res_op_update.status_code, 200)

        # Operator CANNOT delete batch (Admin & Inspector only)
        res_op_delete = self.client.delete(f'/api/batches/{created_b_id}', headers=headers_op)
        self.assertEqual(res_op_delete.status_code, 403)

        # 3. Auditor CANNOT create or update batches (read-only audit role)
        auditor_token = self.get_token("auditor@sentineltrace.local", "ChangeMe123!")
        headers_aud = {"Authorization": f"Bearer {auditor_token}"}

        res_aud_create = self.client.post('/api/batches', headers=headers_aud, json={
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 10
        })
        self.assertEqual(res_aud_create.status_code, 403)

        # 4. Admin CAN delete batch
        headers_adm = {"Authorization": f"Bearer {admin_token}"}
        res_adm_delete = self.client.delete(f'/api/batches/{created_b_id}', headers=headers_adm)
        self.assertEqual(res_adm_delete.status_code, 200)


if __name__ == '__main__':
    unittest.main()
