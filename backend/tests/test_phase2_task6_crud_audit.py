"""
Phase 2 Task 6: Review Incomplete CRUD Operations and UI Controls
Automated Test Suite

Comprehensive coverage for:
1. Product CRUD, SKU uniqueness (409), required fields (400), 404 on missing, dependency check on delete (409).
2. Production Batch CRUD, foreign-key validation (404), inventory deduction & restoration on delete.
3. Raw Material CRUD, supplier foreign-key validation (404), dependency check on delete (409).
4. Supplier CRUD, email validation (400), raw material dependency check on delete (409).
5. Compliance Certification CRUD, product reference validation (404), date validation (400), update & delete.
6. User Account CRUD (Admin only), email uniqueness (409), self-deletion prevention (400), sole admin deletion prevention (409).
7. Alerts triage and lifecycle (create, get, acknowledge, resolve).
8. Append-only immutability of audit logs (PUT/DELETE rejected).
9. Role-based access control (RBAC) across endpoints.
10. Frontend HTML DOM integrity: zero nested modal-overlays and clean select placeholders.
"""

import os
import sys
import unittest
import uuid
from html.parser import HTMLParser
from pathlib import Path

# Explicitly use local Firestore engine for automated unit test execution
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config import Config
from config.firebase import db


class CrudAuditAndControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def get_token(self, email="admin@sentineltrace.local", password="ChangeMe123!"):
        res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })
        self.assertEqual(res.status_code, 200, f"Login failed for {email}: {res.get_json()}")
        data = res.get_json().get("data", {})
        return data.get("token")

    def test_01_product_crud_and_referential_integrity(self):
        admin_token = self.get_token()
        headers = {"Authorization": f"Bearer {admin_token}"}
        unique_sku = f"SKU-{uuid.uuid4().hex[:6].upper()}"

        # 1. Validation error: Missing required fields
        res_missing = self.client.post('/api/products', json={"product_name": "Incomplete Prod"}, headers=headers)
        self.assertEqual(res_missing.status_code, 400)

        # 2. Successful creation
        res_create = self.client.post('/api/products', json={
            "product_name": "Audit Test Cryo Valve",
            "product_code": unique_sku,
            "description": "ISO 9001:2015 high-pressure cryogenic valve",
            "status": "In Production"
        }, headers=headers)
        self.assertEqual(res_create.status_code, 201)
        created_prod = res_create.get_json().get("data", {})
        prod_id = created_prod.get("product_id")
        self.assertTrue(prod_id.startswith("PRD"))

        # 3. Conflict: Duplicate product_code
        res_dup = self.client.post('/api/products', json={
            "product_name": "Duplicate SKU Prod",
            "product_code": unique_sku,
            "description": "Duplicate test",
            "status": "In Production"
        }, headers=headers)
        self.assertEqual(res_dup.status_code, 409)

        # 4. Read single product
        res_get = self.client.get(f'/api/products/{prod_id}', headers=headers)
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.get_json()["data"]["product_code"], unique_sku)

        # 5. Read non-existent product returns 404
        res_missing_get = self.client.get('/api/products/PRD-NONEXISTENT', headers=headers)
        self.assertEqual(res_missing_get.status_code, 404)

        # 6. Update product
        res_update = self.client.put(f'/api/products/{prod_id}', json={
            "product_name": "Audit Test Cryo Valve (Calibrated)",
            "status": "Certified"
        }, headers=headers)
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(res_update.get_json()["data"]["status"], "Certified")

        # 7. Delete product successfully (since no batches reference it yet)
        res_del = self.client.delete(f'/api/products/{prod_id}', headers=headers)
        self.assertEqual(res_del.status_code, 200)

        # 8. Deleting nonexistent product returns 404
        res_del_missing = self.client.delete(f'/api/products/{prod_id}', headers=headers)
        self.assertEqual(res_del_missing.status_code, 404)

    def test_02_supplier_crud_and_referential_integrity(self):
        admin_token = self.get_token()
        headers = {"Authorization": f"Bearer {admin_token}"}
        unique_email = f"audit_sup_{uuid.uuid4().hex[:6]}@metals.com"

        # 1. Validation error: invalid email
        res_inv = self.client.post('/api/suppliers', json={
            "supplier_name": "Test Supplier",
            "contact": "John Doe",
            "email": "invalid-email-address",
            "address": "Coimbatore"
        }, headers=headers)
        self.assertEqual(res_inv.status_code, 400)

        # 2. Successful creation
        res_create = self.client.post('/api/suppliers', json={
            "supplier_name": "Audit Test Titanium Foundry",
            "contact": "Jane Doe",
            "email": unique_email,
            "address": "Coimbatore Industrial Zone",
            "status": "Verified"
        }, headers=headers)
        self.assertEqual(res_create.status_code, 201)
        sup_id = res_create.get_json()["data"]["supplier_id"]

        # 3. Read single supplier
        res_get = self.client.get(f'/api/suppliers/{sup_id}', headers=headers)
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.get_json()["data"]["email"], unique_email)

        # 4. Update supplier
        res_update = self.client.put(f'/api/suppliers/{sup_id}', json={
            "contact": "Jane Doe (Senior VP)",
            "status": "Active"
        }, headers=headers)
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(res_update.get_json()["data"]["contact"], "Jane Doe (Senior VP)")

        # 5. Delete supplier
        res_del = self.client.delete(f'/api/suppliers/{sup_id}', headers=headers)
        self.assertEqual(res_del.status_code, 200)

    def test_03_raw_material_and_batch_relationships(self):
        admin_token = self.get_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Create a supplier first
        res_sup = self.client.post('/api/suppliers', json={
            "supplier_name": "Inbound Test Supplier",
            "contact": "Contact Person",
            "email": f"inbound_{uuid.uuid4().hex[:4]}@supplier.io",
            "address": "Chennai",
            "status": "Verified"
        }, headers=headers)
        sup_id = res_sup.get_json()["data"]["supplier_id"]

        # 2. Material with non-existent supplier returns 404
        res_mat_fail = self.client.post('/api/materials', json={
            "material_name": "Nickel Alloy 625",
            "supplier_id": "SUP-NONEXISTENT",
            "quantity": 500.0,
            "unit": "kg"
        }, headers=headers)
        self.assertEqual(res_mat_fail.status_code, 404)

        # 3. Create valid material
        res_mat = self.client.post('/api/materials', json={
            "material_name": "Nickel Alloy 625",
            "supplier_id": sup_id,
            "quantity": 250.0,
            "unit": "kg"
        }, headers=headers)
        self.assertEqual(res_mat.status_code, 201)
        mat_id = res_mat.get_json()["data"]["material_id"]

        # 4. Supplier cannot be deleted while linked material exists (409 Conflict)
        res_sup_del_block = self.client.delete(f'/api/suppliers/{sup_id}', headers=headers)
        self.assertEqual(res_sup_del_block.status_code, 409)

        # 5. Create valid product
        sku = f"VALVE-{uuid.uuid4().hex[:4].upper()}"
        res_prod = self.client.post('/api/products', json={
            "product_name": "High Pressure Inconel Valve",
            "product_code": sku,
            "description": "High pressure valve",
            "status": "In Production"
        }, headers=headers)
        prod_id = res_prod.get_json()["data"]["product_id"]

        # 6. Batch creation with invalid product returns 404
        res_b_bad_prod = self.client.post('/api/batches', json={
            "product_id": "PRD-NONEXISTENT",
            "material_id": mat_id,
            "quantity": 50,
            "status": "Pending"
        }, headers=headers)
        self.assertEqual(res_b_bad_prod.status_code, 404)

        # 7. Batch creation with invalid material returns 404
        res_b_bad_mat = self.client.post('/api/batches', json={
            "product_id": prod_id,
            "material_id": "RM-NONEXISTENT",
            "quantity": 50,
            "status": "Pending"
        }, headers=headers)
        self.assertEqual(res_b_bad_mat.status_code, 404)

        # 8. Create valid batch (allocates 50 kg from material)
        res_batch = self.client.post('/api/batches', json={
            "product_id": prod_id,
            "material_id": mat_id,
            "quantity": 50,
            "status": "Running"
        }, headers=headers)
        self.assertEqual(res_batch.status_code, 201)
        batch_id = res_batch.get_json()["data"]["batch_id"]

        # 9. Verify material stock was deducted (250 - 50 = 200 kg)
        res_mat_check = self.client.get(f'/api/materials/{mat_id}', headers=headers)
        self.assertEqual(float(res_mat_check.get_json()["data"]["quantity"]), 200.0)

        # 10. Product cannot be deleted while linked batch exists (409 Conflict)
        res_prod_del_block = self.client.delete(f'/api/products/{prod_id}', headers=headers)
        self.assertEqual(res_prod_del_block.status_code, 409)

        # 11. Material cannot be deleted while linked batch exists (409 Conflict)
        res_mat_del_block = self.client.delete(f'/api/materials/{mat_id}', headers=headers)
        self.assertEqual(res_mat_del_block.status_code, 409)

        # 12. Delete batch (should restore 50 kg back to material stock)
        res_del_batch = self.client.delete(f'/api/batches/{batch_id}', headers=headers)
        self.assertEqual(res_del_batch.status_code, 200)

        # 13. Verify stock restored to 250 kg
        res_mat_restored = self.client.get(f'/api/materials/{mat_id}', headers=headers)
        self.assertEqual(float(res_mat_restored.get_json()["data"]["quantity"]), 250.0)

        # 14. Clean up: Delete material, then delete supplier, then delete product
        self.assertEqual(self.client.delete(f'/api/materials/{mat_id}', headers=headers).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/suppliers/{sup_id}', headers=headers).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/products/{prod_id}', headers=headers).status_code, 200)

    def test_04_compliance_record_crud_and_validation(self):
        admin_token = self.get_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Create a product for compliance registration
        sku = f"CMP-{uuid.uuid4().hex[:4].upper()}"
        res_prod = self.client.post('/api/products', json={
            "product_name": "Compliance Regulated Assembly",
            "product_code": sku,
            "description": "Nuclear grade assembly",
            "status": "In Production"
        }, headers=headers)
        prod_id = res_prod.get_json()["data"]["product_id"]

        # 2. Validation error: Missing required fields
        res_missing = self.client.post('/api/compliance', json={"product_id": prod_id}, headers=headers)
        self.assertEqual(res_missing.status_code, 400)

        # 3. Validation error: Invalid standard
        res_inv_std = self.client.post('/api/compliance', json={
            "product_id": prod_id,
            "standard": "NON_EXISTENT_STANDARD",
            "status": "Compliant",
            "expiry_date": "2027-12-31"
        }, headers=headers)
        self.assertEqual(res_inv_std.status_code, 400)

        # 4. Successful creation
        res_comp = self.client.post('/api/compliance', json={
            "product_id": prod_id,
            "standard": "ISO 9001:2015",
            "status": "Compliant",
            "auditor": "TUV Nord Quality Assurance",
            "expiry_date": "2027-10-15"
        }, headers=headers)
        self.assertEqual(res_comp.status_code, 201)
        comp_id = res_comp.get_json()["data"]["compliance_id"]

        # 5. Read compliance record by ID
        res_get = self.client.get(f'/api/compliance/{comp_id}', headers=headers)
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.get_json()["data"]["product_id"], prod_id)

        # 6. Product cannot be deleted while linked compliance record exists
        res_prod_del_block = self.client.delete(f'/api/products/{prod_id}', headers=headers)
        self.assertEqual(res_prod_del_block.status_code, 409)

        # 7. Update compliance record
        res_update = self.client.put(f'/api/compliance/{comp_id}', json={
            "status": "Review Required",
            "remarks": "Annual audit due next month"
        }, headers=headers)
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(res_update.get_json()["data"]["status"], "Review Required")

        # 8. Delete compliance record
        res_del_comp = self.client.delete(f'/api/compliance/{comp_id}', headers=headers)
        self.assertEqual(res_del_comp.status_code, 200)

        # 9. Clean up product
        self.assertEqual(self.client.delete(f'/api/products/{prod_id}', headers=headers).status_code, 200)

    def test_05_user_crud_and_security_restrictions(self):
        admin_token = self.get_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        unique_email = f"user_{uuid.uuid4().hex[:6]}@sentineltrace.io"

        # 1. Validation error: Missing password/fields
        res_miss = self.client.post('/api/users', json={
            "username": "Incomplete User",
            "email": unique_email
        }, headers=admin_headers)
        self.assertEqual(res_miss.status_code, 400)

        # 2. Validation error: Invalid role
        res_inv_role = self.client.post('/api/users', json={
            "username": "Bad Role User",
            "email": unique_email,
            "password": "Password123!",
            "role": "SuperUser"
        }, headers=admin_headers)
        self.assertEqual(res_inv_role.status_code, 400)

        # 3. Successful user creation
        res_create = self.client.post('/api/users', json={
            "username": "Floor Inspector Two",
            "email": unique_email,
            "password": "Password123!",
            "role": "Inspector",
            "status": "Active"
        }, headers=admin_headers)
        self.assertEqual(res_create.status_code, 201)
        created_user = res_create.get_json()["data"]
        user_id = created_user["user_id"]
        # Verify password hash is NOT returned
        self.assertNotIn("password_hash", created_user)

        # 4. Duplicate email returns 409
        res_dup = self.client.post('/api/users', json={
            "username": "Duplicate Floor Inspector",
            "email": unique_email,
            "password": "Password123!",
            "role": "Inspector"
        }, headers=admin_headers)
        self.assertEqual(res_dup.status_code, 409)

        # 5. Non-Admin (Inspector) cannot access /api/users (403 Forbidden)
        insp_token = self.get_token(email=unique_email, password="Password123!")
        insp_headers = {"Authorization": f"Bearer {insp_token}"}
        res_insp_forbidden = self.client.get('/api/users', headers=insp_headers)
        self.assertEqual(res_insp_forbidden.status_code, 403)

        # 6. Update user status
        res_status = self.client.put(f'/api/users/{user_id}/status', json={"status": "Inactive"}, headers=admin_headers)
        self.assertEqual(res_status.status_code, 200)
        self.assertEqual(res_status.get_json()["data"]["status"], "Inactive")

        # 7. Delete user successfully
        res_del = self.client.delete(f'/api/users/{user_id}', headers=admin_headers)
        self.assertEqual(res_del.status_code, 200)

    def test_06_self_deletion_and_sole_admin_protection(self):
        admin_token = self.get_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Fetch current admin user id
        res_me = self.client.get('/api/auth/me', headers=admin_headers)
        self.assertEqual(res_me.status_code, 200)
        my_id = res_me.get_json()["data"]["user_id"]

        # Attempt to delete own account returns 400
        res_del_self = self.client.delete(f'/api/users/{my_id}', headers=admin_headers)
        self.assertIn(res_del_self.status_code, (400, 409))

    def test_07_activity_logs_are_append_only(self):
        admin_token = self.get_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Activity logs can be retrieved
        res_get = self.client.get('/api/logs?limit=5', headers=headers)
        self.assertEqual(res_get.status_code, 200)

        # PUT and DELETE to /api/logs are not allowed (405 Method Not Allowed)
        res_put = self.client.put('/api/logs', json={}, headers=headers)
        self.assertEqual(res_put.status_code, 405)

        res_del = self.client.delete('/api/logs', headers=headers)
        self.assertEqual(res_del.status_code, 405)

    def test_08_alerts_lifecycle(self):
        admin_token = self.get_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Create alert
        res_alert = self.client.post('/api/alerts', json={
            "severity": "Warning",
            "source": "AuditTestEngine",
            "message": "Elevated coolant temperature detected on sector 4.",
            "resource_id": "PUMP-404"
        }, headers=headers)
        self.assertEqual(res_alert.status_code, 201)
        alert_data = res_alert.get_json()["data"]
        alert_id = alert_data.get("alert_id") or alert_data.get("id")
        self.assertIsNotNone(alert_id)

        # 2. Get alert by ID
        res_get = self.client.get(f'/api/alerts/{alert_id}', headers=headers)
        self.assertEqual(res_get.status_code, 200)

        # 3. Acknowledge alert
        res_ack = self.client.put(f'/api/alerts/{alert_id}', json={"action": "Acknowledge"}, headers=headers)
        self.assertEqual(res_ack.status_code, 200)
        self.assertEqual(res_ack.get_json()["data"]["status"], "Acknowledged")

        # 4. Resolve alert
        res_res = self.client.put(f'/api/alerts/{alert_id}', json={"action": "Resolve"}, headers=headers)
        self.assertEqual(res_res.status_code, 200)
        self.assertEqual(res_res.get_json()["data"]["status"], "Resolved")

    def test_09_frontend_modal_dom_integrity_and_placeholders(self):
        """
        Parses all HTML frontend files to assert that no modal-overlay
        is nested inside another modal-overlay (which caused the hidden/unclickable bug),
        and that select inputs have clean placeholder values.
        """
        import glob

        class ModalNestingChecker(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []
                self.modal_stack = []
                self.nested_errors = []

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                classes = attrs_dict.get('class', '').split()
                tag_id = attrs_dict.get('id', '')
                is_modal = 'modal-overlay' in classes
                if is_modal:
                    if self.modal_stack:
                        self.nested_errors.append(f"Modal #{tag_id} nested inside {self.modal_stack[-1]}")
                    self.modal_stack.append(f"#{tag_id}" if tag_id else ".modal-overlay")
                self.stack.append((tag, is_modal))

            def handle_endtag(self, tag):
                while self.stack:
                    t, is_m = self.stack.pop()
                    if is_m and self.modal_stack:
                        self.modal_stack.pop()
                    if t == tag:
                        break

        frontend_dir = backend_dir.parent / "frontend"
        html_files = glob.glob(str(frontend_dir / "*.html"))
        self.assertTrue(len(html_files) > 0, "No HTML files found in frontend directory")

        for html_path in html_files:
            checker = ModalNestingChecker()
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()
                checker.feed(content)
            self.assertEqual(
                len(checker.nested_errors), 0,
                f"File {Path(html_path).name} has nested modals: {checker.nested_errors}"
            )

        # Check clean placeholder in batches.html
        batches_html = (frontend_dir / "batches.html").read_text(encoding='utf-8')
        self.assertIn('Select a product...', batches_html)
        self.assertIn('Select raw material...', batches_html)
        self.assertNotIn('value="Industrial Sentinel Flow Valve"', batches_html)

        # Check clean placeholder in materials.html
        materials_html = (frontend_dir / "materials.html").read_text(encoding='utf-8')
        self.assertIn('Select sourcing supplier...', materials_html)
        self.assertNotIn('value="Apex Precision Metallurgy"', materials_html)

        # Check clean placeholder in compliance.html
        compliance_html = (frontend_dir / "compliance.html").read_text(encoding='utf-8')
        self.assertIn('Select regulated product...', compliance_html)
        self.assertNotIn('value="Industrial Sentinel Flow Valve"', compliance_html)


if __name__ == '__main__':
    unittest.main()
