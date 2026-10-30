"""
Phase 2 Functional Reliability & Data Integrity: Task 1 Regression Test Suite
Verifies:
1. Batch creation deducts raw material inventory.
2. Batch creation rejects requests exceeding available stock (prevents negative inventory).
3. Batch creation rejects zero, negative, or invalid quantities.
4. Batch creation rejects unit mismatches.
5. Concurrent batch creation uses thread locking to strictly prevent overspending.
6. Batch quantity updates adjust inventory (increases deduct additional; decreases restore).
7. Batch quantity increases exceeding stock are rejected without partial changes.
8. Switching materials on a batch restores stock to old material and deducts from new material.
9. Deleting active/pending/failed batches restores allocated inventory.
10. Deleting completed batches preserves consumption without double-crediting inventory.
11. Idempotent requests avoid duplicate stock deductions on retry.
"""

import sys
import os
import unittest
import concurrent.futures
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
from services.material_service import create_material, get_material_by_id
from services.batch_service import create_batch, update_batch, delete_batch, get_batch_by_id


class InventoryIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.admin_user = {"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}

    def setUp(self):
        # Create fresh unique isolated material & product for each test
        import uuid
        test_uid = uuid.uuid4().hex[:6].upper()
        
        prod, _, _ = create_product({
            "product_name": f"Test Turbine {test_uid}",
            "product_code": f"TURB-{test_uid}",
            "description": "Inventory Test Unit",
            "status": "In Production"
        }, self.admin_user)
        self.product_id = prod['product_id']

        mat, _, _ = create_material({
            "material_name": f"Test Alloy {test_uid}",
            "supplier_id": "SUP101",
            "quantity": 500.0,
            "unit": "Kg"
        }, self.admin_user)
        self.material_id = mat['material_id']

