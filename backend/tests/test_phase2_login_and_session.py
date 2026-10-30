"""
Phase 4: Automated Regression Test Suite
Authentication Flow, Session Management, and Dashboard Integration

Regression test coverage:
1. Successful login with valid credentials.
2. Rejection of invalid credentials.
3. Missing email or password.
4. Correct token and user response structure.
5. Authentication state stored under the expected keys.
6. Successful redirect to the dashboard.
7. Protected page access without a token.
8. Protected page access with a valid token.
9. Expired or invalid JWT handling.
10. Logout and session cleanup.
11. Dashboard initialization after login.
12. Failed API requests and useful frontend error messages.
"""

import sys
import os
import unittest
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import jwt

# Set local Firestore mock for hermetic testing
os.environ['USE_LOCAL_FIRESTORE'] = 'true'

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import create_app
from seed import seed_database
from config import Config
from services.auth_service import ensure_default_admin_users, generate_jwt, hash_password


class LoginAndSessionManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()
        ensure_default_admin_users()

    @classmethod
    def tearDownClass(cls):
        # Clean up environment so subsequent integration tests can use live Cloud Firestore
        if 'USE_LOCAL_FIRESTORE' in os.environ:
            del os.environ['USE_LOCAL_FIRESTORE']
        import config.firebase as fb
        fb._firebase_initialized = False
        fb.db = None
        fb.init_firebase()

    def test_01_successful_login_with_valid_credentials(self):
        """1. Successful login with valid credentials returns HTTP 200, JWT token, and user info."""
        res = self.client.post('/api/auth/login', json={
            "email": "admin@sentineltrace.local",
            "password": "ChangeMe123!"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('data', data)
        self.assertIn('token', data['data'])
        self.assertIn('user', data['data'])

        user = data['data']['user']
        self.assertEqual(user['email'], "admin@sentineltrace.local")
        self.assertEqual(user['role'], "Admin")
        self.assertEqual(user['status'], "Active")
        self.assertNotIn('password', user)
        self.assertNotIn('password_hash', user)

    def test_02_rejection_of_invalid_credentials(self):
        """2. Rejection of invalid credentials (wrong password & non-existent user)."""
        # Incorrect password
        res = self.client.post('/api/auth/login', json={
            "email": "admin@sentineltrace.local",
            "password": "WrongPassword123!"
        })
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error', {}).get('code'), 'AUTHENTICATION_FAILED')

        # Non-existent email
        res_none = self.client.post('/api/auth/login', json={
            "email": "doesnotexist@sentineltrace.io",
            "password": "SomePassword123!"
        })
        self.assertEqual(res_none.status_code, 401)
        data_none = res_none.get_json()
        self.assertFalse(data_none.get('success'))

    def test_03_missing_email_or_password(self):
        """3. Missing email or password rejected with HTTP 400 validation error."""
        # Missing password
        res1 = self.client.post('/api/auth/login', json={"email": "admin@sentineltrace.local"})
        self.assertEqual(res1.status_code, 400)
        self.assertEqual(res1.get_json().get('error', {}).get('code'), 'VALIDATION_ERROR')

        # Missing email
        res2 = self.client.post('/api/auth/login', json={"password": "password123"})
        self.assertEqual(res2.status_code, 400)
        self.assertEqual(res2.get_json().get('error', {}).get('code'), 'VALIDATION_ERROR')

        # Empty payload
        res3 = self.client.post('/api/auth/login', json={})
        self.assertEqual(res3.status_code, 400)

    def test_04_correct_token_and_user_response_structure(self):
        """4. Correct token and user response structure, header algorithm, and claim verification."""
        res = self.client.post('/api/auth/login', json={
            "email": "admin@sentineltrace.local",
            "password": "ChangeMe123!"
        })
        token = res.get_json()['data']['token']

        # Header check
        unverified_header = jwt.get_unverified_header(token)
        self.assertEqual(unverified_header['alg'], 'HS256')

        # Payload claims verification
        payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=['HS256'])
        self.assertEqual(payload['email'], "admin@sentineltrace.local")
        self.assertEqual(payload['role'], "Admin")
        self.assertIn('exp', payload)
        self.assertIn('iat', payload)
        self.assertGreater(payload['exp'], time.time())

    def test_05_authentication_state_stored_under_expected_keys(self):
        """5. Authentication state stored under expected keys in frontend storage."""
        frontend_dir = backend_dir.parent / 'frontend' / 'js'
        auth_js = (frontend_dir / 'auth.js').read_text()
        config_js = (frontend_dir / 'config.js').read_text()
        common_js = (frontend_dir / 'common.js').read_text()

        # Both legacy 'token' and prefixed 'sentinelToken' keys must be supported
        for key in ["token", "sentinelToken", "user", "sentinelUser"]:
            self.assertIn(f'"{key}"', config_js, f"config.js must store/retrieve {key}")

        # Check setAuthSession sync
        self.assertIn('localStorage.setItem("token", token)', config_js)
        self.assertIn('localStorage.setItem("sentinelToken", token)', config_js)
        self.assertIn('sessionStorage.setItem("token", token)', config_js)

    def test_06_successful_redirect_to_dashboard(self):
        """6. Successful redirect to dashboard upon successful login."""
        frontend_dir = backend_dir.parent / 'frontend' / 'js'
        auth_js = (frontend_dir / 'auth.js').read_text()

        self.assertIn('dashboard.html', auth_js)
        self.assertIn('window.location.href = "dashboard.html"', auth_js)
        self.assertIn('apiLogin', auth_js)

    def test_07_protected_page_access_without_token(self):
        """7. Protected API endpoints return 401 when accessed without a token."""
        endpoints = [
            '/api/dashboard/stats',
            '/api/products',
            '/api/batches',
            '/api/materials',
            '/api/suppliers',
            '/api/compliance',
            '/api/reports/summary',
            '/api/logs',
            '/api/alerts'
        ]
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 401, f"Endpoint {ep} must reject unauthenticated requests")

    def test_08_protected_page_access_with_valid_token(self):
        """8. Protected API endpoints return 200 when accessed with a valid token."""
        res_login = self.client.post('/api/auth/login', json={
            "email": "admin@sentineltrace.local",
            "password": "ChangeMe123!"
        })
        token = res_login.get_json()['data']['token']
        headers = {"Authorization": f"Bearer {token}"}

        endpoints = [
            '/api/dashboard/stats',
            '/api/products',
            '/api/batches',
            '/api/materials',
            '/api/suppliers',
            '/api/compliance',
            '/api/reports/summary',
            '/api/logs',
            '/api/alerts'
        ]
        for ep in endpoints:
            res = self.client.get(ep, headers=headers)
            self.assertEqual(res.status_code, 200, f"Endpoint {ep} must succeed for authenticated user")

    def test_09_expired_or_invalid_jwt_handling(self):
        """9. Expired or tampered JWTs are rejected with 401."""
        # Expired token
        expired_payload = {
            'user_id': 'USR-EXPIRED',
            'username': 'Expired User',
            'email': 'expired@sentineltrace.io',
            'role': 'Operator',
            'exp': datetime.now(timezone.utc) - timedelta(hours=1),
            'iat': datetime.now(timezone.utc) - timedelta(hours=2)
        }
        expired_token = jwt.encode(expired_payload, Config.JWT_SECRET_KEY, algorithm='HS256')
        res_exp = self.client.get('/api/dashboard/stats', headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(res_exp.status_code, 401)

        # Tampered signature
        tampered_token = expired_token[:-4] + "AAAA"
        res_tamp = self.client.get('/api/dashboard/stats', headers={"Authorization": f"Bearer {tampered_token}"})
        self.assertEqual(res_tamp.status_code, 401)

        # Arbitrary non-JWT header
        res_rand = self.client.get('/api/dashboard/stats', headers={"Authorization": "Bearer invalid.jwt.string"})
        self.assertEqual(res_rand.status_code, 401)

    def test_10_logout_and_session_cleanup(self):
        """10. Logout and session cleanup clear tokens and redirect to login."""
        frontend_dir = backend_dir.parent / 'frontend' / 'js'
        config_js = (frontend_dir / 'config.js').read_text()
        common_js = (frontend_dir / 'common.js').read_text()

        self.assertIn('clearAuthSession', config_js)
        self.assertIn('apiLogout', config_js)
        self.assertIn('localStorage.removeItem("token")', config_js)
        self.assertIn('localStorage.removeItem("sentinelToken")', config_js)
        self.assertIn('handleLogout', common_js)
        self.assertIn('login.html', common_js)

    def test_11_dashboard_initialization_after_login(self):
        """11. Dashboard initialization loads authenticated stats and metrics."""
        res_login = self.client.post('/api/auth/login', json={
            "email": "jack@sentineltrace.io",
            "password": "password123"
        })
        token = res_login.get_json()['data']['token']

        res_stats = self.client.get('/api/dashboard/stats', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_stats.status_code, 200)
        data = res_stats.get_json()['data']

        self.assertIn('total_batches', data)
        self.assertIn('total_units_produced', data)
        self.assertIn('recent_batches', data)
        self.assertIn('monthly_throughput', data)

    def test_12_failed_api_requests_and_frontend_error_messages(self):
        """12. Failed API requests surface clear, useful frontend error messages."""
        frontend_dir = backend_dir.parent / 'frontend' / 'js'
        config_js = (frontend_dir / 'config.js').read_text()
        auth_js = (frontend_dir / 'auth.js').read_text()

        # Checks for user-friendly network error detection
        self.assertIn('Unable to connect to Sentinel-Trace server', config_js)
        self.assertIn('showToast', auth_js)
        self.assertIn('Authentication error:', auth_js)


if __name__ == '__main__':
    unittest.main()
