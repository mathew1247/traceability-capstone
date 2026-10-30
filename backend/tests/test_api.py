import sys
import unittest
import json
from pathlib import Path

import os
# Explicitly use local engine for automated unit test execution
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from seed import seed_database
from unittest.mock import patch

class SentinelTraceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Seed database before running tests
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def get_auth_token(self, email="admin@sentineltrace.local", password="ChangeMe123!"):
        res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })
        data = res.get_json()
        if data.get('success') and 'data' in data:
            return data['data']['token']
        return None

    # 1. Health check
    def test_01_health_check(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('status'), 'healthy')

    # 2. Login & JWT
    def test_02_login_valid(self):
        token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        self.assertIsNotNone(token)

    def test_03_login_invalid(self):
        res = self.client.post('/api/auth/login', json={
            "email": "admin@sentineltrace.local",
            "password": "WrongPassword999!"
        })
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data.get('success'))

    # 3. RBAC checks
    def test_04_rbac_operator_restricted_from_users(self):
        token = self.get_auth_token("operator@sentineltrace.local", "ChangeMe123!")
        res = self.client.get('/api/users', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)

    def test_05_rbac_admin_allowed_users(self):
        token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        res = self.client.get('/api/users', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertIsInstance(data.get('data'), list)

    # 4. Supplier CRUD
    def test_06_supplier_crud(self):
        token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        # CREATE
        create_res = self.client.post('/api/suppliers', headers=headers, json={
            "supplier_name": "Test Metalworks Corp",
            "contact": "John Foreman",
            "email": "jforeman@testmetal.com",
            "address": "10 Foundry Road"
        })
        self.assertEqual(create_res.status_code, 201)
        created = create_res.get_json()['data']
        sup_id = created['supplier_id']

        # READ ONE
        get_res = self.client.get(f'/api/suppliers/{sup_id}', headers=headers)
        self.assertEqual(get_res.status_code, 200)

        # UPDATE
        update_res = self.client.put(f'/api/suppliers/{sup_id}', headers=headers, json={
            "contact": "Jane Foreman"
        })
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.get_json()['data']['contact'], "Jane Foreman")

        # DELETE
        del_res = self.client.delete(f'/api/suppliers/{sup_id}', headers=headers)
        self.assertEqual(del_res.status_code, 200)

    # 5. Raw Material CRUD & Supplier Verification
    def test_07_material_supplier_verification(self):
        token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt create with invalid supplier ID
        bad_res = self.client.post('/api/materials', headers=headers, json={
            "material_name": "Ghost Alloy",
            "supplier_id": "SUP_NONEXISTENT_999",
            "quantity": 100,
            "unit": "Kg"
        })
        self.assertEqual(bad_res.status_code, 404)

        # Create with valid supplier SUP101
        good_res = self.client.post('/api/materials', headers=headers, json={
            "material_name": "Certified Beryllium Copper Bar",
            "supplier_id": "SUP101",
            "quantity": 250,
            "unit": "Kg"
        })
        self.assertEqual(good_res.status_code, 201)
        mat_id = good_res.get_json()['data']['material_id']

        # Clean up
        self.client.delete(f'/api/materials/{mat_id}', headers=headers)

    # 6. Product CRUD & Unique Code Verification
    def test_08_product_unique_code(self):
        token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt create with duplicate code TURB-A320-X
        dup_res = self.client.post('/api/products', headers=headers, json={
            "product_name": "Duplicate Turbine",
            "product_code": "TURB-A320-X",
            "description": "Should fail",
            "status": "In Production"
        })
        self.assertEqual(dup_res.status_code, 409)

        # Create with unique code
        ok_res = self.client.post('/api/products', headers=headers, json={
            "product_name": "Titanium Cryo Valve",
            "product_code": "CRYO-VALVE-77",
            "description": "Cryogenic fuel line valve assembly.",
            "status": "In Production"
        })
        self.assertEqual(ok_res.status_code, 201)
        prod_id = ok_res.get_json()['data']['product_id']

        # Clean up
        self.client.delete(f'/api/products/{prod_id}', headers=headers)

    # 7. Batch Relation Verification
    def test_09_batch_relation_check(self):
        token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        # Invalid product_id
        res = self.client.post('/api/batches', headers=headers, json={
            "product_id": "PRD_INVALID",
            "material_id": "RM301",
            "quantity": 50
        })
        self.assertEqual(res.status_code, 404)

        # Valid create
        valid_res = self.client.post('/api/batches', headers=headers, json={
            "product_id": "PRD101",
            "material_id": "RM301",
            "quantity": 50
        })
        self.assertEqual(valid_res.status_code, 201)
        batch_id = valid_res.get_json()['data']['batch_id']

        # Clean up
        self.client.delete(f'/api/batches/{batch_id}', headers=headers)

    # 8. Compliance & Expiry Alert Trigger
    def test_10_compliance_crud_and_alert(self):
        token = self.get_auth_token("inspector@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        # Create expiring compliance record
        res = self.client.post('/api/compliance', headers=headers, json={
            "product_id": "PRD101",
            "standard": "GMP",
            "status": "Review Required",
            "remarks": "Expiring quickly in test scenario",
            "expiry_date": "2026-10-15"
        })
        self.assertEqual(res.status_code, 201)
        cmp_id = res.get_json()['data']['compliance_id']

        # Clean up
        admin_token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        self.client.delete(f'/api/compliance/{cmp_id}', headers={"Authorization": f"Bearer {admin_token}"})

    # 9. Traceability Graph Query
    def test_11_traceability_lineage(self):
        token = self.get_auth_token("operator@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        res = self.client.get('/api/traceability/BAT201', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['data']
        self.assertEqual(data['matched_entity_type'], 'ProductionBatch')
        self.assertIsNotNone(data['traceability']['product'])
        self.assertIsNotNone(data['traceability']['material'])
        self.assertIsNotNone(data['traceability']['supplier'])

    # 10. Dashboard Stats
    def test_12_dashboard_stats(self):
        token = self.get_auth_token("operator@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        res = self.client.get('/api/dashboard/stats', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['data']
        self.assertIn('total_products', data)
        self.assertIn('total_batches', data)
        self.assertIn('compliance_rate', data)
        self.assertIn('network_status', data)

    # 11. Alerts Lifecycle
    def test_13_alerts_lifecycle(self):
        token = self.get_auth_token("inspector@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        res = self.client.get('/api/alerts', headers=headers)
        self.assertEqual(res.status_code, 200)
        alerts = res.get_json()['data']
        self.assertIsInstance(alerts, list)

        if alerts:
            first_id = alerts[0]['alert_id']
            # Acknowledge
            ack_res = self.client.put(f'/api/alerts/{first_id}', headers=headers, json={"action": "Acknowledge"})
            self.assertEqual(ack_res.status_code, 200)
            self.assertEqual(ack_res.get_json()['data']['status'], "Acknowledged")

    # 12. Network Target Validation & Mocked Nmap Scan
    def test_14_network_target_security_rules(self):
        token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt scan on arbitrary Internet IP (e.g. 8.8.8.8) -> must reject with 400!
        ext_res = self.client.post('/api/network/scan', headers=headers, json={"target": "8.8.8.8"})
        self.assertEqual(ext_res.status_code, 400)
        self.assertIn("prohibited", ext_res.get_json()['error']['message'].lower())

        # Attempt scan with invalid subnet syntax
        inv_res = self.client.post('/api/network/scan', headers=headers, json={"target": "not-an-ip"})
        self.assertEqual(inv_res.status_code, 400)

        # Mocked Nmap scan against authorized loopback
        with patch('services.network_service.scan_network') as mock_scan:
            mock_scan.return_value = ({
                "target": "127.0.0.1",
                "devices_found": 1,
                "hosts": [{"ip": "127.0.0.1", "status": "up", "ports": [{"port": 5000, "protocol": "tcp", "service": "http", "state": "open"}]}],
                "scanner_engine": "Mocked Test Engine"
            }, None)

            scan_res = self.client.post('/api/network/scan', headers=headers, json={"target": "127.0.0.1"})
            self.assertEqual(scan_res.status_code, 201)
            self.assertTrue(scan_res.get_json()['success'])

    # 13. Reports & Analytics Summary
    def test_15_reports_summary(self):
        token = self.get_auth_token("auditor@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        res = self.client.get('/api/reports/summary', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['data']
        self.assertIn('production', data)
        self.assertIn('compliance', data)
        self.assertIn('network', data)
        self.assertIn('alerts', data)

    # 14. Activity Logs
    def test_16_activity_logs(self):
        token = self.get_auth_token("auditor@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        res = self.client.get('/api/logs', headers=headers)
        self.assertEqual(res.status_code, 200)
        logs = res.get_json()['data']
        self.assertIsInstance(logs, list)

    # 15. Audit Lineage Chain Validation
    def test_17_audit_lineage_chain(self):
        token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        # Valid product lineage audit
        res = self.client.post('/api/traceability/PRD101/audit', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['data']
        self.assertEqual(data['query_id'], 'PRD101')
        self.assertIn('integrity_status', data)
        self.assertGreater(data['nodes_verified'], 0)

        # Non-existent identifier
        err_res = self.client.post('/api/traceability/NONEXISTENT999/audit', headers=headers)
        self.assertEqual(err_res.status_code, 404)

        # Unauthenticated request rejected
        unauth_res = self.client.post('/api/traceability/PRD101/audit')
        self.assertEqual(unauth_res.status_code, 401)

    # 16. Verify Supplier Documents Against Records
    def test_18_verify_supplier_documents(self):
        admin_token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Valid supplier with real records
        res = self.client.get('/api/suppliers/SUP101/verify-documents', headers=admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()['data']
        self.assertEqual(data['supplier_id'], 'SUP101')
        self.assertIn('verified', data)
        self.assertIn('message', data)

        # Non-existent supplier
        not_found = self.client.get('/api/suppliers/SUP9999/verify-documents', headers=admin_headers)
        self.assertEqual(not_found.status_code, 404)

        # Role restriction: Operator cannot verify vendor documents
        op_token = self.get_auth_token("operator@sentineltrace.local", "ChangeMe123!")
        op_res = self.client.get('/api/suppliers/SUP101/verify-documents', headers={"Authorization": f"Bearer {op_token}"})
        self.assertEqual(op_res.status_code, 403)

    # 17. Clear All Notices Preserves Unrelated Alerts & History
    def test_19_clear_all_notices_preserves_unrelated_alerts(self):
        token = self.get_auth_token("admin@sentineltrace.local", "ChangeMe123!")
        headers = {"Authorization": f"Bearer {token}"}

        # Create Notice alert
        n_res = self.client.post('/api/alerts', headers=headers, json={
            "severity": "Notice",
            "source": "System",
            "message": "Routine maintenance notice test"
        })
        self.assertEqual(n_res.status_code, 201)
        notice_id = n_res.get_json()['data']['alert_id']

        # Create Critical alert (must NOT be cleared by Clear Notices)
        c_res = self.client.post('/api/alerts', headers=headers, json={
            "severity": "Critical",
            "source": "Security",
            "message": "Critical intrusion prevention test"
        })
        self.assertEqual(c_res.status_code, 201)
        critical_id = c_res.get_json()['data']['alert_id']

        # Execute Clear All Notices
        clear_res = self.client.post('/api/alerts/clear-notices', headers=headers)
        self.assertEqual(clear_res.status_code, 200)
        self.assertGreaterEqual(clear_res.get_json()['data']['cleared_count'], 1)

        # Check Notice alert was dismissed
        chk_notice = self.client.get(f'/api/alerts/{notice_id}', headers=headers)
        self.assertEqual(chk_notice.get_json()['data']['status'], 'Dismissed')

        # Check Critical alert was PRESERVED as Active
        chk_crit = self.client.get(f'/api/alerts/{critical_id}', headers=headers)
        self.assertEqual(chk_crit.get_json()['data']['status'], 'Active')

    # 18. Password Recovery & Cryptographic Reset
    def test_20_password_recovery_and_reset(self):
        # Request password reset for existing inspector
        email = "inspector@sentineltrace.local"
        forgot_res = self.client.post('/api/auth/forgot-password', json={"email": email})
        self.assertEqual(forgot_res.status_code, 200)
        data = forgot_res.get_json()['data']
        self.assertTrue(data['dispatched'])
        reset_token = data.get('token')
        self.assertIsNotNone(reset_token)

        # Request reset with invalid email format rejected with 400
        inv_res = self.client.post('/api/auth/forgot-password', json={"email": "not-valid-email"})
        self.assertEqual(inv_res.status_code, 400)

        # Reset password using token
        new_pass = "UpdatedSecurePass999!"
        reset_res = self.client.post('/api/auth/reset-password', json={
            "token": reset_token,
            "new_password": new_pass
        })
        self.assertEqual(reset_res.status_code, 200)

        # Authenticate with new password
        login_res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": new_pass
        })
        self.assertEqual(login_res.status_code, 200)

        # Old password must now be rejected
        old_login_res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": "ChangeMe123!"
        })
        self.assertEqual(old_login_res.status_code, 401)

    # 19. Firebase Configuration and Safe Diagnostics
    def test_21_firebase_diagnostic(self):
        diag_res = self.client.get('/api/diagnostic/firebase')
        # Diagnostic should return 200 or 503 depending on live connectivity, but always valid structure
        self.assertIn(diag_res.status_code, (200, 503))
        payload = diag_res.get_json()
        self.assertIn('data', payload)
        diag = payload['data']
        self.assertEqual(diag.get('configured_project_id'), 'capstone-8ee41')
        # Confirm no private keys or credentials leaked
        diag_str = str(payload)
        self.assertNotIn('private_key', diag_str)
        self.assertNotIn('client_email', diag_str)
        self.assertNotIn('BEGIN PRIVATE KEY', diag_str)

if __name__ == '__main__':
    unittest.main()