    # 1. Successful Batch Creation Deducts Inventory
    def test_01_batch_creation_deducts_material_inventory(self):
        batch, err, code = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 120,
            "status": "Running"
        }, self.admin_user)

        self.assertEqual(code, 201)
        self.assertIsNone(err)
        self.assertEqual(batch['allocated_material_qty'], 120)

        # Verify material was deducted: 500 - 120 = 380
        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 380.0)

    # 2. Rejection When Stock Is Insufficient
    def test_02_batch_creation_rejects_insufficient_stock(self):
        # Current stock is 500. Attempt to allocate 600.
        batch, err, code = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 600,
            "status": "Running"
        }, self.admin_user)

        self.assertEqual(code, 400)
        self.assertIsNone(batch)
        self.assertIn("Insufficient inventory", err)

        # Verify stock was untouched
        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 500.0)

    # 3. Invalid Quantities (Zero and Negative)
    def test_03_batch_creation_rejects_zero_or_negative_quantity(self):
        for bad_qty in [0, -10, "invalid"]:
            batch, err, code = create_batch({
                "product_id": self.product_id,
                "material_id": self.material_id,
                "quantity": bad_qty
            }, self.admin_user)
            self.assertEqual(code, 400)
            self.assertIsNone(batch)

        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 500.0)

    # 4. Unit Compatibility Check
    def test_04_batch_creation_rejects_unit_mismatch(self):
        batch, err, code = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 50,
            "unit": "Liters"  # Material is Kg
        }, self.admin_user)

        self.assertEqual(code, 400)
        self.assertIn("Unit mismatch", err)

        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 500.0)

    # 5. Concurrent Overspend Prevention
    def test_05_concurrent_batch_creation_prevents_overspend(self):
        """
        Stock is 100. 5 concurrent requests try to allocate 40 units each (demand = 200).
        Exactly 2 must succeed, 3 must be rejected with 400.
        Remaining stock must be exactly 20 (never negative).
        """
        mat, _, _ = create_material({
            "material_name": "Concurrent Overspend Test Material",
            "supplier_id": "SUP101",
            "quantity": 100.0,
            "unit": "Kg"
        }, self.admin_user)
        m_id = mat['material_id']

        results = []

        def worker(idx):
            return create_batch({
                "product_id": self.product_id,
                "material_id": m_id,
                "quantity": 40,
                "status": "Running"
            }, self.admin_user)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        successes = [r for r in results if r[2] == 201]
        rejections = [r for r in results if r[2] == 400]

        self.assertEqual(len(successes), 2, "Exactly 2 batches of 40 should succeed on 100 stock.")
        self.assertEqual(len(rejections), 3, "Remaining 3 batches should be rejected.")

        # Verify final stock is exactly 100 - (2 * 40) = 20
        final_mat = get_material_by_id(m_id)
        self.assertEqual(final_mat['quantity'], 20.0)

    # 6. Batch Quantity Updates Adjust Inventory
    def test_06_batch_update_quantity_adjusts_inventory(self):
        # Create initial batch with 100 units (stock drops 500 -> 400)
        batch, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 100
        }, self.admin_user)
        b_id = batch['batch_id']

        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 400.0)

        # Increase batch quantity from 100 to 150 (extra 50 needed -> stock drops 400 -> 350)
        updated, err, code = update_batch(b_id, {"quantity": 150}, self.admin_user)
        self.assertEqual(code, 200)
        self.assertEqual(updated['quantity'], 150)
        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 350.0)

        # Decrease batch quantity from 150 to 80 (70 returned -> stock increases 350 -> 420)
        updated, err, code = update_batch(b_id, {"quantity": 80}, self.admin_user)
        self.assertEqual(code, 200)
        self.assertEqual(updated['quantity'], 80)
        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 420.0)

    # 7. Quantity Increase Exceeding Available Stock Rejected
    def test_07_batch_update_quantity_exceeding_stock_rejected(self):
        # Reduce material stock to 30
        db.collection(Config.COLLECTION_RAW_MATERIALS).document(self.material_id).update({"quantity": 30.0})

        batch, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 20
        }, self.admin_user)
        b_id = batch['batch_id']
        # Stock is now 10

        # Attempt to increase batch by 50 (from 20 to 70). Needs 50, but only 10 available.
        updated, err, code = update_batch(b_id, {"quantity": 70}, self.admin_user)
        self.assertEqual(code, 400)
        self.assertIn("Insufficient inventory", err)

        # Verify stock and batch quantity remain unchanged
        mat = get_material_by_id(self.material_id)
        self.assertEqual(mat['quantity'], 10.0)
        b_doc = get_batch_by_id(b_id)
        self.assertEqual(b_doc['quantity'], 20)

    # 8. Material Transfer / Switch on Batch Update
    def test_08_batch_update_material_switch_transfers_stock(self):
        # Create second material with 200.0
        mat_b, _, _ = create_material({
            "material_name": "Alternative Alloy B",
            "supplier_id": "SUP101",
            "quantity": 200.0,
            "unit": "Kg"
        }, self.admin_user)
        m_b_id = mat_b['material_id']

        # Batch created with 100 on material A (A drops 500 -> 400)
        batch, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 100
        }, self.admin_user)
        b_id = batch['batch_id']

        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 400.0)
        self.assertEqual(get_material_by_id(m_b_id)['quantity'], 200.0)

        # Switch batch material to Material B
        updated, err, code = update_batch(b_id, {"material_id": m_b_id}, self.admin_user)
        self.assertEqual(code, 200)

        # Material A gets 100 back (400 -> 500)
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 500.0)
        # Material B has 100 deducted (200 -> 100)
        self.assertEqual(get_material_by_id(m_b_id)['quantity'], 100.0)

    # 9. Active Batch Deletion Restores Stock
    def test_09_batch_deletion_restores_active_stock(self):
        # Create batch of 60 (stock drops 500 -> 440)
        batch, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 60,
            "status": "Running"
        }, self.admin_user)
        b_id = batch['batch_id']
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 440.0)

        # Delete active batch
        ok, err, code = delete_batch(b_id, self.admin_user)
        self.assertTrue(ok)

        # Stock is restored back to 500
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 500.0)

    # 10. Completed Batch Deletion Does Not Double-Credit Stock
    def test_10_completed_batch_deletion_preserves_consumption(self):
        # Create batch of 50 (stock drops 500 -> 450)
        batch, _, _ = create_batch({
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 50,
            "status": "Running"
        }, self.admin_user)
        b_id = batch['batch_id']

        # Update batch to Completed
        update_batch(b_id, {"status": "Completed"}, self.admin_user)

        # Delete completed batch
        ok, _, code = delete_batch(b_id, self.admin_user)
        self.assertTrue(ok)

        # Stock remains consumed at 450 (not credited back)
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 450.0)

    # 11. Idempotent Retry Avoids Double Deduction
    def test_11_idempotent_retry_avoids_duplicate_deduction(self):
        import uuid
        key = f"IDEM-{uuid.uuid4().hex[:8]}"
        payload = {
            "product_id": self.product_id,
            "material_id": self.material_id,
            "quantity": 80,
            "idempotency_key": key
        }

        # First request
        batch1, err1, code1 = create_batch(payload, self.admin_user)
        self.assertEqual(code1, 201)
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 420.0)

        # Retry request with same idempotency key
        batch2, err2, code2 = create_batch(payload, self.admin_user)
        self.assertEqual(code2, 200)
        self.assertEqual(batch2['batch_id'], batch1['batch_id'])

        # Stock must NOT be deducted again
        self.assertEqual(get_material_by_id(self.material_id)['quantity'], 420.0)


if __name__ == '__main__':
    unittest.main()
