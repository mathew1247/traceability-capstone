"""
Phase 1 Security & Bug Fixes Regression Test Suite for Sentinel-Trace
Verifies:
1. Task 1 (P0): SMTP Environment Variable Vulnerability Prevention
   - Request-controlled data cannot mutate os.environ['SMTP_PASSWORD']
   - Unauthenticated requests to /api/alerts/test-email return 401
   - Non-admin users (e.g., Operator) are rejected with 403
   - Admin receives 503 SMTP_NOT_CONFIGURED when server credentials are unset
   - Responses and logs never leak SMTP credentials
2. Task 2 (P1): Batch Status Update NameError Fix
   - Valid batch status updates succeed with HTTP 200
   - Invalid batch status updates return HTTP 400 validation error (no 500 NameError)
3. Task 3 (P1): Production Cryptographic Secret Enforcement
   - Production startup raises RuntimeError if SECRET_KEY or JWT_SECRET_KEY is missing or insecure default
   - Startup error messages never expose secret values
   - Development and test mode function normally with safe fallbacks
4. Task 4 (P1): Prevention of Insecure Default Accounts in Production
   - ensure_default_admin_users() is a no-op in production mode
   - Default accounts with predictable passwords are not seeded in production
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Explicitly use local mock Firestore engine for hermetic tests
os.environ.setdefault('USE_LOCAL_FIRESTORE', 'true')

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config import Config
from config.firebase import db
from services.batch_service import create_batch, update_batch
from services.auth_service import ensure_default_admin_users, create_user


class Phase1SecurityFixesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure fresh seeded test data in local simulator
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def get_token(self, email="admin@sentineltrace.local", password="ChangeMe123!"):
        res = self.client.post('/api/auth/login', json={
            "email": email,
            "password": password
        })
        data = res.get_json()
        if data and data.get('success') and 'data' in data:
            return data['data']['token']
        return None

    # =========================================================================
    # TASK 1: SMTP ENVIRONMENT VARIABLE VULNERABILITY PREVENTION (P0)
    # =========================================================================
    def test_01_smtp_env_cannot_be_overwritten_by_request(self):
        """Test that submitting app_password or SMTP_PASSWORD in request never mutates os.environ."""
        original_smtp_pass = os.environ.get('SMTP_PASSWORD')
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")
        self.assertIsNotNone(admin_token)

        malicious_payload = {
            "recipient": "attacker@external.test",
            "app_password": "malicious_injected_password_12345",
            "smtp_password": "malicious_injected_password_67890",
            "SMTP_PASSWORD": "malicious_injected_password_abcde"
        }

        # Issue POST request to test-email endpoint
        res = self.client.post(
            '/api/alerts/test-email',
            headers={"Authorization": f"Bearer {admin_token}"},
            json=malicious_payload
        )

        # Verify os.environ['SMTP_PASSWORD'] remained completely untouched
        current_smtp_pass = os.environ.get('SMTP_PASSWORD')
        self.assertEqual(current_smtp_pass, original_smtp_pass)
        self.assertNotIn("malicious_injected_password", str(current_smtp_pass))

        # Check response body never leaks the injected or server secrets
        response_text = res.get_data(as_text=True)
        self.assertNotIn("malicious_injected_password", response_text)

    def test_02_test_email_unauthenticated_rejected(self):
        """Unauthenticated requests to test-email must return 401 Unauthorized."""
        res = self.client.post('/api/alerts/test-email', json={"recipient": "test@test.com"})
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data.get('success'))

    def test_03_test_email_unauthorized_role_rejected(self):
        """Non-Admin roles (e.g. Operator, Inspector) must be rejected with 403 Forbidden."""
        # Create an Operator user
        create_user(
            username="Line Operator 01",
            email="operator01@sentineltrace.local",
            password="Password123!",
            role="Operator",
            creator_user={"user_id": "USR-ADMIN01", "username": "Admin", "role": "Admin"}
        )
        operator_token = self.get_token("operator01@sentineltrace.local", "Password123!")
        self.assertIsNotNone(operator_token)

        res = self.client.post(
            '/api/alerts/test-email',
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"recipient": "test@test.com"}
        )
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertFalse(data.get('success'))
        error_info = data.get('error', {})
        self.assertEqual(error_info.get('code'), 'FORBIDDEN_INSUFFICIENT_ROLE')

    def test_04_test_email_admin_unconfigured_smtp_returns_503(self):
        """When SMTP is not configured in server environment, admin request returns safe 503."""
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")

        # Ensure SMTP_PASSWORD is not set in environment or config
        with patch.dict(os.environ, {"SMTP_PASSWORD": ""}, clear=False):
            with patch.object(Config, 'SMTP_PASSWORD', None):
                res = self.client.post(
                    '/api/alerts/test-email',
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"recipient": "audit@sentineltrace.io"}
                )
                self.assertEqual(res.status_code, 503)
                data = res.get_json()
                self.assertFalse(data.get('success'))
                error_info = data.get('error', {})
                self.assertEqual(error_info.get('code'), 'SMTP_NOT_CONFIGURED')
                self.assertIn("SMTP service is not configured", error_info.get('message', ''))

    # =========================================================================
    # TASK 2: BATCH STATUS UPDATE NAMEERROR FIX (P1)
    # =========================================================================
    def test_05_batch_status_invalid_returns_400_no_nameerror(self):
        """Updating a batch with an invalid status returns 400 validation error, not 500 NameError."""
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")

        # Update batch BAT201 with invalid status
        res = self.client.put(
            '/api/batches/BAT201',
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "INVALID_BATCH_STATUS_XYZ"}
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get('success'))
        error_info = data.get('error', {})
        self.assertEqual(error_info.get('code'), 'UPDATE_BATCH_FAILED')
        self.assertIn("Invalid batch status", error_info.get('message', ''))
        # Ensure error message mentions valid statuses cleanly
        self.assertIn("Completed", error_info.get('message', ''))

    def test_06_batch_status_valid_updates_succeed(self):
        """Updating a batch with valid statuses ('Running', 'In QA Inspection', 'Passed') succeeds."""
        admin_token = self.get_token("admin@sentineltrace.local", "ChangeMe123!")

        for valid_st in ['Running', 'In QA Inspection', 'Passed', 'Completed', 'Failed', 'Pending']:
            res = self.client.put(
                '/api/batches/BAT201',
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"status": valid_st}
            )
            self.assertEqual(res.status_code, 200, f"Failed updating to valid status: {valid_st}")
            data = res.get_json()
            self.assertTrue(data.get('success'))
            self.assertEqual(data['data']['status'], valid_st)

    # =========================================================================
    # TASK 3: SECURE PRODUCTION CRYPTOGRAPHIC SECRETS (P1)
    # =========================================================================
    def test_07_production_mode_fails_fast_on_missing_or_default_secrets(self):
        """In production mode, missing or default fallback secrets raise RuntimeError on startup."""
        # 1. Missing SECRET_KEY in production
        with patch.object(Config, 'ENV', 'production'), \
             patch.object(Config, 'is_prod', True), \
             patch.object(Config, 'SECRET_KEY', None), \
             patch.object(Config, 'JWT_SECRET_KEY', 'valid-production-jwt-secret-key-12345'):
            with self.assertRaises(RuntimeError) as ctx:
                create_app()
            self.assertIn("SECRET_KEY is missing or set to an insecure default", str(ctx.exception))
            # Verify secret values are never printed
            self.assertNotIn("valid-production-jwt-secret-key-12345", str(ctx.exception))

        # 2. Hardcoded fallback SECRET_KEY in production
        with patch.object(Config, 'ENV', 'production'), \
             patch.object(Config, 'is_prod', True), \
             patch.object(Config, 'SECRET_KEY', 'sentinel-trace-prod-secret-key-2026'), \
             patch.object(Config, 'JWT_SECRET_KEY', 'valid-production-jwt-secret-key-12345'):
            with self.assertRaises(RuntimeError) as ctx:
                create_app()
            self.assertIn("SECRET_KEY is missing or set to an insecure default", str(ctx.exception))

        # 3. Missing JWT_SECRET_KEY in production
        with patch.object(Config, 'ENV', 'production'), \
             patch.object(Config, 'is_prod', True), \
             patch.object(Config, 'SECRET_KEY', 'valid-production-flask-secret-key-67890'), \
             patch.object(Config, 'JWT_SECRET_KEY', None):
            with self.assertRaises(RuntimeError) as ctx:
                create_app()
            self.assertIn("JWT_SECRET_KEY is missing or set to an insecure default", str(ctx.exception))

        # 4. Hardcoded fallback JWT_SECRET_KEY in production
        with patch.object(Config, 'ENV', 'production'), \
             patch.object(Config, 'is_prod', True), \
             patch.object(Config, 'SECRET_KEY', 'valid-production-flask-secret-key-67890'), \
             patch.object(Config, 'JWT_SECRET_KEY', 'sentinel-trace-prod-jwt-key-2026-secure-fallback'):
            with self.assertRaises(RuntimeError) as ctx:
                create_app()
            self.assertIn("JWT_SECRET_KEY is missing or set to an insecure default", str(ctx.exception))

    def test_08_production_mode_starts_with_strong_unique_secrets(self):
        """In production mode with strong unique secrets, application initializes cleanly."""
        with patch.object(Config, 'ENV', 'production'), \
             patch.object(Config, 'is_prod', True), \
             patch.object(Config, 'SECRET_KEY', 'strong-production-flask-secret-key-99999'), \
             patch.object(Config, 'JWT_SECRET_KEY', 'strong-production-jwt-secret-key-88888'):
            prod_app = create_app()
            self.assertIsNotNone(prod_app)

    def test_09_development_mode_permits_safe_fallbacks(self):
        """In development mode, safe fallback secrets allow local development to proceed."""
        with patch.object(Config, 'ENV', 'development'), \
             patch.object(Config, 'is_prod', False):
            dev_app = create_app()
            self.assertIsNotNone(dev_app)

    # =========================================================================
    # TASK 4: PREVENT INSECURE DEFAULT ACCOUNTS IN PRODUCTION (P1)
    # =========================================================================
    def test_10_production_mode_does_not_seed_default_accounts(self):
        """ensure_default_admin_users() must be a no-op in production mode."""
        # Use a fresh unseeded users collection mock to verify no accounts are written
        with patch.object(Config, 'ENV', 'production'), patch.object(Config, 'is_prod', True):
            # Temporarily point to an isolated collection name
            test_coll_name = 'test_prod_unseeded_users'
            with patch.object(Config, 'COLLECTION_USERS', test_coll_name):
                # Ensure the collection is empty
                docs = db.collection(test_coll_name).get()
                self.assertEqual(len(list(docs)), 0)

                # Call ensure_default_admin_users in production mode
                ensure_default_admin_users()

                # Verify NO documents were written
                docs_after = db.collection(test_coll_name).get()
                self.assertEqual(len(list(docs_after)), 0)

    def test_11_development_mode_can_seed_default_accounts(self):
        """In development mode, ensure_default_admin_users() seeds default accounts when empty."""
        with patch.object(Config, 'ENV', 'development'), patch.object(Config, 'is_prod', False):
            test_coll_name = 'test_dev_seedable_users'
            with patch.object(Config, 'COLLECTION_USERS', test_coll_name):
                # Call ensure_default_admin_users in development mode
                ensure_default_admin_users()

                # Verify default accounts were seeded
                docs_after = db.collection(test_coll_name).get()
                self.assertGreater(len(list(docs_after)), 0)

    # =========================================================================
    # TASK 5: NAVBAR USERNAME CONTRACT AND SCHEMA INTEGRITY (P2)
    # =========================================================================
    def test_12_auth_login_response_schema_and_username_contract(self):
        """Verify login endpoint returns username in user payload matching frontend common.js expectations."""
        res = self.client.post('/api/auth/login', json={
            "email": "admin@sentineltrace.local",
            "password": "ChangeMe123!"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        user_info = data['data']['user']
        self.assertIn('username', user_info)
        self.assertEqual(user_info['username'], 'Jack Mathew')
        self.assertEqual(user_info['role'], 'Admin')

        # Simulate client-side normalization logic in common.js:
        # const displayName = parsed.username || parsed.name || "Operator";
        client_display_name = user_info.get('username') or user_info.get('name') or "Operator"
        client_avatar_initial = (client_display_name or 'U')[0].upper()
        self.assertEqual(client_display_name, "Jack Mathew")
        self.assertEqual(client_avatar_initial, "J")


if __name__ == '__main__':
    unittest.main()
